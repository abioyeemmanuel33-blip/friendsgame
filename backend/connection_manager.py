"""
connection_manager.py — tracks open WebSocket connections per room.

One ConnectionManager instance lives for the whole server.
It maps room_code -> list of WebSocket objects.

Note: this tracks *sockets*, not players. A player might reconnect
and get a new socket; that's fine.
"""

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        # room_code -> list of WebSocket
        self.active: dict[str, list[WebSocket]] = {}

    async def connect(self, room_code: str, websocket: WebSocket):
        """Accept the connection and register it under the room."""
        await websocket.accept()
        self.active.setdefault(room_code, []).append(websocket)

    def disconnect(self, room_code: str, websocket: WebSocket):
        """Remove a socket from the room's list (if present)."""
        if room_code in self.active:
            if websocket in self.active[room_code]:
                self.active[room_code].remove(websocket)
            if not self.active[room_code]:
                del self.active[room_code]

    async def broadcast(self, room_code: str, message: dict):
        """Send the same JSON message to every socket in the room."""
        # Iterate over a copy so we can safely remove dead sockets.
        for ws in list(self.active.get(room_code, [])):
            try:
                await ws.send_json(message)
            except Exception:
                # Socket died between calls — drop it silently.
                self.disconnect(room_code, ws)


connection_manager = ConnectionManager()