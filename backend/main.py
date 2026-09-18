"""
main.py — entry point for the Friends Game backend.

Exposes:
  GET  /                             — home page
  GET  /lobby.html                   — lobby page
  GET  /game.html                    — placeholder game page
  GET  /css/*, /js/*                 — static files
  POST /rooms/create                 — create a room
  POST /rooms/join                   — join a room by code
  GET  /rooms/{code}                 — fetch current room state
  WS   /ws/{room_code}/{player_id}   — real-time room channel
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from connection_manager import connection_manager
from models import CreateRoomRequest, JoinRoomRequest
from room_manager import room_manager

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"

app = FastAPI(title="Friends Game API", version="0.5.0")


# ---------- static file serving ----------

app.mount("/css", StaticFiles(directory=FRONTEND_DIR / "css"), name="css")
app.mount("/js", StaticFiles(directory=FRONTEND_DIR / "js"), name="js")


@app.get("/")
def home_page():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/lobby.html")
def lobby_page():
    return FileResponse(FRONTEND_DIR / "lobby.html")


@app.get("/game.html")
def game_page():
    return FileResponse(FRONTEND_DIR / "game.html")


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
    room = room_manager.get_room(code)
    if room is None:
        raise HTTPException(status_code=404, detail=f"Room '{code}' not found.")
    return room


# ---------- WebSocket endpoint ----------

@app.websocket("/ws/{room_code}/{player_id}")
async def websocket_endpoint(websocket: WebSocket, room_code: str, player_id: str):
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

    # Send the new connection the current room state.
    await websocket.send_json(
        {
            "type": "ROOM_STATE",
            "room": room.model_dump(mode="json"),
        }
    )

    # Announce to everyone.
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

            # ---------- SET_READY ----------
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

            # ---------- START_GAME ----------
            elif msg_type == "START_GAME":
                # Server-side validation — never trust the client.
                is_host = player.id == room.host_id
                all_ready = all(p.ready for p in room.players)
                enough_players = len(room.players) >= 2

                if not is_host:
                    await websocket.send_json(
                        {"type": "ERROR", "message": "Only the host can start the game."}
                    )
                    continue

                if not enough_players:
                    await websocket.send_json(
                        {"type": "ERROR", "message": "At least 2 players required."}
                    )
                    continue

                if not all_ready:
                    await websocket.send_json(
                        {"type": "ERROR", "message": "All players must be ready."}
                    )
                    continue

                # Mark the room in-game.
                room.status = "in_game"

                # Broadcast to EVERY player in the room.
                await connection_manager.broadcast(
                    room_code,
                    {
                        "type": "GAME_STARTED",
                        "room_code": room_code,
                        "room": room.model_dump(mode="json"),
                    },
                )

            elif msg_type == "PING":
                await websocket.send_json({"type": "PONG"})

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