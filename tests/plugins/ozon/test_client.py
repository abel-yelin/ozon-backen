import pytest
from app.plugins.ozon.client import OzonClient

@pytest.mark.asyncio
async def test_update_product_pictures_builds_correct_payload(mocker):
    """Test that update_product_pictures builds the correct API payload."""
    client = OzonClient("test_client_id", "test_api_key")

    # Mock the _post method to capture the payload
    mock_post = mocker.patch.object(client, '_post', return_value={"result": "ok"})

    await client.update_product_pictures(
        product_id=123456,
        images=["https://r2.com/img1.jpg", "https://r2.com/img2.jpg"],
        images360=["https://r2.com/360_1.jpg"],
        color_image="https://r2.com/color.jpg"
    )

    # Verify _post was called with correct endpoint and payload
    mock_post.assert_called_once_with("/v1/product/pictures", {
        "product_id": 123456,
        "images": ["https://r2.com/img1.jpg", "https://r2.com/img2.jpg"],
        "images360": ["https://r2.com/360_1.jpg"],
        "color_image": "https://r2.com/color.jpg"
    })

@pytest.mark.asyncio
async def test_update_product_pictures_truncates_arrays(mocker):
    """Test that images array is truncated to 30 and images360 to 70."""
    client = OzonClient("test_client_id", "test_api_key")
    mock_post = mocker.patch.object(client, '_post', return_value={"result": "ok"})

    # Create arrays exceeding limits
    images_40 = [f"https://r2.com/img{i}.jpg" for i in range(40)]
    images360_80 = [f"https://r2.com/360_{i}.jpg" for i in range(80)]

    await client.update_product_pictures(
        product_id=123456,
        images=images_40,
        images360=images360_80
    )

    call_args = mock_post.call_args
    payload = call_args[0][1]

    # Verify truncation
    assert len(payload["images"]) == 30
    assert len(payload["images360"]) == 70
    assert payload["images"] == images_40[:30]
    assert payload["images360"] == images360_80[:70]

@pytest.mark.asyncio
async def test_update_product_pictures_omits_none_values(mocker):
    """Test that None values are not included in the payload."""
    client = OzonClient("test_client_id", "test_api_key")
    mock_post = mocker.patch.object(client, '_post', return_value={"result": "ok"})

    await client.update_product_pictures(
        product_id=123456,
        images=None,
        images360=None,
        color_image=None
    )

    call_args = mock_post.call_args
    payload = call_args[0][1]

    # Only product_id should be in payload
    assert payload == {"product_id": 123456}
    assert "images" not in payload
    assert "images360" not in payload
    assert "color_image" not in payload
