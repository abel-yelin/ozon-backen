"""Async utilities for Image Studio optimization."""
from __future__ import annotations

import asyncio
from typing import Optional
from pathlib import Path

import httpx


class AsyncRateLimiter:
    """Rate limiter using asyncio.Semaphore."""

    def __init__(self, max_concurrent: int = 10):
        """
        Initialize rate limiter.

        Args:
            max_concurrent: Maximum number of concurrent operations
        """
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self.max_concurrent = max_concurrent

    async def __aenter__(self):
        """Acquire semaphore slot."""
        await self._semaphore.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Release semaphore slot."""
        self._semaphore.release()


class AsyncFileDownloader:
    """Async file downloader with httpx."""

    def __init__(self, timeout: int = 120, max_retries: int = 2):
        """
        Initialize downloader.

        Args:
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
        """
        self.timeout = timeout
        self.max_retries = max_retries
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._client is None:
            timeout_config = httpx.Timeout(self.timeout, connect=20)
            limits = httpx.Limits(max_keepalive_connections=20, max_connections=50)
            self._client = httpx.AsyncClient(
                timeout=timeout_config,
                limits=limits,
                trust_env=False
            )
        return self._client

    async def download(
        self,
        url: str,
        output_path: Path,
        progress_callback: Optional[callable] = None
    ) -> None:
        """
        Download file from URL to local path.

        Args:
            url: Source URL
            output_path: Destination file path
            progress_callback: Optional callback for progress updates

        Raises:
            httpx.HTTPError: On download failure after retries
        """
        client = await self._get_client()

        for attempt in range(self.max_retries + 1):
            try:
                async with client.stream("GET", url) as response:
                    response.raise_for_status()

                    # Use aiofiles for async write
                    import aiofiles
                    output_path.parent.mkdir(parents=True, exist_ok=True)

                    async with aiofiles.open(output_path, 'wb') as f:
                        async for chunk in response.aiter_bytes(chunk_size=8192):
                            await f.write(chunk)
                            if progress_callback:
                                await progress_callback(len(chunk))

                return

            except httpx.HTTPError as e:
                if attempt < self.max_retries:
                    # Exponential backoff
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None


class AsyncBatchUploader:
    """Batch uploader for R2 storage."""

    def __init__(self, max_concurrent: int = 10):
        """
        Initialize batch uploader.

        Args:
            max_concurrent: Maximum concurrent uploads
        """
        self.rate_limiter = AsyncRateLimiter(max_concurrent)

    async def upload_batch(
        self,
        items: list[dict],
        upload_func: callable
    ) -> list[dict]:
        """
        Upload multiple items concurrently.

        Args:
            items: List of items to upload, each with 'data', 'key', 'format'
            upload_func: Async function to perform single upload

        Returns:
            List of results with URLs and metadata
        """
        async def upload_one(item):
            async with self.rate_limiter:
                return await upload_func(item)

        import asyncio
        results = await asyncio.gather(
            *[upload_one(item) for item in items],
            return_exceptions=True
        )

        # Process results
        uploaded = []
        for item, result in zip(items, results):
            if isinstance(result, Exception):
                uploaded.append({
                    "sku": item.get("sku", ""),
                    "ok": False,
                    "error": str(result)
                })
            else:
                uploaded.append({
                    "sku": item.get("sku", ""),
                    "ok": True,
                    "result_url": result.get("url"),
                    "metadata": result.get("metadata", {})
                })

        return uploaded
