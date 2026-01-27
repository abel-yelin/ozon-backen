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
import asyncio

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
    download_images: bool = Field(True, description="If true, download and upload to R2. If false, only return Ozon URLs")


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


class PresignedUrlRequest(BaseModel):
    """Request model for R2 presigned URL"""
    r2_path: str = Field(..., description="R2 storage path (e.g., users/123/ozon/article/image.jpg)")
    content_type: str = Field("image/jpeg", description="Content type of the file")


class PresignedUrlResponse(BaseModel):
    """Response model for presigned URL"""
    success: bool
    upload_url: Optional[str] = None
    public_url: Optional[str] = None
    error: Optional[str] = None


# ==================== Routes ====================

@router.post("/download", response_model=DownloadResponse)
async def download_ozon_images(
    request: DownloadRequest,
    authorized: bool = Depends(verify_api_key)
):
    """
    Download Ozon product images or get image URLs.

    **Two modes:**

    1. **Download mode (download_images=true, default)**:
       - Backend calls Ozon API
       - Downloads images
       - Uploads to R2
       - Returns R2 URLs

    2. **Metadata mode (download_images=false)**:
       - Backend calls Ozon API
       - Returns original Ozon image URLs
       - Frontend handles download & upload to R2

    **Backend responsibilities:**
    - Call Ozon Seller API
    - Optionally download and upload to R2 (if download_images=true)

    **Frontend responsibilities:**
    - User authentication
    - Credential storage
    - Download & upload to R2 (if download_images=false)

    Request:
    ```json
    {
      "credential": {
        "client_id": "xxx",
        "api_key": "xxx"
      },
      "articles": ["123456", "789012"],
      "field": "offer_id",
      "user_id": "user_123",
      "download_images": false
    }
    ```

    Response (download_images=false):
    ```json
    {
      "success": true,
      "data": {
        "total_articles": 1,
        "processed": 1,
        "total_images": 8,
        "success_images": 8,
        "failed_images": 0,
        "items": [{
          "article": "123456",
          "product_id": 3422867147,
          "status": "success",
          "urls": ["https://cdn1.ozone.ru/...", ...]
        }]
      }
    }
    ```
    """
    try:
        logger.info(f"Processing Ozon download for user={request.user_id}, articles={len(request.articles)}, download_images={request.download_images}")

        # Process download directly (no database, no async tasks)
        result = await ozon_plugin.process({
            "user_id": request.user_id,
            "credential": {
                "client_id": request.credential.client_id,
                "api_key": request.credential.api_key
            },
            "articles": request.articles,
            "field": request.field,
            "r2_service": r2_service,
            "download_images": request.download_images
        })

        success = bool(result.get("success_images"))
        error = None if success else "NO_IMAGES_FOUND"

        # If metadata-only mode, success is based on finding images
        # If download mode, success is based on successful downloads
        if not request.download_images:
            # Metadata mode: success if we found any images
            success = bool(result.get("total_images", 0) > 0)
            error = None if success else "NO_IMAGES_FOUND"

        return DownloadResponse(
            success=success,
            data=result,
            error=error
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


@router.post("/r2/presigned-url", response_model=PresignedUrlResponse)
async def get_r2_presigned_url(
    request: PresignedUrlRequest,
    authorized: bool = Depends(verify_api_key)
):
    """
    Generate R2 presigned URL for direct browser upload.

    **Usage flow:**
    1. Frontend requests presigned URL with desired R2 path
    2. Backend returns upload URL (valid for 1 hour)
    3. Browser uploads directly to R2 using the presigned URL
    4. File is accessible via public_url

    **Request:**
    ```json
    {
      "r2_path": "users/user_123/ozon/article_123/image_1.jpg",
      "content_type": "image/jpeg"
    }
    ```

    **Response:**
    ```json
    {
      "success": true,
      "upload_url": "https://...",
      "public_url": "https://r0.image2url.com/users/.../image_1.jpg"
    }
    ```

    **Frontend upload example:**
    ```javascript
    // 1. Get presigned URL
    const response = await fetch('/api/v1/ozon/r2/presigned-url', {
      method: 'POST',
      body: JSON.stringify({ r2_path: 'users/123/ozon/article/image.jpg' })
    });
    const { upload_url, public_url } = await response.json();

    // 2. Upload directly to R2
    await fetch(upload_url, {
      method: 'PUT',
      body: imageBlob,
      headers: { 'Content-Type': 'image/jpeg' }
    });

    // 3. Use public_url
    console.log('Image available at:', public_url);
    ```
    """
    try:
        logger.info(f"Generating presigned URL for r2_path={request.r2_path}")

        # Generate presigned URL using R2 service
        loop = asyncio.get_event_loop()

        def generate_presigned():
            return r2_service.s3_client.generate_presigned_url(
                'put_object',
                Params={
                    'Bucket': settings.r2_bucket_name,
                    'Key': request.r2_path,
                },
                ExpiresIn=3600,  # 1 hour
                HttpMethod='PUT'
            )

        upload_url = await loop.run_in_executor(None, generate_presigned)
        public_url = f"{settings.r2_public_url}/{request.r2_path}"

        logger.info(f"Generated presigned URL for r2_path={request.r2_path}")

        return PresignedUrlResponse(
            success=True,
            upload_url=upload_url,
            public_url=public_url
        )

    except Exception as e:
        logger.error(f"Failed to generate presigned URL: {e}")
        return PresignedUrlResponse(
            success=False,
            upload_url=None,
            public_url=None,
            error=str(e)
        )
