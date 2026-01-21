"""Ozon API routes - simplified, stateless design

Backend only handles "heavy lifting":
- Ozon API calls
- Image downloading
- R2 uploads

Frontend handles:
- User authentication
- Credential storage
- Task management
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
import logging

from app.api.deps import verify_api_key
from app.plugins.ozon.download import OzonDownloadPlugin
from app.plugins.ozon.image_push import OzonImagePushPlugin
from app.services.storage import R2Service
from app.core.config import settings

router = APIRouter(prefix="/ozon", tags=["ozon"])
logger = logging.getLogger(__name__)

# Initialize plugin and R2 service
ozon_plugin = OzonDownloadPlugin(settings.plugins_config.get("ozon-download", {}))
r2_service = R2Service()


# ==================== Request/Response Models ====================

class OzonCredential(BaseModel):
    """Ozon API credentials (passed from frontend)"""
    client_id: str = Field(..., description="Ozon Client-Id")
    api_key: str = Field(..., description="Ozon Api-Key")


class DownloadRequest(BaseModel):
    """Request model for Ozon download"""
    credential: OzonCredential
    articles: List[str] = Field(..., description="List of article numbers", min_length=1, max_length=100)
    field: Literal["offer_id", "sku", "vendor_code"] = Field("offer_id", description="Search field")
    user_id: str = Field(..., description="User ID from frontend (for R2 path isolation)")


class ImageResult(BaseModel):
    """Result for a single article's images"""
    article: str
    product_id: Optional[int]
    status: "Literal['success', 'failed']"
    total_images: int
    success_images: int
    urls: List[str]
    error: Optional[str] = None


class DownloadResponse(BaseModel):
    """Response model for download result"""
    success: bool
    data: Optional[dict]
    error: Optional[str] = None


class PushImagesRequest(BaseModel):
    """Request model for pushing images to Ozon"""
    credential: OzonCredential
    product_id: int = Field(..., gt=0, description="Ozon Product ID")
    images: Optional[List[str]] = Field(None, max_length=30)
    images360: Optional[List[str]] = Field(None, max_length=70)
    color_image: Optional[str] = None


class PushImagesResponse(BaseModel):
    """Response model for image push"""
    success: bool
    data: Optional[dict] = None
    error: Optional[str] = None
    errors: Optional[List[dict]] = None


# ==================== Routes ====================

@router.post("/download", response_model=DownloadResponse)
async def download_ozon_images(
    request: DownloadRequest,
    authorized: bool = Depends(verify_api_key)
):
    """
    Download Ozon product images directly to R2.

    **Backend responsibilities (heavy lifting):**
    - Call Ozon Seller API
    - Download images
    - Upload to R2

    **Frontend responsibilities:**
    - User authentication
    - Credential storage
    - Task management

    Request:
    ```json
    {
      "credential": {
        "client_id": "xxx",
        "api_key": "xxx"
      },
      "articles": ["123456", "789012"],
      "field": "offer_id",
      "user_id": "user_123"
    }
    ```

    Response:
    ```json
    {
      "success": true,
      "data": {
        "total_articles": 2,
        "processed": 2,
        "total_images": 16,
        "success_images": 15,
        "failed_images": 1,
        "items": [...]
      }
    }
    ```
    """
    try:
        logger.info(f"Processing Ozon download for user={request.user_id}, articles={len(request.articles)}")

        # Process download directly (no database, no async tasks)
        result = await ozon_plugin.process({
            "user_id": request.user_id,
            "credential": {
                "client_id": request.credential.client_id,
                "api_key": request.credential.api_key
            },
            "articles": request.articles,
            "field": request.field,
            "r2_service": r2_service
        })

        success = bool(result.get("success_images"))
        return DownloadResponse(
            success=success,
            data=result,
            error=None if success else "NO_IMAGES_DOWNLOADED"
        )

    except Exception as e:
        logger.error(f"Ozon download failed: {e}")
        return DownloadResponse(
            success=False,
            data=None,
            error=str(e)
        )


@router.get("/health")
async def ozon_health():
    """Check Ozon plugin health"""
    return {
        "status": "healthy",
        "plugin": "ozon-download",
        "version": "1.0.0"
    }


@router.post("/push-images")
async def push_product_images(
    request: PushImagesRequest,
    authorized: bool = Depends(verify_api_key)
):
    """
    Push processed images to Ozon product, replacing existing images.

    **Flow:**
    1. Validate input (URLs, quantities)
    2. Call Ozon API to update pictures
    3. Confirm update by fetching current images
    4. Return summary with updated counts

    **Request:**
    ```json
    {
      "credential": {
        "client_id": "xxx",
        "api_key": "xxx"
      },
      "product_id": 123456,
      "images": ["https://r2.com/img1.jpg", ...],
      "images360": ["https://r2.com/360_1.jpg", ...],
      "color_image": "https://r2.com/color.jpg"
    }
    ```

    **Response (Success):**
    ```json
    {
      "success": true,
      "data": {
        "product_id": 123456,
        "updated": {
          "images": 5,
          "images360": 0,
          "color_image": true
        },
        "current_images": ["url1", "url2", ...]
      }
    }
    ```

    **Response (Validation Error):**
    ```json
    {
      "success": false,
      "errors": [
        {"field": "images", "index": 2, "url": "...", "reason": "Invalid URL format"}
      ]
    }
    ```
    """
    try:
        logger.info(f"Processing Ozon image push for product_id={request.product_id}")

        # Initialize plugin
        plugin = OzonImagePushPlugin({})

        # Process the push
        result = await plugin.push_images({
            "credential": {
                "client_id": request.credential.client_id,
                "api_key": request.credential.api_key
            },
            "product_id": request.product_id,
            "images": request.images or [],
            "images360": request.images360 or [],
            "color_image": request.color_image
        })

        # Ensure success flag is set
        if "success" not in result:
            result["success"] = bool(result.get("data"))

        return result

    except Exception as e:
        logger.error(f"Ozon image push failed: {e}")
        return {
            "success": False,
            "data": None,
            "error": str(e)
        }
