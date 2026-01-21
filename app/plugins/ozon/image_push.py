"""Ozon image push plugin for updating product pictures."""

from typing import Optional, List, Dict, Any
import logging

from app.plugins.ozon.client import OzonClient

logger = logging.getLogger(__name__)


class OzonImagePushPlugin:
    """Plugin for pushing images to Ozon product listings."""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the plugin.

        Args:
            config: Plugin configuration dict
        """
        self.config = config

    async def push_images(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Push images to Ozon product.

        Main entry point for image push operation.

        Args:
            context: Dict containing:
                - credential: {client_id, api_key}
                - product_id: int
                - images: List[str] (optional)
                - images360: List[str] (optional)
                - color_image: str (optional)

        Returns:
            Dict with success status and data/errors
        """
        # Step 1: Validate input
        validation = self._validate(context)
        if validation["errors"]:
            return {"success": False, "errors": validation["errors"]}

        try:
            # Step 2: Create Ozon client
            credential = context.get("credential", {})
            client = OzonClient(
                credential.get("client_id", ""),
                credential.get("api_key", "")
            )

            # Step 3: Call Ozon API to update
            update_result = await client.update_product_pictures(
                context["product_id"],
                images=context.get("images") or None,
                images360=context.get("images360") or None,
                color_image=context.get("color_image")
            )

            # Check for API errors
            if update_result.get("error") or update_result.get("errors"):
                error_msg = update_result.get("error") or str(update_result.get("errors"))
                logger.error(f"Ozon API error: {error_msg}")
                return {
                    "success": False,
                    "error": f"Ozon API error: {error_msg}"
                }

            # Step 4: Confirm result by fetching current images
            current_urls = await client.get_picture_urls(context["product_id"])

            # Step 5: Build response
            return self._build_response(update_result, current_urls, context)

        except Exception as e:
            logger.error(f"Error in push_images: {e}")
            return {"success": False, "error": str(e)}

    def _validate(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate input URLs and quantities.

        Args:
            context: Input context dict

        Returns:
            Dict with "errors" list (empty if valid)
        """
        errors = []

        # URL format validation for images array
        for field in ["images", "images360"]:
            urls = context.get(field, [])
            for i, url in enumerate(urls):
                if not isinstance(url, str):
                    errors.append({
                        "field": field,
                        "index": i,
                        "url": str(url),
                        "reason": "Invalid URL format"
                    })
                    continue
                if not url.startswith(("http://", "https://")):
                    errors.append({
                        "field": field,
                        "index": i,
                        "url": url,
                        "reason": "Invalid URL format"
                    })

        # Quantity limits validation
        images = context.get("images", [])
        if len(images) > 30:
            errors.append({
                "field": "images",
                "reason": "Exceeds limit (30)"
            })

        images360 = context.get("images360", [])
        if len(images360) > 70:
            errors.append({
                "field": "images360",
                "reason": "Exceeds limit (70)"
            })

        return {"errors": errors}

    def _build_response(
        self,
        update_result: Dict[str, Any],
        current_urls: List[str],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Build standardized response.

        Args:
            update_result: Raw Ozon API response
            current_urls: Current image URLs from Ozon
            context: Original input context

        Returns:
            Standardized response dict
        """
        product_id = context["product_id"]
        images_count = len(context.get("images", []))
        images360_count = len(context.get("images360", []))
        has_color = context.get("color_image") is not None

        return {
            "success": True,
            "data": {
                "product_id": product_id,
                "updated": {
                    "images": images_count,
                    "images360": images360_count,
                    "color_image": has_color
                },
                "current_images": current_urls
            }
        }
