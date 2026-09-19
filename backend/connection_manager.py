"""
connection_manager.py — tracks open WebSocket connections per room.
"""

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.active: dict[str, list[WebSocket]] = {}

    async def connect(self, room_code: str, websocket: WebSocket):
        await websocket.accept()
        self.active.setdefault(room_code, []).append(websocket)

    def disconnect(self, room_code: str, websocket: WebSocket):
        if room_code in self.active:
            if websocket in self.active[room_code]:
                self.active[room_code].remove(websocket)
            if not self.active[room_code]:
                del self.active[room_code]

    async def broadcast(self, room_code: str, message: dict):
        for ws in list(self.active.get(room_code, [])):
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect(room_code, ws)


connection_manager = ConnectionManager()