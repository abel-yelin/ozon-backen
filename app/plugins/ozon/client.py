"""Ozon Seller API client"""

import json
import logging
from typing import Optional, List
import aiohttp
from aiohttp import ClientTimeout

logger = logging.getLogger(__name__)


class OzonClient:
    """
    Client for Ozon Seller API.

    Handles product lookup and image URL retrieval.
    """

    def __init__(self, client_id: str, api_key: str, timeout: int = 20):
        """
        Initialize Ozon API client.

        Args:
            client_id: Ozon Client-Id
            api_key: Ozon Api-Key
            timeout: Request timeout in seconds
        """
        self.client_id = client_id
        self.api_key = api_key
        self.base_url = "https://api-seller.ozon.ru"
        self.timeout = ClientTimeout(total=timeout)

    async def _post(self, path: str, payload: dict) -> dict:
        """
        Make POST request to Ozon API.

        Args:
            path: API endpoint path
            payload: Request payload

        Returns:
            Response data as dict
        """
        url = self.base_url + path
        headers = {
            "Client-Id": self.client_id,
            "Api-Key": self.api_key,
            "Content-Type": "application/json",
        }

        logger.debug(f"Ozon API POST {path} payload={json.dumps(payload, ensure_ascii=False)}")

        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            async with session.post(url, json=payload, headers=headers) as response:
                data = await response.json()
                return data

    async def find_product_id(
        self,
        article: str,
        field: str = "offer_id"
    ) -> Optional[int]:
        """
        Find product ID by article number.

        Args:
            article: Article/SKU number
            field: Field to search (offer_id/sku/vendor_code)

        Returns:
            Product ID or None if not found
        """
        try:
            if field == "offer_id":
                payload = {
                    "filter": {
                        "offer_id": [article],
                        "product_id": [],
                        "visibility": "ALL"
                    },
                    "last_id": "",
                    "limit": 100
                }
            else:
                payload = {
                    "page": 1,
                    "page_size": 100,
                    "filter": {field: article}
                }

            response = await self._post("/v3/product/list", payload)
            items = response.get("result", {}).get("items", [])

            for item in items:
                product_id = item.get("product_id")
                field_value = item.get(field) or item.get("offer_id")

                if str(field_value) == str(article):
                    if product_id:
                        try:
                            return int(product_id)
                        except (ValueError, TypeError):
                            return int(str(product_id))

            logger.warning(f"Product not found for article={article} field={field}")
            return None

        except Exception as e:
            logger.error(f"Error finding product ID: {e}")
            return None

    async def get_picture_urls(self, product_id: int) -> List[str]:
        """
        Get all picture URLs for a product.

        Args:
            product_id: Ozon product ID

        Returns:
            List of unique picture URLs
        """
        try:
            payload = {"product_id": [str(product_id)]}
            response = await self._post("/v2/product/pictures/info", payload)

            urls = []
            # Check multiple possible response structures
            images = (
                response.get("result", {}).get("images", []) or
                response.get("images", [])
            )

            for img in images:
                url = (
                    img.get("url") or
                    img.get("image_url") or
                    img.get("link")
                )
                if url:
                    urls.append(str(url).strip())

            # Also check items structure
            items = response.get("result", {}).get("items", [])
            for item in items:
                for key in ("primary_photo", "photo", "color_photo", "photo_360"):
                    arr = item.get(key) or []
                    for url in arr:
                        if url:
                            urls.append(str(url).strip())

            # Remove duplicates while preserving order
            seen = set()
            unique_urls = []
            for url in urls:
                if url not in seen:
                    seen.add(url)
                    unique_urls.append(url)

            logger.info(f"Found {len(unique_urls)} images for product_id={product_id}")
            return unique_urls

        except Exception as e:
            logger.error(f"Error getting picture URLs: {e}")
            return []

    async def get_product_info(
        self,
        offer_id: str,
        product_id: int
    ) -> dict:
        """
        Get product description info.

        Args:
            offer_id: Offer ID
            product_id: Product ID

        Returns:
            Dict with 'name' and 'description'
        """
        try:
            payload = {
                "offer_id": offer_id,
                "product_id": int(product_id)
            }
            response = await self._post("/v1/product/info/description", payload)

            result = response.get("result", {})
            return {
                "name": result.get("name") or "",
                "description": result.get("description") or ""
            }

        except Exception as e:
            logger.error(f"Error getting product info: {e}")
            return {"name": "", "description": ""}

    async def close(self):
        """Close the client (cleanup)"""
        # Client is stateless, nothing to close
        pass
