"""Ozon download plugin - main orchestrator"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

from app.plugins.base import BasePlugin, ProcessingMode
from app.plugins.ozon.client import OzonClient
from app.plugins.ozon.downloader import download_and_upload_to_r2, generate_r2_path
from app.services.storage import R2StorageService

logger = logging.getLogger(__name__)


class OzonDownloadPlugin(BasePlugin):
    """
    Plugin for batch downloading Ozon product images.

    Features:
    - Multi-account support (user-configured credentials)
    - Direct R2 upload (no local storage)
    - Concurrent downloads
    - Multiple search fields (offer_id, sku, vendor_code)
    """

    name = "ozon-download"
    display_name = "Ozon 图片下载"
    category = "platform"
    processing_mode = ProcessingMode.SYNC

    def __init__(self, config: dict):
        """
        Initialize plugin.

        Args:
            config: Plugin configuration from YAML
        """
        self.config = config
        self.max_workers = config.get("max_workers", 5)
        self.timeout = config.get("timeout_sec", 20)
        self.default_field = config.get("default_field", "offer_id")

    async def process(self, input_data: dict) -> dict:
        """
        Process download task.

        Args:
            input_data: {
                "user_id": str,
                "credential": {
                    "client_id": str,
                    "api_key": str
                },
                "articles": List[str],
                "field": str (optional),
                "r2_service": R2StorageService,
                "download_images": bool (optional, default=True)
            }

        Returns:
            Result dict with download statistics
        """
        user_id = input_data.get("user_id")
        credential = input_data.get("credential", {})
        articles = input_data.get("articles", [])
        field = input_data.get("field", self.default_field)
        r2_service = input_data.get("r2_service")
        download_images = input_data.get("download_images", True)

        if not user_id or not r2_service:
            raise ValueError("Missing required fields: user_id, r2_service")

        if not credential.get("client_id") or not credential.get("api_key"):
            raise ValueError("Invalid credential")

        result = {
            "total_articles": len(articles),
            "processed": 0,
            "total_images": 0,
            "success_images": 0,
            "failed_images": 0,
            "items": []
        }

        # Create Ozon client
        client = OzonClient(
            client_id=credential["client_id"],
            api_key=credential["api_key"],
            timeout=self.timeout
        )

        try:
            # Process each article
            for article in articles:
                item_result = await self._process_article(
                    client=client,
                    user_id=user_id,
                    article=article,
                    field=field,
                    r2_service=r2_service,
                    download_images=download_images
                )

                result["items"].append(item_result)
                result["processed"] += 1

                result["total_images"] += item_result["total_images"]
                result["success_images"] += item_result["success_images"]
                result["failed_images"] += item_result["failed_images"]

        finally:
            await client.close()

        return result

    async def _process_article(
        self,
        client: OzonClient,
        user_id: str,
        article: str,
        field: str,
        r2_service: R2StorageService,
        download_images: bool = True
    ) -> dict:
        """
        Process a single article.

        Args:
            client: Ozon API client
            user_id: User ID for R2 path
            article: Article number
            field: Search field type
            r2_service: R2 storage service
            download_images: If True, download and upload to R2. If False, only return Ozon URLs.

        Returns:
            {
                "article": str,
                "product_id": Optional[int],
                "status": "success" | "failed",
                "total_images": int,
                "success_images": int,
                "failed_images": int,
                "urls": List[str],
                "error": Optional[str]
            }
        """
        logger.info(f"Processing article={article} field={field} download_images={download_images}")

        # Step 1: Find product ID
        product_id = await client.find_product_id(article, field)

        if not product_id:
            logger.warning(f"Product not found for article={article}")
            return {
                "article": article,
                "status": "failed",
                "error": "PRODUCT_NOT_FOUND",
                "total_images": 0,
                "success_images": 0,
                "failed_images": 0,
                "urls": []
            }

        logger.info(f"Found product_id={product_id} for article={article}")

        # Step 2: Get image URLs
        image_urls = await client.get_picture_urls(product_id)

        if not image_urls:
            logger.warning(f"No images found for article={article}")
            return {
                "article": article,
                "product_id": product_id,
                "status": "failed",
                "error": "NO_IMAGES",
                "total_images": 0,
                "success_images": 0,
                "failed_images": 0,
                "urls": []
            }

        logger.info(f"Found {len(image_urls)} images for article={article}")

        # Step 3: Return Ozon URLs directly (metadata-only mode)
        if not download_images:
            logger.info(f"Metadata-only mode: returning {len(image_urls)} Ozon URLs without downloading")
            return {
                "article": article,
                "product_id": product_id,
                "status": "success",
                "total_images": len(image_urls),
                "success_images": len(image_urls),
                "failed_images": 0,
                "urls": image_urls  # Return original Ozon URLs
            }

        # Step 4: Download and upload to R2 (concurrent)
        stats = {
            "total": len(image_urls),
            "success": 0,
            "failed": 0,
            "urls": []
        }

        # Create semaphore for concurrent control
        semaphore = asyncio.Semaphore(self.max_workers)

        async def download_single(index: int, url: str) -> Optional[str]:
            """Download single image and upload to R2"""
            async with semaphore:
                # Detect extension from URL
                extension = self._get_extension_from_url(url)

                # Generate R2 path
                r2_path = generate_r2_path(user_id, article, index + 1, extension)

                # Download and upload
                success, public_url, error = await download_and_upload_to_r2(
                    url=url,
                    r2_path=r2_path,
                    r2_service=r2_service,
                    timeout=self.timeout
                )

                if success:
                    stats["success"] += 1
                    stats["urls"].append(public_url)
                    logger.debug(f"Successfully downloaded {url} -> {public_url}")
                else:
                    stats["failed"] += 1
                    logger.error(f"Failed to download {url}: {error}")

                return public_url if success else None

        # Run downloads concurrently
        tasks = [
            download_single(i, url)
            for i, url in enumerate(image_urls)
        ]

        await asyncio.gather(*tasks, return_exceptions=True)

        status = "success" if stats["success"] > 0 else "failed"
        error = None
        if status == "failed":
            error = "DOWNLOAD_FAILED"
        return {
            "article": article,
            "product_id": product_id,
            "status": status,
            "total_images": stats["total"],
            "success_images": stats["success"],
            "failed_images": stats["failed"],
            "urls": stats["urls"],
            "error": error
        }

    def _get_extension_from_url(self, url: str) -> str:
        """Extract file extension from URL"""
        url_lower = url.lower()
        for ext in ["webp", "jpg", "jpeg", "png"]:
            if f".{ext}" in url_lower:
                return ext
        return "jpg"  # Default

    def validate_input(self, input_data: dict) -> Tuple[bool, Optional[str]]:
        """
        Validate input data.

        Returns:
            Tuple of (is_valid, error_message)
        """
        required_fields = ["user_id", "credential", "articles", "r2_service"]

        for field in required_fields:
            if field not in input_data:
                return False, f"Missing required field: {field}"

        articles = input_data.get("articles", [])

        if not isinstance(articles, list):
            return False, "articles must be a list"

        if not articles:
            return False, "articles list cannot be empty"

        credential = input_data.get("credential", {})

        if not credential.get("client_id") or not credential.get("api_key"):
            return False, "Invalid credential: missing client_id or api_key"

        return True, None
