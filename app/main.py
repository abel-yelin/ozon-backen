"""FastAPI application entry point"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1 import health, image, ozon, ai, image_studio
from app.plugins.plugin_manager import plugin_manager
from app.plugins.image.compress import ImageCompressPlugin
from app.plugins.ozon.download import OzonDownloadPlugin
from app.plugins.ai.playground import AiPlaygroundPlugin
from app.core.config import settings
from app.core.logger import setup_logging

# Setup logging
setup_logging()

# Create FastAPI app
app = FastAPI(
    title="Python Capability Service",
    version="2.1.0",
    description="Stateless processing capabilities - backend only handles heavy lifting"
)

# CORS middleware - use environment-specific origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register plugins
compress_plugin = ImageCompressPlugin(config=settings.plugins_config)
plugin_manager.register(compress_plugin)

ozon_download_plugin = OzonDownloadPlugin(config=settings.plugins_config.get("ozon-download", {}))
plugin_manager.register(ozon_download_plugin)

# Register AI Playground plugin
ai_playground_config = {
    "api_base": settings.plugins_config.get("ai", {}).get("api_base", ""),
    "api_key": settings.plugins_config.get("ai", {}).get("api_key", ""),
    "model": settings.plugins_config.get("ai", {}).get("model", ""),
    "target_width": settings.plugins_config.get("ai", {}).get("target_width", 1500),
    "target_height": settings.plugins_config.get("ai", {}).get("target_height", 2000),
    "default_temperature": settings.plugins_config.get("ai", {}).get("default_temperature", 0.5),
}
ai_playground_plugin = AiPlaygroundPlugin(config=ai_playground_config)
plugin_manager.register(ai_playground_plugin)

# Include routers
app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(image.router, prefix="/api/v1/image", tags=["image"])
app.include_router(ozon.router, prefix="/api/v1", tags=["ozon"])
app.include_router(ai.router, prefix="/api/v1/ai", tags=["ai"])
app.include_router(image_studio.router, prefix="/api/v1", tags=["image-studio"])


# Startup/Shutdown events
@app.on_event("startup")
async def startup():
    """Initialize on application startup"""
    pass


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on application shutdown"""
    pass
