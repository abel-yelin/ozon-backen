"""FastAPI application entry point"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1 import health, image, ozon
from app.plugins.plugin_manager import plugin_manager
from app.plugins.image.compress import ImageCompressPlugin
from app.plugins.ozon.download import OzonDownloadPlugin
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

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Configure in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register plugins
compress_plugin = ImageCompressPlugin(config=settings.plugins_config)
plugin_manager.register(compress_plugin)

ozon_download_plugin = OzonDownloadPlugin(config=settings.plugins_config.get("ozon-download", {}))
plugin_manager.register(ozon_download_plugin)

# Include routers
app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(image.router, prefix="/api/v1/image", tags=["image"])
app.include_router(ozon.router, prefix="/api/v1", tags=["ozon"])


# Startup/Shutdown events
@app.on_event("startup")
async def startup():
    """Initialize on application startup"""
    pass


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on application shutdown"""
    pass
