"""Cloudflare R2 storage service"""

import boto3
from botocore.client import Config as BotoConfig
import hashlib
import asyncio
from app.core.config import settings


class R2Service:
    """Cloudflare R2 storage service wrapper"""

    def __init__(self):
        self.s3_client = boto3.client(
            's3',
            endpoint_url=f'https://{settings.r2_account_id}.r2.cloudflarestorage.com',
            aws_access_key_id=settings.r2_access_key_id,
            aws_secret_access_key=settings.r2_secret_access_key,
            config=BotoConfig(signature_version='s3v4'),
            region_name='auto'
        )
        self.bucket_name = settings.r2_bucket_name
        self.public_url = settings.r2_public_url

    async def upload(
        self,
        data: bytes,
        filename: str,
        content_type: str
    ) -> str:
        """Upload file to R2 and return public URL

        Args:
            data: File binary data
            filename: Filename
            content_type: MIME type

        Returns:
            Public access URL
        """
        # Generate unique key
        key = f"uploads/{hashlib.sha256(data).hexdigest()[:16]}_{filename}"

        # Upload
        await self._upload_async(data, key, content_type)

        # Return public URL
        return f"{self.public_url}/{key}"

    async def upload_bytes(self, data: bytes, key: str, content_type: str = "image/jpeg") -> str:
        """
        Upload bytes directly to R2 with custom key (for Ozon plugin).

        Args:
            data: Binary data to upload
            key: R2 storage key (full path)
            content_type: MIME type

        Returns:
            Public URL
        """
        await self._upload_async(data, key, content_type)
        return f"{self.public_url}/{key}"

    def upload_bytes_sync(self, data: bytes, key: str, content_type: str = "image/jpeg") -> str:
        """
        Synchronous version of upload_bytes for use in non-async contexts.

        Args:
            data: Binary data to upload
            key: R2 storage key (full path)
            content_type: MIME type

        Returns:
            Public URL
        """
        self.s3_client.put_object(
            Bucket=self.bucket_name,
            Key=key,
            Body=data,
            ContentType=content_type
        )
        return f"{self.public_url}/{key}"

    async def _upload_async(self, data: bytes, key: str, content_type: str) -> None:
        """Async wrapper for boto3 upload (runs in thread pool)"""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=data,
                ContentType=content_type
            )
        )

    async def delete(self, key: str) -> bool:
        """Delete file from R2"""
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.s3_client.delete_object(
                    Bucket=self.bucket_name,
                    Key=key
                )
            )
            return True
        except Exception:
            return False

    async def exists(self, key: str) -> bool:
        """Check if file exists in R2"""
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.s3_client.head_object(
                    Bucket=self.bucket_name,
                    Key=key
                )
            )
            return True
        except Exception:
            return False

    async def upload_bytes_async(
        self,
        data: bytes,
        key: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        """
        Upload bytes to R2 asynchronously.

        Args:
            data: Bytes to upload
            key: Storage key/path
            content_type: MIME type

        Returns:
            Public URL of uploaded file

        Raises:
            Exception: On upload failure
        """
        await self._upload_async(data, key, content_type)
        return f"{self.public_url}/{key}"

    async def upload_batch_async(
        self,
        items: list[dict],  # Each with 'data', 'key', 'content_type'
        max_concurrent: int = 10
    ) -> list[dict]:
        """
        Upload multiple items concurrently.

        Args:
            items: List of upload items
            max_concurrent: Max concurrent uploads

        Returns:
            List of results with URLs
        """
        from app.services.async_utils import AsyncRateLimiter

        async def upload_one(item):
            return await self.upload_bytes_async(
                data=item["data"],
                key=item["key"],
                content_type=item.get("content_type", "application/octet-stream"),
            )

        rate_limiter = AsyncRateLimiter(max_concurrent)
        async with rate_limiter:
            results = await asyncio.gather(
                *[upload_one(item) for item in items],
                return_exceptions=True
            )

        return [
            {"url": r, "ok": True} if not isinstance(r, Exception)
            else {"ok": False, "error": str(r)}
            for r in results
        ]


# Alias for compatibility with plugin code
R2StorageService = R2Service
