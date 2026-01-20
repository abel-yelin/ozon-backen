"""API dependencies - authentication and other shared dependencies"""

from typing import Optional
from fastapi import Header, HTTPException, Query
from app.core.config import settings


async def verify_api_key(
    x_api_key: Optional[str] = Header(default=None),
    api_key: Optional[str] = Query(default=None)
):
    """Verify API Key from header or query string"""
    provided_key = x_api_key or api_key
    if not provided_key or provided_key != settings.python_service_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True
