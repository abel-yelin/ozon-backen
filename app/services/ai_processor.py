"""AI Image Processing Service - Core processing logic for AI operations

This module contains the heavy lifting logic for:
- Background replacement using external LLM API
- Batch optimization (compression, resizing)
- Image enhancement (sharpening, upscaling)
"""

from __future__ import annotations
import base64
import io
import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from PIL import Image, ImageFilter, ImageEnhance
import aiohttp
import requests
import logging

logger = logging.getLogger(__name__)


class AiImageProcessor:
    """Core AI image processing service"""

    def __init__(self, config: Dict[str, Any]):
        """Initialize AI processor with configuration

        Args:
            config: Dictionary containing:
                - api_base: LLM API base URL
                - api_key: LLM API key
                - model: Model name for image generation
                - target_width: Default target width
                - target_height: Default target height
                - default_temperature: Default temperature for generation
        """
        self.api_base = config.get("api_base", "")
        self.api_key = config.get("api_key", "")
        self.model = config.get("model", "")
        self.target_width = config.get("target_width", 1500)
        self.target_height = config.get("target_height", 2000)
        self.default_temperature = config.get("default_temperature", 0.5)

    async def process_background_replacement(
        self,
        image_data: bytes,
        background_prompt: str,
        negative_prompt: str = "",
        temperature: float = 0.5,
        cancel_check: Optional[callable] = None
    ) -> Tuple[bytes, Dict[str, Any]]:
        """Process background replacement using AI

        Args:
            image_data: Source image bytes
            background_prompt: Description of desired background
            negative_prompt: Things to avoid in the background
            temperature: Generation temperature (0-1)
            cancel_check: Optional callable to check for cancellation

        Returns:
            Tuple of (result_image_bytes, metadata)

        Raises:
            ValueError: If API configuration is invalid
            requests.RequestException: If API call fails
            Exception: If processing fails
        """
        if cancel_check:
            cancel_check()

        if not self.api_key or not self.api_base or not self.model:
            raise ValueError("AI API configuration is incomplete")

        # Load image
        image = Image.open(io.BytesIO(image_data))
        if image.mode != "RGB":
            image = image.convert("RGB")

        original_width, original_height = image.size

        # Build prompt
        extra_prompt = f"Background: {background_prompt}"
        if negative_prompt:
            extra_prompt += f". Negative: {negative_prompt}"

        # Call external LLM API for image generation
        result_image = await self._call_ai_image_api(
            image=image,
            prompt=extra_prompt,
            temperature=temperature,
            cancel_check=cancel_check
        )

        metadata = {
            "original_width": original_width,
            "original_height": original_height,
            "result_width": result_image.width,
            "result_height": result_image.height,
            "background_prompt": background_prompt,
        }

        # Convert result to bytes
        output = io.BytesIO()
        result_image.save(output, format="PNG")
        result_bytes = output.getvalue()

        return result_bytes, metadata

    async def process_batch_optimization(
        self,
        image_data: bytes,
        quality: str = "standard",
        output_format: str = "webp",
        max_size: int = 1920,
        maintain_aspect: bool = True,
        cancel_check: Optional[callable] = None
    ) -> Tuple[bytes, Dict[str, Any]]:
        """Process batch optimization (compression and resizing)

        Args:
            image_data: Source image bytes
            quality: Quality level (low, standard, high)
            output_format: Output format (png, jpg, webp)
            max_size: Maximum dimension
            maintain_aspect: Whether to maintain aspect ratio
            cancel_check: Optional callable to check for cancellation

        Returns:
            Tuple of (optimized_image_bytes, metadata)
        """
        if cancel_check:
            cancel_check()

        image = Image.open(io.BytesIO(image_data))
        original_size = len(image_data)
        original_width, original_height = image.size

        # Determine quality values
        quality_map = {"low": 70, "standard": 85, "high": 95}
        jpeg_quality = quality_map.get(quality, 85)

        # Resize if needed
        if max_size and (image.width > max_size or image.height > max_size):
            if maintain_aspect:
                image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            else:
                image = image.resize((max_size, max_size), Image.Resampling.LANCZOS)

        # Determine format
        format_map = {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "webp": "WEBP"}
        pil_format = format_map.get(output_format.lower(), "PNG")

        # Save with optimization
        output = io.BytesIO()
        save_kwargs = {}
        if pil_format in ("JPEG", "WEBP"):
            save_kwargs["quality"] = jpeg_quality
            save_kwargs["optimize"] = True

        image.save(output, format=pil_format, **save_kwargs)
        result_bytes = output.getvalue()

        metadata = {
            "original_width": original_width,
            "original_height": original_height,
            "result_width": image.width,
            "result_height": image.height,
            "original_size": original_size,
            "result_size": len(result_bytes),
            "compression_ratio": round(1 - len(result_bytes) / original_size, 2),
            "quality": quality,
            "format": output_format,
        }

        return result_bytes, metadata

    async def process_image_enhancement(
        self,
        image_data: bytes,
        enhancement_level: int = 5,
        sharpen: bool = True,
        denoise: bool = True,
        upscale: bool = False,
        cancel_check: Optional[callable] = None
    ) -> Tuple[bytes, Dict[str, Any]]:
        """Process image enhancement

        Args:
            image_data: Source image bytes
            enhancement_level: Enhancement level (1-10)
            sharpen: Whether to apply sharpening
            denoise: Whether to apply denoising
            upscale: Whether to upscale 2x
            cancel_check: Optional callable to check for cancellation

        Returns:
            Tuple of (enhanced_image_bytes, metadata)
        """
        if cancel_check:
            cancel_check()

        image = Image.open(io.BytesIO(image_data))
        if image.mode != "RGB":
            image = image.convert("RGB")

        original_width, original_height = image.size

        # Apply sharpening
        if sharpen:
            image = image.filter(ImageFilter.SHARPEN)
            if cancel_check:
                cancel_check()

        # Apply denoising (smooth)
        if denoise:
            image = image.filter(ImageFilter.SMOOTH)
            if cancel_check:
                cancel_check()

        # Adjust contrast based on enhancement level
        if enhancement_level > 0:
            enhancer = ImageEnhance.Contrast(image)
            contrast_factor = 1.0 + (enhancement_level * 0.05)
            image = enhancer.enhance(contrast_factor)
            if cancel_check:
                cancel_check()

            # Adjust brightness slightly
            enhancer = ImageEnhance.Brightness(image)
            brightness_factor = 1.0 + (enhancement_level * 0.03)
            image = enhancer.enhance(brightness_factor)
            if cancel_check:
                cancel_check()

        # Upscale if requested
        if upscale:
            new_width = image.width * 2
            new_height = image.height * 2
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

        output = io.BytesIO()
        image.save(output, format="PNG")
        result_bytes = output.getvalue()

        metadata = {
            "original_width": original_width,
            "original_height": original_height,
            "result_width": image.width,
            "result_height": image.height,
            "enhancement_level": enhancement_level,
            "sharpen": sharpen,
            "denoise": denoise,
            "upscale": upscale,
        }

        return result_bytes, metadata

    async def _call_ai_image_api(
        self,
        image: Image.Image,
        prompt: str,
        temperature: float,
        cancel_check: Optional[callable] = None
    ) -> Image.Image:
        """Call external LLM API for image generation/editing

        Args:
            image: PIL Image to process
            prompt: Processing prompt
            temperature: Generation temperature
            cancel_check: Optional callable to check for cancellation

        Returns:
            Processed PIL Image

        Raises:
            requests.RequestException: If API call fails
        """
        # Encode image to base64
        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        image_bytes = buffered.getvalue()
        base64_image = base64.b64encode(image_bytes).decode("utf-8")

        # Build API request
        url = f"{self.api_base.rstrip('/')}/{self.model}:generateContent"

        payload = {
            "contents": [
                {
                    "parts": [
                        {"inline_data": {"mime_type": "image/png", "data": base64_image}},
                        {"text": prompt}
                    ]
                }
            ],
            "generationConfig": {"temperature": temperature}
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        if cancel_check:
            cancel_check()

        # Make API call
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=300) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise requests.RequestException(f"API error {response.status}: {error_text}")

                data = await response.json()

        if cancel_check:
            cancel_check()

        # Parse response
        candidates = data.get("candidates", [])
        if not candidates:
            raise ValueError("No candidates in API response")

        content = candidates[0].get("content", {})
        parts = content.get("parts", [])

        # Look for inline data (image)
        for part in parts:
            inline_data = part.get("inlineData")
            if inline_data:
                result_base64 = inline_data.get("data", "")
                result_bytes = base64.b64decode(result_base64)
                return Image.open(io.BytesIO(result_bytes))

        raise ValueError("No image data in API response")

    @staticmethod
    def download_image(url: str) -> bytes:
        """Download image from URL

        Args:
            url: Image URL (http, https, or data: base64)

        Returns:
            Image bytes

        Raises:
            ValueError: If URL is invalid or download fails
        """
        if url.startswith("data:image"):
            # Base64 encoded image
            header, data = url.split(",", 1)
            return base64.b64decode(data)

        elif url.startswith("http://") or url.startswith("https://"):
            # URL image - download synchronously
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            return response.content

        else:
            # Local file path
            path = Path(url)
            if not path.exists():
                raise FileNotFoundError(f"Image not found: {url}")
            return path.read_bytes()
