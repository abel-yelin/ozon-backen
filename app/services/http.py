"""HTTP client connection pool management"""

from typing import Optional
import aiohttp
from aiohttp import ClientSession


class HttpClient:
    """HTTP client connection pool manager"""

    _session: Optional[ClientSession] = None

    @classmethod
    async def get_session(cls) -> ClientSession:
        """Get shared HTTP session"""
        if cls._session is None:
            timeout = aiohttp.ClientTimeout(total=30)
            connector = aiohttp.TCPConnector(
                limit=100,           # Total connections
                limit_per_host=10    # Max connections per host
            )
            cls._session = ClientSession(
                timeout=timeout,
                connector=connector
            )
        return cls._session

    @classmethod
    async def close(cls):
        """Close connection pool"""
        if cls._session:
            await cls._session.close()
            cls._session = None
