"""
main.py — entry point for the Friends Game backend.

Exposes:
  GET  /                             — home page (static)
  GET  /lobby.html                   — lobby page (static)
  GET  /css/style.css                — stylesheet (static)
  GET  /js/home.js                   — home page logic (static)
  GET  /js/lobby.js                  — lobby page logic (static)
  POST /rooms/create                 — create a room
  POST /rooms/join                   — join a room by code
  GET  /rooms/{code}                 — fetch current state of a room
  WS   /ws/{room_code}/{player_id}   — real-time room channel
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from connection_manager import connection_manager
from models import CreateRoomRequest, JoinRoomRequest
from room_manager import room_manager

# `Path(__file__).parent` is the folder containing this file: backend/.
# Going up one level gives us the project root, which contains frontend/.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"

app = FastAPI(title="Friends Game API", version="0.4.0")


# ---------- static file serving ----------

# Mount the frontend/ folder so its contents are served from the URL root.
# After this line:
#   frontend/css/style.css  is reachable at  /css/style.css
#   frontend/js/home.js     is reachable at  /js/home.js
#   frontend/lobby.html     is reachable at  /lobby.html
#
# html=True means: if a request comes in for "/" and there's no file
# called "index" at that path, look for "index.html".
app.mount("/css", StaticFiles(directory=FRONTEND_DIR / "css"), name="css")
app.mount("/js", StaticFiles(directory=FRONTEND_DIR / "js"), name="js")


@app.get("/")
def home_page():
    """Serve frontend/index.html at the site root."""
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/lobby.html")
def lobby_page():
    """Serve frontend/lobby.html directly."""
    return FileResponse(FRONTEND_DIR / "lobby.html")


# ---------- room endpoints (REST) ----------

@app.post("/rooms/create")
def create_room(request: CreateRoomRequest):
    room = room_manager.create_room(request.host_name)
    return room


@app.post("/rooms/join")
def join_room(request: JoinRoomRequest):
    room = room_manager.join_room(request.room_code, request.player_name)
    if room is None:
        raise HTTPException(
            status_code=404,
            detail=f"Room '{request.room_code}' not found.",
        )
    return room


@app.get("/rooms/{code}")
def get_room(code: str):
    """
    Return the current state of a room, or 404.

    The lobby page calls this once on load, before opening the WebSocket,
    so it can render immediately instead of waiting for the first broadcast.
    """
    room = room_manager.get_room(code)
    if room is None:
        raise HTTPException(status_code=404, detail=f"Room '{code}' not found.")
    return room


# ---------- WebSocket endpoint ----------

@app.websocket("/ws/{room_code}/{player_id}")
async def websocket_endpoint(websocket: WebSocket, room_code: str, player_id: str):
    """
    Real-time channel for one player in one room.

    On connect:
      - validates the room exists and the player is in it
      - announces PLAYER_JOINED to everyone in the room
      - sends the current room state to the newly connected player

    On message (JSON):
      - SET_READY  {ready: bool} — updates the player's ready flag, broadcasts PLAYER_READY

    On disconnect:
      - broadcasts PLAYER_LEFT
    """
    room_code = room_code.upper()
    room = room_manager.get_room(room_code)

    if room is None:
        await websocket.close(code=4004, reason="Room not found")
        return

    player = next((p for p in room.players if p.id == player_id), None)
    if player is None:
        await websocket.close(code=4003, reason="Player not in room")
        return

    await connection_manager.connect(room_code, websocket)

    # The newly connected player needs to know the current state right away.
    await websocket.send_json(
        {
            "type": "ROOM_STATE",
            "room": room.model_dump(mode="json"),
        }
    )

    # Tell everyone else that this player joined the channel.
    await connection_manager.broadcast(
        room_code,
        {
            "type": "PLAYER_JOINED",
            "player_id": player.id,
            "player_name": player.name,
            "room_code": room_code,
        },
    )

    try:
        while True:
            message = await websocket.receive_json()
            msg_type = message.get("type")

            if msg_type == "SET_READY":
                player.ready = bool(message.get("ready", False))
                await connection_manager.broadcast(
                    room_code,
                    {
                        "type": "PLAYER_READY",
                        "player_id": player.id,
                        "ready": player.ready,
                        "room": room.model_dump(mode="json"),
                    },
                )

            elif msg_type == "PING":
                await websocket.send_json({"type": "PONG"})

            # Ignore unknown message types for now.

    except WebSocketDisconnect:
        connection_manager.disconnect(room_code, websocket)
        await connection_manager.broadcast(
            room_code,
            {
                "type": "PLAYER_LEFT",
                "player_id": player.id,
                "player_name": player.name,
                "room_code": room_code,
            },
        )