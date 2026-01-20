"""AI Playground Plugin - Main plugin for AI image processing operations

This plugin handles three types of AI jobs:
1. Background replacement - Replace image backgrounds with AI-generated scenes
2. Batch optimization - Compress and optimize multiple images
3. Image enhancement - Enhance image quality with upscaling and filters
"""

from __future__ import annotations
import asyncio
import io
import logging
import uuid
import threading
from typing import Any, Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor

from app.plugins.base import BasePlugin, ProcessingMode
from app.services.ai_processor import AiImageProcessor
from app.services.storage import R2Service

logger = logging.getLogger(__name__)


class AiPlaygroundPlugin(BasePlugin):
    """
    AI Playground Plugin for image processing operations.

    This plugin maintains an in-memory job state for tracking processing jobs.
    It does NOT write to any database - all persistence is handled by the frontend.
    """

    name = "ai-playground"
    display_name = "AI Playground"
    category = "ai"
    processing_mode = ProcessingMode.SYNC

    def __init__(self, config: Dict[str, Any]):
        """Initialize the AI Playground plugin

        Args:
            config: Plugin configuration dictionary containing:
                - api_base: LLM API base URL
                - api_key: LLM API key
                - model: Model name for image generation
                - target_width: Default target width
                - target_height: Default target height
                - default_temperature: Default temperature
        """
        self.config = config
        self.processor = AiImageProcessor(config)
        self.r2 = R2Service()

        # In-memory job state (NOT persistent)
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._job_lock = threading.Lock()
        self._cancel_events: Dict[str, threading.Event] = {}

    @property
    def enabled(self) -> bool:
        """Plugin is enabled if API key is configured"""
        return bool(self.config.get("api_key"))

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process an AI job request

        Args:
            input_data: Dictionary containing:
                - job_id: Unique job identifier
                - user_id: User identifier
                - type: Job type (background_replacement, batch_optimization, image_enhancement)
                - config: Job-specific configuration
                - source_image_urls: List of source image URLs

        Returns:
            Dictionary with:
                - success: bool
                - data: Result data (if successful)
                - error: Error message (if failed)
        """
        job_id = input_data.get("job_id") or str(uuid.uuid4())
        job_type = input_data.get("type", "background_replacement")
        source_urls = input_data.get("source_image_urls", [])
        config = input_data.get("config", {})

        if not source_urls:
            return {"success": False, "error": "No source images provided"}

        # Initialize job state
        with self._job_lock:
            self._jobs[job_id] = {
                "job_id": job_id,
                "type": job_type,
                "status": "processing",
                "progress": 0,
                "total": len(source_urls),
                "processed": 0,
                "result_urls": [],
                "source_urls": source_urls,
                "metadata": [],
                "error": None,
            }
            self._cancel_events[job_id] = threading.Event()

        try:
            # Process each image
            for idx, url in enumerate(source_urls):
                # Check for cancellation
                if self._cancel_events[job_id].is_set():
                    raise Exception("Job cancelled")

                # Download source image
                try:
                    image_bytes = self.processor.download_image(url)
                except Exception as e:
                    logger.error(f"Failed to download image {idx + 1}: {e}")
                    with self._job_lock:
                        job = self._jobs.get(job_id, {})
                        job["error"] = f"Image {idx + 1} download failed: {str(e)}"
                        job["status"] = "failed"
                    return {"success": False, "error": job["error"]}

                # Process based on job type
                try:
                    result_bytes, metadata = await self._process_single_image(
                        job_type=job_type,
                        image_bytes=image_bytes,
                        config=config,
                        cancel_check=lambda: self._check_cancelled(job_id)
                    )
                except Exception as e:
                    logger.error(f"Failed to process image {idx + 1}: {e}")
                    with self._job_lock:
                        job = self._jobs.get(job_id, {})
                        job["error"] = f"Image {idx + 1} processing failed: {str(e)}"
                        job["status"] = "failed"
                    return {"success": False, "error": job["error"]}

                # Upload result to R2
                try:
                    result_filename = f"ai_playground_{job_id}_{idx + 1}.png"
                    result_url = await self.r2.upload(
                        data=result_bytes,
                        filename=result_filename,
                        content_type="image/png"
                    )
                except Exception as e:
                    logger.error(f"Failed to upload result {idx + 1}: {e}")
                    with self._job_lock:
                        job = self._jobs.get(job_id, {})
                        job["error"] = f"Image {idx + 1} upload failed: {str(e)}"
                        job["status"] = "failed"
                    return {"success": False, "error": job["error"]}

                # Update job state
                with self._job_lock:
                    job = self._jobs.get(job_id, {})
                    job["result_urls"].append(result_url)
                    job["metadata"].append(metadata)
                    job["processed"] += 1
                    job["progress"] = int((idx + 1) / len(source_urls) * 100)

            # Mark job as completed
            with self._job_lock:
                job = self._jobs.get(job_id, {})
                job["status"] = "completed"
                job["progress"] = 100

            return {
                "success": True,
                "data": {
                    "job_id": job_id,
                    "status": "completed",
                    "result_image_urls": job["result_urls"],
                    "source_image_urls": job["source_urls"],
                    "metadata": job["metadata"],
                }
            }

        except Exception as e:
            logger.error(f"Job {job_id} failed: {e}")
            with self._job_lock:
                job = self._jobs.get(job_id, {})
                job["status"] = "failed"
                job["error"] = str(e)
            return {"success": False, "error": str(e)}

    async def _process_single_image(
        self,
        job_type: str,
        image_bytes: bytes,
        config: Dict[str, Any],
        cancel_check: Optional[callable] = None
    ) -> Tuple[bytes, Dict[str, Any]]:
        """Process a single image based on job type

        Args:
            job_type: Type of processing to apply
            image_bytes: Source image bytes
            config: Processing configuration
            cancel_check: Optional callable to check for cancellation

        Returns:
            Tuple of (result_bytes, metadata)
        """
        if job_type == "background_replacement":
            background_prompt = config.get("backgroundPrompt", "")
            negative_prompt = config.get("negativePrompt", "")
            quality = config.get("quality", "standard")
            temperature = 0.5 if quality == "standard" else 0.3 if quality == "high" else 0.7

            return await self.processor.process_background_replacement(
                image_data=image_bytes,
                background_prompt=background_prompt,
                negative_prompt=negative_prompt,
                temperature=temperature,
                cancel_check=cancel_check
            )

        elif job_type == "batch_optimization":
            quality = config.get("quality", "standard")
            output_format = config.get("format", "webp")
            max_size = config.get("maxSize", 1920)
            maintain_aspect = config.get("maintainAspect", True)

            return await self.processor.process_batch_optimization(
                image_data=image_bytes,
                quality=quality,
                output_format=output_format,
                max_size=max_size,
                maintain_aspect=maintain_aspect,
                cancel_check=cancel_check
            )

        elif job_type == "image_enhancement":
            enhancement_level = config.get("enhancementLevel", 5)
            sharpen = config.get("sharpen", True)
            denoise = config.get("denoise", True)
            upscale = config.get("upscale", False)

            return await self.processor.process_image_enhancement(
                image_data=image_bytes,
                enhancement_level=enhancement_level,
                sharpen=sharpen,
                denoise=denoise,
                upscale=upscale,
                cancel_check=cancel_check
            )

        else:
            raise ValueError(f"Unknown job type: {job_type}")

    def _check_cancelled(self, job_id: str) -> bool:
        """Check if a job has been cancelled

        Args:
            job_id: Job identifier

        Returns:
            True if cancelled, False otherwise
        """
        event = self._cancel_events.get(job_id)
        return event is not None and event.is_set()

    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get the current status of a job

        Args:
            job_id: Job identifier

        Returns:
            Job status dict or None if not found
        """
        with self._job_lock:
            job = self._jobs.get(job_id)
            if not job:
                return None

            return {
                "job_id": job["job_id"],
                "status": job["status"],
                "progress": job["progress"],
                "processed": job["processed"],
                "total": job["total"],
                "message": job.get("error"),
            }

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a running job

        Args:
            job_id: Job identifier

        Returns:
            True if job was cancelled, False otherwise
        """
        with self._job_lock:
            job = self._jobs.get(job_id)
            if not job:
                return False

            if job["status"] in ("processing", "pending"):
                job["status"] = "cancelled"
                event = self._cancel_events.get(job_id)
                if event:
                    event.set()
                return True

            return False

    def validate_input(self, input_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate input data

        Args:
            input_data: Input data dictionary

        Returns:
            Tuple of (is_valid, error_message)
        """
        required_fields = ["job_id", "type", "source_image_urls", "config"]

        for field in required_fields:
            if field not in input_data:
                return False, f"Missing required field: {field}"

        job_type = input_data.get("type")

        if job_type not in ("background_replacement", "batch_optimization", "image_enhancement"):
            return False, f"Invalid job type: {job_type}"

        source_urls = input_data.get("source_image_urls", [])

        if not isinstance(source_urls, list) or not source_urls:
            return False, "source_image_urls must be a non-empty list"

        config = input_data.get("config", {})

        if job_type == "background_replacement":
            if not config.get("backgroundPrompt"):
                return False, "backgroundPrompt is required for background replacement"

        return True, None

    async def health_check(self) -> bool:
        """Health check - verifies API key is configured

        Returns:
            True if plugin is healthy, False otherwise
        """
        return bool(self.config.get("api_key"))
