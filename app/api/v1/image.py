"""Image processing endpoints"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, HttpUrl
from typing import Optional, Dict
from app.plugins.plugin_manager import plugin_manager
from app.api.deps import verify_api_key
import time

router = APIRouter()


class CompressRequest(BaseModel):
    image_url: HttpUrl
    options: Optional[Dict] = {}


class CompressResponse(BaseModel):
    success: bool
    data: Optional[Dict] = None
    error: Optional[str] = None
    execution_time_ms: Optional[int] = None


@router.post("/compress", response_model=CompressResponse)
async def compress_image(
    request: CompressRequest,
    authorized: bool = Depends(verify_api_key)
):
    """Image compression API endpoint"""
    # Get plugin
    plugin = plugin_manager.get("image-compress")
    if not plugin:
        raise HTTPException(status_code=501, detail="Plugin not found")

    # Execute processing
    start = time.time()
    result = await plugin.process({
        "image_url": str(request.image_url),
        "options": request.options
    })
    execution_time = int((time.time() - start) * 1000)
    result["execution_time_ms"] = execution_time

    return result
