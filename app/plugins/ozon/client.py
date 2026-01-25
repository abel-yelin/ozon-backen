"""Ozon Seller API client"""

import json
import logging
from typing import Optional, List, Dict
import aiohttp
from aiohttp import ClientTimeout
import os

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
                # Ozon API returns text/plain Content-Type, so we need to ignore content type check
                # Also, get raw text first to handle potential formatting issues
                text = await response.text()

                # Log the raw response for debugging
                if os.environ.get("OZON_DEBUG") == "1":
                    logger.debug(f"Ozon API raw response {path}: {text}")

                # Parse JSON, handling potential extra whitespace or multiple objects
                try:
                    # Try parsing the full response first
                    data = json.loads(text)
                except json.JSONDecodeError as e:
                    # If that fails, try to extract just the first JSON object
                    # Ozon sometimes returns responses with extra whitespace/newlines
                    logger.warning(f"JSON parse error on {path}, trying to clean response: {e}")
                    logger.warning(f"Raw response text (first 500 chars): {text[:500]}")

                    # Try stripping whitespace
                    try:
                        data = json.loads(text.strip())
                    except json.JSONDecodeError:
                        # If still failing, try extracting first JSON object
                        # Find matching braces
                        text = text.strip()
                        if text.startswith('{'):
                            # Find matching closing brace
                            brace_count = 0
                            end_pos = 0
                            for i, char in enumerate(text):
                                if char == '{':
                                    brace_count += 1
                                elif char == '}':
                                    brace_count -= 1
                                if brace_count == 0:
                                    end_pos = i + 1
                                    break
                            if end_pos > 0:
                                data = json.loads(text[:end_pos])
                            else:
                                raise
                        else:
                            raise

                if response.status != 200:
                    logger.warning(
                        "Ozon API non-200 response %s %s: %s",
                        response.status,
                        path,
                        data
                    )
                if os.environ.get("OZON_DEBUG") == "1":
                    logger.debug("Ozon API response %s: %s", path, data)
                return data

    def _value_matches(self, value: object, target: str) -> bool:
        """Match target string against scalar or list values."""
        if value is None:
            return False
        if isinstance(value, list):
            return any(str(v) == target for v in value)
        return str(value) == target

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
                filter_payload = {
                    "offer_id": [article],
                    "product_id": [],
                    "visibility": "ALL"
                }
            else:
                filter_payload = {
                    field: [article],
                    "product_id": [],
                    "visibility": "ALL"
                }

            payload = {
                "filter": filter_payload,
                "last_id": "",
                "limit": 100
            }

            response = await self._post("/v3/product/list", payload)
            if response.get("error") or response.get("errors"):
                logger.warning(
                    "Ozon API error on product list for article=%s field=%s: %s",
                    article,
                    field,
                    response.get("error") or response.get("errors")
                )
                return None
            items = response.get("result", {}).get("items", [])
            total = response.get("result", {}).get("total")
            target = str(article)

            for item in items:
                product_id = item.get("product_id")
                field_value = item.get(field) or item.get("offer_id")

                if self._value_matches(field_value, target):
                    if product_id:
                        try:
                            return int(product_id)
                        except (ValueError, TypeError):
                            return int(str(product_id))

            if items and total == 1:
                product_id = items[0].get("product_id")
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
            if response.get("error") or response.get("errors"):
                logger.warning(
                    "Ozon API error on pictures info for product_id=%s: %s",
                    product_id,
                    response.get("error") or response.get("errors")
                )
                return []

            def add_url(value: object) -> None:
                if not value:
                    return
                if isinstance(value, str):
                    s = value.strip()
                    if s.startswith("http://") or s.startswith("https://"):
                        urls.append(s)
                    return
                if isinstance(value, list):
                    for item in value:
                        add_url(item)

            def extract_images(images_list: object) -> None:
                if not images_list:
                    return
                if isinstance(images_list, dict):
                    images_list = [images_list]
                if isinstance(images_list, list):
                    for img in images_list:
                        if isinstance(img, dict):
                            add_url(
                                img.get("url")
                                or img.get("image_url")
                                or img.get("link")
                                or img.get("origin_url")
                                or img.get("preview_url")
                            )
                        else:
                            add_url(img)

            # Check multiple possible response structures
            images = (
                response.get("result", {}).get("images", [])
                or response.get("images", [])
            )
            extract_images(images)

            # Also check items structure
            items = response.get("result", {}).get("items", []) or response.get("items", [])
            if isinstance(items, dict):
                items = [items]
            for item in items:
                if not isinstance(item, dict):
                    continue
                extract_images(item.get("images") or item.get("pictures"))
                for key in ("primary_image", "primary_photo", "photo", "color_photo", "photo_360"):
                    add_url(item.get(key))

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

    async def update_product_pictures(
        self,
        product_id: int,
        images: Optional[List[str]] = None,
        images360: Optional[List[str]] = None,
        color_image: Optional[str] = None
    ) -> dict:
        """
        Update product images on Ozon.

        Replaces all existing images for a product with the provided URLs.
        The first image in the array becomes the primary image.

        Args:
            product_id: Ozon product ID
            images: Main image URLs (max 30, will be truncated)
            images360: 360° image URLs (max 70, will be truncated)
            color_image: Marketing color image URL

        Returns:
            Ozon API response dict

        Raises:
            Exception: If API call fails
        """
        payload = {"product_id": product_id}

        # Add images if provided (truncate to 30)
        if images is not None:
            payload["images"] = images[:30]

        # Add images360 if provided (truncate to 70)
        if images360 is not None:
            payload["images360"] = images360[:70]

        # Add color_image if provided
        if color_image is not None:
            payload["color_image"] = color_image

        # Use the correct endpoint: /v1/product/pictures/import
        return await self._post("/v1/product/pictures/import", payload)

    async def close(self):
        """Close the client (cleanup)"""
        # Client is stateless, nothing to close
        pass
