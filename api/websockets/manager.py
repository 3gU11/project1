import asyncio
import logging
from typing import List, Any
from fastapi import WebSocket

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.event_loop = None

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.event_loop = asyncio.get_running_loop()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")

    async def send_personal_message(self, message: Any, websocket: WebSocket):
        await websocket.send_json(message)

    async def broadcast(self, message: Any):
        logger.info(f"Broadcasting message: {message} to {len(self.active_connections)} clients")
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning(f"Error sending WebSocket message: {e}")
                self.disconnect(connection)

    def broadcast_from_sync(self, message: Any):
        loop = self.event_loop
        if loop is None or not loop.is_running():
            return
        try:
            if asyncio.get_running_loop() is loop:
                loop.create_task(self.broadcast(message))
                return
        except RuntimeError:
            pass
        loop.call_soon_threadsafe(lambda: loop.create_task(self.broadcast(message)))

manager = ConnectionManager()
