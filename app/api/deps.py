"""API dependencies - authentication and other shared dependencies"""

from fastapi import Header, HTTPException
from app.core.config import settings


async def verify_api_key(x_api_key: str = Header(...)):
    """Verify API Key"""
    if x_api_key != settings.python_service_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True
