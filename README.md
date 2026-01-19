# Python Capability Service

**Phase 1: Foundation** - Stateless processing capabilities for image2url

## Overview

This is a stateless Python capability service that provides image processing, video processing, document handling, and AI capabilities to Next.js frontends. The service follows a **plugin-based architecture** where each capability is implemented as an independent plugin.

**Architecture Principles:**
- 🔒 **Stateless**: No business data storage
- 🔌 **Plugin-based**: All capabilities are plugins
- 🚀 **Async-first**: Built on FastAPI with async/await
- 🎯 **Simple**: YAGNI principle - only what's needed

## Phase 1 Features

✅ FastAPI application with plugin architecture
✅ Image compression plugin (sync processing)
✅ R2 storage integration (Cloudflare)
✅ API key authentication
✅ Health check endpoint
✅ Docker containerization
✅ Basic test framework

## Project Structure

```
dev/back-end/
├── app/
│   ├── api/                    # API routes
│   │   ├── deps.py             # Authentication
│   │   └── v1/
│   │       ├── health.py       # Health check
│   │       └── image.py        # Image compression API
│   ├── core/                   # Core infrastructure
│   │   ├── config.py           # Configuration
│   │   ├── logger.py           # Logging
│   │   └── security.py         # Security utilities
│   ├── plugins/                # Plugin system
│   │   ├── base.py             # BasePlugin class
│   │   ├── plugin_manager.py   # Plugin manager
│   │   └── image/
│   │       └── compress.py     # Image compression plugin
│   ├── services/               # External services
│   │   ├── storage.py          # R2 storage
│   │   └── http.py             # HTTP client pool
│   └── main.py                 # FastAPI app entry
├── config/
│   └── plugins.yaml            # Plugin configuration
├── tests/                      # Tests
│   ├── conftest.py
│   └── test_compress.py
├── .env.example                # Environment template
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── pyproject.toml
```

## Quick Start

### Prerequisites

- Python 3.11+
- Docker (optional, for containerized deployment)
- Cloudflare R2 account with credentials

### Local Development

1. **Install dependencies:**
   ```bash
   cd dev/back-end
   pip install -r requirements.txt
   ```

2. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your R2 credentials
   ```

3. **Run the service:**
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

### Docker Deployment

1. **Build and run with docker-compose:**
   ```bash
   cd dev/back-end
   docker-compose up --build
   ```

2. **Service will be available at:**
   - API: http://localhost:8000
   - Health: http://localhost:8000/api/v1/health
   - Docs: http://localhost:8000/docs

## API Usage

### Health Check

```bash
curl http://localhost:8000/api/v1/health
```

Response:
```json
{
  "status": "healthy",
  "version": "2.0.0",
  "plugins": [
    {
      "name": "image-compress",
      "display_name": "图片压缩",
      "category": "image",
      "enabled": true,
      "healthy": true
    }
  ]
}
```

### Image Compression

```bash
curl -X POST "http://localhost:8000/api/v1/image/compress" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-secret-key" \
  -d '{
    "image_url": "https://example.com/image.jpg",
    "options": {
      "quality": 80,
      "format": "webp",
      "max_width": 1920,
      "max_height": 1080
    }
  }'
```

Response:
```json
{
  "success": true,
  "data": {
    "output_url": "https://r2.example.com/uploads/a1b2c3d4e5f6g7h8_compressed.webp",
    "metadata": {
      "original_size": 5242880,
      "compressed_size": 1048576,
      "compression_ratio": 0.8,
      "width": 1920,
      "height": 1080,
      "format": "webp"
    }
  },
  "execution_time_ms": 1234
}
```

## Plugin System

### Creating a New Plugin

1. **Inherit from BasePlugin:**
   ```python
   from app.plugins.base import BasePlugin, ProcessingMode

   class MyPlugin(BasePlugin):
       name = "my-plugin"
       display_name = "My Plugin"
       category = "image"
       processing_mode = ProcessingMode.SYNC

       async def process(self, input_data: dict) -> dict:
           # Implementation
           pass

       def validate_input(self, input_data: dict) -> tuple[bool, str | None]:
           # Validation
           pass
   ```

2. **Register in main.py:**
   ```python
   from app.plugins.my_plugin import MyPlugin
   my_plugin = MyPlugin(config=settings.plugins_config)
   plugin_manager.register(my_plugin)
   ```

3. **Create API endpoint:**
   ```python
   @router.post("/my-endpoint")
   async def my_endpoint(request: Request, authorized: bool = Depends(verify_api_key)):
       plugin = plugin_manager.get("my-plugin")
       result = await plugin.process(...)
       return result
   ```

## Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `R2_ACCOUNT_ID` | Cloudflare R2 account ID | Yes |
| `R2_ACCESS_KEY_ID` | R2 access key | Yes |
| `R2_SECRET_ACCESS_KEY` | R2 secret key | Yes |
| `R2_BUCKET_NAME` | R2 bucket name | Yes |
| `R2_PUBLIC_URL` | R2 public URL | Yes |
| `PYTHON_SERVICE_API_KEY` | API authentication key | Yes |

### Plugin Configuration

Edit `config/plugins.yaml`:

```yaml
plugins:
  image-compress:
    enabled: true
    max_file_size: 52428800  # 50MB
    supported_formats: ["jpg", "jpeg", "png", "webp"]
```

## Testing

Run tests:

```bash
cd dev/back-end
pytest
```

Run with coverage:

```bash
pytest --cov=app tests/
```

## Deployment

### Production Considerations

1. **Security:**
   - Change default API key
   - Configure CORS origins
   - Use HTTPS

2. **Performance:**
   - Use gunicorn with uvicorn workers
   - Enable Redis for caching (Phase 2)
   - Configure connection pooling

3. **Monitoring:**
   - Add structured logging
   - Implement Prometheus metrics (Phase 2)
   - Set up health check monitoring

## Roadmap

### Phase 1 ✅ (Current)
- Foundation and plugin system
- Image compression plugin
- Basic APIs and tests

### Phase 2 (Next)
- Multiple plugins (5-10)
- Async task system (Celery + Redis)
- Advanced error handling
- Response caching

### Phase 2 Plugins
- Image: resize, remove-background, nsfw-check, ocr
- Video: transcode, compress, screenshot
- Document: pdf-to-images, pdf-to-text
- AI: embedding, classify

## Architecture Benefits

✅ **Business Autonomy**: Each site controls its own data
✅ **Capability Reuse**: Multiple sites share Python capabilities
✅ **Simple Scaling**: Independent scaling of Python service
✅ **Clear Decoupling**: Python doesn't care about business logic
✅ **Easy Extension**: New capabilities = new plugins
✅ **Fault Isolation**: Python failure doesn't affect site logic

## License

MIT

## Authors

- Abel
- Claude (AI Assistant)

---

**Version**: 2.0.0 (Phase 1)
**Status**: Foundation Complete
**Last Updated**: 2026-01-17
