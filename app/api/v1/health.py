"""Health check endpoint"""

from fastapi import APIRouter
from app.plugins.plugin_manager import plugin_manager

router = APIRouter()


@router.get("/health")
async def health_check():
    """Health check - returns service status and plugin information"""
    return {
        "status": "healthy",
        "version": "2.0.0",
        "plugins": [
            {
                "name": p.name,
                "display_name": p.display_name,
                "category": p.category,
                "enabled": p.enabled,
                "healthy": await p.health_check()
            }
            for p in plugin_manager.list_plugins()
        ]
    }
