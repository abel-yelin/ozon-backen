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


# Alias for compatibility with plugin code
R2StorageService = R2Service
