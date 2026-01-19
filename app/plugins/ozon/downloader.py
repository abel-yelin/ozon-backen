"""Image downloader with direct R2 upload (no local storage)"""

import logging
import aiohttp
from typing import Tuple, Optional
from io import BytesIO

logger = logging.getLogger(__name__)


async def download_image_to_bytes(url: str, timeout: int = 20) -> Tuple[bool, Optional[bytes], Optional[str]]:
    """
    Download image directly to memory (bytes).

    Args:
        url: Image URL (supports http/https and data URLs)
        timeout: Request timeout in seconds

    Returns:
        Tuple of (success, image_bytes, error_message)
    """
    # Handle data URLs
    if url.startswith("data:"):
        try:
            import base64
            from urllib.parse import unquote_to_bytes

            header, data = url.split(",", 1)
            if ";base64" in header:
                image_bytes = base64.b64decode(data)
            else:
                image_bytes = unquote_to_bytes(data)

            return True, image_bytes, None

        except Exception as e:
            logger.error(f"Error decoding data URL: {e}")
            return False, None, str(e)

    # Handle HTTP/HTTPS URLs
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
                if response.status == 200:
                    image_bytes = await response.read()
                    return True, image_bytes, None
                else:
                    error = f"HTTP {response.status}"
                    logger.error(f"Failed to download {url}: {error}")
                    return False, None, error

    except aiohttp.ClientError as e:
        logger.error(f"HTTP client error downloading {url}: {e}")
        return False, None, str(e)
    except Exception as e:
        logger.error(f"Unexpected error downloading {url}: {e}")
        return False, None, str(e)


async def download_and_upload_to_r2(
    url: str,
    r2_path: str,
    r2_service,
    timeout: int = 20
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Download image and directly upload to R2 (streaming, no local storage).

    Args:
        url: Image URL to download
        r2_path: Destination path in R2
        r2_service: R2StorageService instance
        timeout: Request timeout in seconds

    Returns:
        Tuple of (success, r2_public_url, error_message)
    """
    # Download to memory
    success, image_bytes, error = await download_image_to_bytes(url, timeout)

    if not success:
        return False, None, error

    # Upload directly to R2
    try:
        public_url = await r2_service.upload_bytes(image_bytes, r2_path)
        return True, public_url, None
    except Exception as e:
        logger.error(f"Error uploading to R2: {e}")
        return False, None, str(e)


def generate_r2_path(user_id: str, article: str, index: int, extension: str = "jpg") -> str:
    """
    Generate R2 storage path for an image.

    Format: users/{user_id}/ozon/{article}/{article}_{index}.{ext}

    Args:
        user_id: User identifier
        article: Product article number
        index: Image index
        extension: File extension

    Returns:
        R2 path
    """
    # Sanitize article for filename
    safe_article = "".join(c if c.isalnum() or c in "-_" else "_" for c in article)
    return f"users/{user_id}/ozon/{safe_article}/{safe_article}_{index}.{extension}"
