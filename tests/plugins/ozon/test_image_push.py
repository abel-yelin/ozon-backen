import pytest
from app.plugins.ozon.image_push import OzonImagePushPlugin

@pytest.mark.asyncio
async def test_validate_rejects_invalid_url_format():
    """Test that validation catches URLs not starting with http/https."""
    plugin = OzonImagePushPlugin({})

    context = {
        "product_id": 123456,
        "images": ["https://valid.com/img.jpg", "invalid-url", "ftp://bad.com/img.jpg"],
        "images360": [],
        "color_image": None
    }

    result = plugin._validate(context)

    assert len(result["errors"]) == 2
    assert result["errors"][0] == {
        "field": "images",
        "index": 1,
        "url": "invalid-url",
        "reason": "Invalid URL format"
    }
    assert result["errors"][1] == {
        "field": "images",
        "index": 2,
        "url": "ftp://bad.com/img.jpg",
        "reason": "Invalid URL format"
    }

@pytest.mark.asyncio
async def test_validate_rejects_exceeded_limits():
    """Test that validation catches array size exceeding limits."""
    plugin = OzonImagePushPlugin({})

    # Create arrays exceeding limits
    images_35 = [f"https://r2.com/img{i}.jpg" for i in range(35)]
    images360_75 = [f"https://r2.com/360_{i}.jpg" for i in range(75)]

    context = {
        "product_id": 123456,
        "images": images_35,
        "images360": images360_75,
        "color_image": None
    }

    result = plugin._validate(context)

    assert len(result["errors"]) == 2
    error_fields = {e["field"] for e in result["errors"]}
    assert "images" in error_fields
    assert "images360" in error_fields

@pytest.mark.asyncio
async def test_validate_passes_with_valid_input():
    """Test that validation passes with correct input."""
    plugin = OzonImagePushPlugin({})

    context = {
        "product_id": 123456,
        "images": ["https://r2.com/img1.jpg", "https://r2.com/img2.jpg"],
        "images360": ["https://r2.com/360_1.jpg"],
        "color_image": "https://r2.com/color.jpg"
    }

    result = plugin._validate(context)

    assert result["errors"] == []

@pytest.mark.asyncio
async def test_build_response():
    """Test response building logic."""
    plugin = OzonImagePushPlugin({})

    update_result = {"result": "ok"}
    current_urls = ["https://r2.com/img1.jpg", "https://r2.com/img2.jpg"]
    context = {
        "product_id": 123456,
        "images": ["url1", "url2", "url3"],
        "images360": ["360_1"],
        "color_image": "color_url"
    }

    result = plugin._build_response(update_result, current_urls, context)

    assert result["success"] == True
    assert result["data"]["product_id"] == 123456
    assert result["data"]["updated"]["images"] == 3
    assert result["data"]["updated"]["images360"] == 1
    assert result["data"]["updated"]["color_image"] == True
    assert result["data"]["current_images"] == current_urls
