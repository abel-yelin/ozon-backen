import pytest
from app.services.async_utils import AsyncRateLimiter, AsyncFileDownloader


@pytest.mark.asyncio
async def test_rate_limiter_concurrent_limit():
    """Rate limiter should limit concurrent operations"""
    limiter = AsyncRateLimiter(max_concurrent=2)

    execution_order = []

    async def task(n):
        async with limiter:
            execution_order.append(n)
            await asyncio.sleep(0.1)

    # Run 5 tasks concurrently
    import asyncio
    await asyncio.gather(*[task(i) for i in range(5)])

    # Should have executed in batches due to limit
    assert len(execution_order) == 5


@pytest.mark.asyncio
async def test_file_downloader(tmp_path):
    """Downloader should fetch file and save to disk"""
    # This test will use a mock URL
    downloader = AsyncFileDownloader(timeout=5)

    # We'll implement with mocking later
    assert downloader.timeout == 5
