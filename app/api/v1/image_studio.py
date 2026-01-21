"""Image Studio API endpoints (FastAPI)

Heavy processing only. No database operations here.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, Dict, Any
from app.api.deps import verify_api_key

from app.services.image_studio_queue import JobQueue
from app.services.image_studio_worker import run_image_studio_job

router = APIRouter()

IMAGE_STUDIO_QUEUE = JobQueue(lanes=["image"], lane_workers={"image": 2}, log_dir="job_logs/image_studio")
IMAGE_STUDIO_QUEUE.start()


class ImageStudioJobRequest(BaseModel):
  job_id: str
  user_id: str
  mode: str
  sku: str
  stem: Optional[str] = None
  options: Dict[str, Any] = {}


@router.post("/image-studio/jobs")
async def submit_job(
  request: ImageStudioJobRequest,
  authorized: bool = Depends(verify_api_key),
):
  try:
    job_id = IMAGE_STUDIO_QUEUE.enqueue(
      mode=request.mode,
      sku=request.sku,
      stem=request.stem,
      options=request.options,
      runner=lambda: run_image_studio_job(request.model_dump()),
      prompt=None,
      lane="image",
      job_id=request.job_id,
    )
    return {"success": True, "data": {"job_id": job_id}}
  except Exception as e:
    return {"success": False, "error": str(e)}


@router.get("/image-studio/jobs/{job_id}/status")
async def get_job_status(
  job_id: str,
  authorized: bool = Depends(verify_api_key),
):
  job = IMAGE_STUDIO_QUEUE.get(job_id)
  if not job:
    raise HTTPException(status_code=404, detail="Job not found")
  return {
    "job_id": job_id,
    "status": job.get("status"),
    "error": job.get("error"),
    "result": job.get("result"),
  }


@router.post("/image-studio/jobs/{job_id}/cancel")
async def cancel_job(
  job_id: str,
  authorized: bool = Depends(verify_api_key),
):
  ok, status = IMAGE_STUDIO_QUEUE.cancel(job_id)
  if not ok:
    raise HTTPException(status_code=404, detail="Job not found")
  return {"success": True, "status": status}


@router.get("/image-studio/jobs/{job_id}/logs")
async def get_job_logs(
  job_id: str,
  from_bytes: Optional[int] = None,
  tail: Optional[int] = None,
  full: Optional[bool] = False,
  authorized: bool = Depends(verify_api_key),
):
  if full:
    from_bytes = 0
  info = IMAGE_STUDIO_QUEUE.get_log_chunk(
    job_id,
    from_bytes=from_bytes,
    tail_bytes=None if full else tail,
  )
  if info is None:
    raise HTTPException(status_code=404, detail="Job not found")
  return info
