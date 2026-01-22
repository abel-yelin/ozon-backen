"""Integration tests for batch workflow."""
import pytest


@pytest.mark.asyncio
async def test_batch_generation_workflow():
    """Test complete batch generation workflow with async processing.

    This test validates:
    - Job submission
    - Async batch processing
    - Progress tracking
    - Result retrieval
    """
    # This is a placeholder for integration test
    # Full implementation would require:
    # - Test fixtures for AI API mocking
    # - Test image sources
    # - R2 storage mocking
    # - WebSocket client for progress

    # For now, just verify the module structure
    from app.services.image_studio_engine import process_batch_main_async
    from app.services.image_studio_worker import run_image_studio_job
    from app.api.v1.ws_progress import progress_manager

    assert callable(process_batch_main_async)
    assert callable(run_image_studio_job)
    assert progress_manager is not None


def test_websocket_endpoint_exists():
    """Test that WebSocket endpoint is registered."""
    from app.main import app

    routes = [route.path for route in app.routes]
    ws_route = next((r for r in routes if "ws/progress" in r), None)

    assert ws_route is not None, "WebSocket progress endpoint should be registered"


def test_async_utils_export():
    """Test that async utilities are exported correctly."""
    from app.services.async_utils import (
        AsyncRateLimiter,
        AsyncFileDownloader,
        AsyncBatchUploader,
        download_image_batch,
    )

    assert AsyncRateLimiter is not None
    assert AsyncFileDownloader is not None
    assert AsyncBatchUploader is not None
    assert callable(download_image_batch)


def test_r2_async_methods():
    """Test that R2Service has async methods."""
    from app.services.storage import R2Service
    import inspect

    r2 = R2Service()

    # Check async methods exist
    assert hasattr(r2, "upload_bytes_async")
    assert hasattr(r2, "upload_batch_async")

    # Verify they are async
    assert inspect.iscoroutinefunction(r2.upload_bytes_async)
    assert inspect.iscoroutinefunction(r2.upload_batch_async)


@pytest.mark.asyncio
async def test_rate_limiter_basic():
    """Test AsyncRateLimiter basic functionality."""
    from app.services.async_utils import AsyncRateLimiter
    import asyncio

    limiter = AsyncRateLimiter(max_concurrent=2)

    execution_order = []
    completed = 0

    async def task(n):
        nonlocal completed
        async with limiter:
            execution_order.append(n)
            await asyncio.sleep(0.05)
            completed += 1

    # Run 5 tasks
    await asyncio.gather(*[task(i) for i in range(5)])

    # All should complete
    assert completed == 5
    assert len(execution_order) == 5


@pytest.mark.asyncio
async def test_file_downloader_init():
    """Test AsyncFileDownloader initialization."""
    from app.services.async_utils import AsyncFileDownloader

    downloader = AsyncFileDownloader(timeout=30, max_retries=3)

    assert downloader.timeout == 30
    assert downloader.max_retries == 3
    assert downloader._client is None


def test_image_studio_engine_async_functions():
    """Test that async functions exist in image_studio_engine."""
    from app.services.image_studio_engine import (
        _process_sku_main_async,
        process_batch_main_async,
        encode_image_for_model,
    )
    import inspect

    # Check functions exist
    assert callable(_process_sku_main_async)
    assert callable(process_batch_main_async)
    assert callable(encode_image_for_model)

    # Verify async functions are async
    assert inspect.iscoroutinefunction(_process_sku_main_async)
    assert inspect.iscoroutinefunction(process_batch_main_async)


def test_webp_encoding_in_encode_image():
    """Test that encode_image_for_model uses WebP."""
    from app.services.image_studio_engine import encode_image_for_model
    from PIL import Image
    import re

    # Create a test image
    img = Image.new('RGB', (100, 100), color='red')

    # Encode
    b64 = encode_image_for_model(img, max_long_side=800)

    # Should be base64
    assert isinstance(b64, str)
    assert len(b64) > 0

    # Should be valid base64
    import base64
    decoded = base64.b64decode(b64)

    # Should be WebP format (RIFF....WEBP)
    assert decoded[:4] == b"RIFF"
    assert b"WEBP" in decoded[:12]
