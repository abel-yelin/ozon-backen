"""AI Playground API endpoints

This module provides REST API endpoints for AI Playground operations:
- Submit AI jobs
- Get job status
- Get job results
- Cancel jobs
- Health check
- SSE streaming for real-time progress
"""

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, HttpUrl
from typing import Optional, List, Dict, Any
from app.plugins.plugin_manager import plugin_manager
from app.api.deps import verify_api_key
import time
import asyncio
import json
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================================================
# Request/Response Models
# ============================================================================

class BackgroundReplacementConfig(BaseModel):
    backgroundPrompt: str
    negativePrompt: Optional[str] = ""
    quality: Optional[str] = "standard"
    format: Optional[str] = "png"
    seed: Optional[int] = None


class BatchOptimizationConfig(BaseModel):
    quality: Optional[str] = "standard"
    format: Optional[str] = "webp"
    maxSize: Optional[int] = 1920
    maintainAspect: Optional[bool] = True


class ImageEnhancementConfig(BaseModel):
    enhancementLevel: Optional[int] = 5
    sharpen: Optional[bool] = True
    denoise: Optional[bool] = True
    upscale: Optional[bool] = False


class AiJobRequest(BaseModel):
    job_id: str
    user_id: str
    type: str  # background_replacement, batch_optimization, image_enhancement
    config: Dict[str, Any]
    source_image_urls: List[str]


class AiJobResponse(BaseModel):
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    execution_time_ms: Optional[int] = None


class AiJobProgress(BaseModel):
    job_id: str
    status: str
    progress: int
    processed: int
    total: int
    current_image: Optional[str] = None
    message: Optional[str] = None


class AiJobResult(BaseModel):
    job_id: str
    status: str
    result_image_urls: List[str]
    source_image_urls: List[str]
    processing_time_ms: int
    metadata: List[Dict[str, Any]]


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/job", response_model=AiJobResponse)
async def submit_ai_job(
    request: AiJobRequest,
    authorized: bool = Depends(verify_api_key)
):
    """Submit a new AI processing job

    This endpoint accepts AI job requests and returns immediately.
    Processing happens asynchronously in the background.

    Args:
        request: Job request containing type, config, and source images
        authorized: API key authorization

    Returns:
        Job response with job_id and initial status
    """
    plugin = plugin_manager.get("ai-playground")

    if not plugin:
        raise HTTPException(status_code=501, detail="AI Playground plugin not found")

    if not plugin.enabled:
        raise HTTPException(status_code=503, detail="AI Playground plugin is not enabled")

    # Validate input
    is_valid, error = plugin.validate_input(request.model_dump())
    if not is_valid:
        raise HTTPException(status_code=400, detail=error)

    # Process job (this will run asynchronously)
    start = time.time()

    result = await plugin.process(request.model_dump())

    execution_time = int((time.time() - start) * 1000)

    if result.get("success"):
        return AiJobResponse(
            success=True,
            data=result.get("data"),
            execution_time_ms=execution_time
        )
    else:
        return AiJobResponse(
            success=False,
            error=result.get("error", "Unknown error"),
            execution_time_ms=execution_time
        )


@router.get("/job/{job_id}/status", response_model=AiJobProgress)
async def get_ai_job_status(
    job_id: str,
    authorized: bool = Depends(verify_api_key)
):
    """Get the current status of an AI job

    Args:
        job_id: Job identifier
        authorized: API key authorization

    Returns:
        Current job progress information
    """
    plugin = plugin_manager.get("ai-playground")

    if not plugin:
        raise HTTPException(status_code=501, detail="AI Playground plugin not found")

    status = plugin.get_job_status(job_id)

    if not status:
        raise HTTPException(status_code=404, detail="Job not found")

    return AiJobProgress(**status)


@router.post("/job/{job_id}/cancel")
async def cancel_ai_job(
    job_id: str,
    authorized: bool = Depends(verify_api_key)
):
    """Cancel a running AI job

    Args:
        job_id: Job identifier
        authorized: API key authorization

    Returns:
        Success status
    """
    plugin = plugin_manager.get("ai-playground")

    if not plugin:
        raise HTTPException(status_code=501, detail="AI Playground plugin not found")

    success = plugin.cancel_job(job_id)

    if not success:
        raise HTTPException(status_code=404, detail="Job not found or cannot be cancelled")

    return {"success": True, "message": "Job cancelled"}


# Note: SSE streaming endpoint will be added in a separate task
# For now, job status is polled via GET /job/{job_id}/status


@router.get("/job/{job_id}/stream")
async def stream_ai_job_progress(
    job_id: str,
    authorized: bool = Depends(verify_api_key)
):
    """Stream job progress via Server-Sent Events

    Args:
        job_id: Job identifier
        authorized: API key authorization

    Returns:
        SSE stream with progress updates
    """
    plugin = plugin_manager.get("ai-playground")

    if not plugin:
        raise HTTPException(status_code=501, detail="AI Playground plugin not found")

    async def event_stream():
        """Generator for SSE events"""
        last_status = None
        while True:
            status = plugin.get_job_status(job_id)

            if not status:
                yield f"event: error\ndata: {json.dumps({'error': 'Job not found'})}\n\n"
                break

            # Only send if status changed
            if status != last_status:
                event_type = "progress" if status["status"] == "processing" else status["status"]
                yield f"event: {event_type}\ndata: {json.dumps(status)}\n\n"
                last_status = status.copy()

            # Stop if job is complete or failed
            if status["status"] in ("completed", "failed", "cancelled"):
                break

            await asyncio.sleep(0.5)  # Poll every 500ms

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
