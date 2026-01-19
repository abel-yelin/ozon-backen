"""Tests for image compression plugin"""

import pytest
from app.plugins.image.compress import ImageCompressPlugin


def test_validate_input_success(compress_plugin):
    """Test: Input validation success"""
    input_data = {"image_url": "https://example.com/image.jpg"}
    is_valid, error = compress_plugin.validate_input(input_data)
    assert is_valid is True
    assert error is None


def test_validate_input_missing_url(compress_plugin):
    """Test: Missing image_url parameter"""
    input_data = {}
    is_valid, error = compress_plugin.validate_input(input_data)
    assert is_valid is False
    assert "Missing required parameter" in error


def test_plugin_metadata(compress_plugin):
    """Test: Plugin metadata"""
    assert compress_plugin.name == "image-compress"
    assert compress_plugin.display_name == "图片压缩"
    assert compress_plugin.category == "image"
    assert compress_plugin.processing_mode.value == "sync"


def test_plugin_enabled(compress_plugin):
    """Test: Plugin is enabled by default"""
    assert compress_plugin.enabled is True


@pytest.mark.asyncio
async def test_health_check(compress_plugin):
    """Test: Plugin health check"""
    assert await compress_plugin.health_check() is True
