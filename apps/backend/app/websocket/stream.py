from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket client connections and broadcasts."""

    def __init__(self) -> None:
        # channel -> list of websockets
        self._connections: dict[str, list[WebSocket]] = {
            "transactions": [],
            "metrics": [],
        }

    async def connect(self, channel: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.setdefault(channel, []).append(websocket)
        logger.info("WS client connected on channel '%s'", channel)

    def disconnect(self, channel: str, websocket: WebSocket) -> None:
        conns = self._connections.get(channel, [])
        if websocket in conns:
            conns.remove(websocket)
        logger.info("WS client disconnected from channel '%s'", channel)

    async def broadcast(self, channel: str, message: str) -> None:
        """Broadcast a JSON string to all clients on the given channel."""
        dead: list[WebSocket] = []
        for ws in list(self._connections.get(channel, [])):
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(channel, ws)

    def active_connections(self, channel: str) -> int:
        return len(self._connections.get(channel, []))


manager = ConnectionManager()
