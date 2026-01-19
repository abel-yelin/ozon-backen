"""Pytest configuration and fixtures"""

import pytest
from app.plugins.image.compress import ImageCompressPlugin


@pytest.fixture
def compress_plugin():
    """Create plugin instance for testing"""
    config = {"max_file_size": 52428800}
    return ImageCompressPlugin(config)
