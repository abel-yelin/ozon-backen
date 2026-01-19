"""Image compression plugin - Phase 1 first plugin"""

from typing import Dict, Any
from app.plugins.base import BasePlugin, ProcessingMode
from PIL import Image
import io
import aiohttp
import hashlib
from app.services.storage import R2Service


class ImageCompressPlugin(BasePlugin):
    """Image compression plugin"""

    name = "image-compress"
    display_name = "图片压缩"
    category = "image"
    processing_mode = ProcessingMode.SYNC

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.r2 = R2Service()
        self.max_file_size = config.get("max_file_size", 52428800)  # 50MB

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Compress image (no database write)

        Flow:
        1. Validate input
        2. Download image
        3. Compress
        4. Upload to R2
        5. Return result
        """
        # 1. Validate input
        is_valid, error = self.validate_input(input_data)
        if not is_valid:
            return {"success": False, "error": error}

        # 2. Download image
        image_url = input_data["image_url"]
        options = input_data.get("options", {})

        async with aiohttp.ClientSession() as session:
            async with session.get(str(image_url)) as resp:
                if resp.status != 200:
                    return {"success": False, "error": "Failed to download image"}
                image_data = await resp.read()

        # 3. Compress
        original_size = len(image_data)
        img = Image.open(io.BytesIO(image_data))

        quality = options.get("quality", 80)
        target_format = options.get("format", img.format).lower()
        max_width = options.get("max_width")
        max_height = options.get("max_height")

        # Resize if needed
        if max_width or max_height:
            img.thumbnail((max_width or img.width, max_height or img.height))

        # Compress
        output = io.BytesIO()
        img.save(output, format=target_format, quality=quality, optimize=True)
        compressed_data = output.getvalue()
        compressed_size = len(compressed_data)

        # 4. Upload to R2
        filename = f"compressed_{hashlib.sha256(image_data).hexdigest()[:16]}.{target_format}"
        output_url = await self.r2.upload(
            data=compressed_data,
            filename=filename,
            content_type=f"image/{target_format}"
        )

        # 5. Return result (no DB write)
        return {
            "success": True,
            "data": {
                "output_url": output_url,
                "metadata": {
                    "original_size": original_size,
                    "compressed_size": compressed_size,
                    "compression_ratio": round(1 - compressed_size / original_size, 2),
                    "width": img.width,
                    "height": img.height,
                    "format": target_format
                }
            }
        }

    def validate_input(self, input_data: Dict[str, Any]) -> tuple[bool, str | None]:
        """Input validation"""
        if "image_url" not in input_data:
            return False, "Missing required parameter: image_url"

        # Optional: check file size
        file_size = input_data.get("file_size", 0)
        if file_size > self.max_file_size:
            return False, f"File size exceeds maximum of {self.max_file_size} bytes"

        return True, None
