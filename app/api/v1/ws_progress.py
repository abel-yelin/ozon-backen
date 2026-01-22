"""WebSocket progress tracking for Image Studio."""
from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict
import asyncio
import json

router = APIRouter()


class ProgressManager:
    """Manage WebSocket connections for progress updates."""

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, job_id: str, websocket: WebSocket):
        """Connect a WebSocket client."""
        await websocket.accept()
        self.active_connections[job_id] = websocket

    def disconnect(self, job_id: str):
        """Disconnect a WebSocket client."""
        if job_id in self.active_connections:
            del self.active_connections[job_id]

    async def send_progress(self, job_id: str, progress: dict):
        """Send progress update to client."""
        if job_id in self.active_connections:
            try:
                await self.active_connections[job_id].send_json(progress)
            except Exception:
                self.disconnect(job_id)

    async def broadcast(self, progress: dict):
        """Broadcast progress to all connected clients."""
        disconnected = []
        for job_id, websocket in self.active_connections.items():
            try:
                await websocket.send_json(progress)
            except Exception:
                disconnected.append(job_id)

        for job_id in disconnected:
            self.disconnect(job_id)


# Global progress manager
progress_manager = ProgressManager()


@router.websocket("/ws/progress/{job_id}")
async def progress_websocket(websocket: WebSocket, job_id: str):
    """WebSocket endpoint for real-time progress updates.

    Connect to this endpoint to receive real-time progress updates for a job:
    ws://localhost:8000/api/v1/ws/progress/{job_id}

    Progress messages format:
    {
        "type": "progress" | "complete" | "error" | "ping",
        "stage": "main" | "secondary",
        "current": 1,
        "total": 10,
        "sku": "SKU123",
        "percentage": 10.0,
        "message": "Processing SKU123"
    }
    """
    await progress_manager.connect(job_id, websocket)

    try:
        while True:
            # Keep connection alive with ping
            await asyncio.sleep(10)
            try:
                await websocket.send_json({"type": "ping"})
            except Exception:
                break
    except WebSocketDisconnect:
        progress_manager.disconnect(job_id)
    except Exception:
        progress_manager.disconnect(job_id)
