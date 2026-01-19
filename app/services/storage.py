"""Cloudflare R2 storage service"""

import boto3
from botocore.client import Config as BotoConfig
import hashlib
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
        self.s3_client.put_object(
            Bucket=self.bucket_name,
            Key=key,
            Body=data,
            ContentType=content_type
        )

        # Return public URL
        return f"{self.public_url}/{key}"

    async def delete(self, key: str) -> bool:
        """Delete file from R2"""
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=key
            )
            return True
        except Exception:
            return False
