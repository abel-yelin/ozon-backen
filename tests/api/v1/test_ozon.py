import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_push_images_requires_api_key():
    """Test that /push-images endpoint requires API key authentication."""
    response = client.post("/api/v1/ozon/push-images", json={
        "credential": {"client_id": "test", "api_key": "test"},
        "product_id": 123456,
        "images": ["https://r2.com/img.jpg"]
    })

    # Should fail without proper auth
    assert response.status_code in [401, 403]

def test_push_images_validates_product_id():
    """Test that product_id must be positive."""
    # This test assumes the API key is handled properly
    # For now, we'll test the validation at the model level
    from pydantic import ValidationError
    from app.api.v1.ozon import PushImagesRequest

    with pytest.raises(ValidationError):
        PushImagesRequest(
            credential={"client_id": "test", "api_key": "test"},
            product_id=-1,
            images=["https://r2.com/img.jpg"]
        )

def test_push_images_validates_array_lengths():
    """Test that array lengths are validated by Pydantic."""
    from pydantic import ValidationError
    from app.api.v1.ozon import PushImagesRequest

    # Test images > 30
    with pytest.raises(ValidationError):
        PushImagesRequest(
            credential={"client_id": "test", "api_key": "test"},
            product_id=123456,
            images=[f"https://r2.com/img{i}.jpg" for i in range(31)]
        )

    # Test images360 > 70
    with pytest.raises(ValidationError):
        PushImagesRequest(
            credential={"client_id": "test", "api_key": "test"},
            product_id=123456,
            images360=[f"https://r2.com/360_{i}.jpg" for i in range(71)]
        )

@pytest.mark.asyncio
async def test_push_images_integration(mocker):
    """Test full integration with mocked Ozon API."""
    from app.api.v1.ozon import push_product_images
    from app.api.v1.ozon import PushImagesRequest

    # Mock the plugin
    mock_plugin = mocker.patch('app.api.v1.ozon.OzonImagePushPlugin')
    mock_instance = mock_plugin.return_value

    # Use AsyncMock for async method
    async def mock_push_images(context):
        return {
            "success": True,
            "data": {
                "product_id": 123456,
                "updated": {"images": 2, "images360": 0, "color_image": False},
                "current_images": ["url1", "url2"]
            }
        }

    mock_instance.push_images = mock_push_images

    request = PushImagesRequest(
        credential={"client_id": "test", "api_key": "test"},
        product_id=123456,
        images=["https://r2.com/img1.jpg", "https://r2.com/img2.jpg"]
    )

    result = await push_product_images(request, authorized=True)

    # Result is a dict
    assert result["success"] == True
    assert result["data"]["product_id"] == 123456
    assert result["data"]["updated"]["images"] == 2
