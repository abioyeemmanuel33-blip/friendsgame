"""
main.py — entry point for the Friends Game backend.
"""

import asyncio
import random
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from connection_manager import connection_manager
from maps import (
    HAZARD_CHARS,
    clear_hazard,
    generate_match_map,
    is_finish_tile,
    is_hazard,
    is_walkable,
    list_active_hazards,
    pick_random_tile,
    put_hazard,
    spawn_positions,
)
from models import CreateRoomRequest, JoinRoomRequest
from room_manager import room_manager

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"

app = FastAPI(title="Friends Game API", version="0.11.1")


# ---------- constants ----------

TICK_INTERVAL_SEC = 2.0       # hazard churn interval
TARGET_MIN_HAZARDS = 8
TARGET_MAX_HAZARDS = 12

DEATH_ROLL = 1.0              # 1.0 = always die on hazard contact
RESPAWN_DELAY_SEC = 5.0
RESPAWN_TICK_SEC = 0.25


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
    return room_manager.create_room(request.host_name)


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


# ---------- hazard ticker ----------

def _forbidden_tiles_for_room(room) -> set[tuple[int, int]]:
    forbidden: set[tuple[int, int]] = set()
    for p in room.players:
        forbidden.add((p.row, p.col))
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            forbidden.add((p.row + dr, p.col + dc))
    return forbidden


def _tick_one_room(room) -> bool:
    if room.hazard_map is None or room.status != "in_game":
        return False

    active = list_active_hazards(room.hazard_map)
    count = len(active)
    changed = False

    if count < TARGET_MIN_HAZARDS:
        forbidden = _forbidden_tiles_for_room(room)
        tile = pick_random_tile(room.hazard_map, forbidden)
        if tile is not None:
            ch = random.choice(HAZARD_CHARS)
            put_hazard(room.hazard_map, tile[0], tile[1], ch)
            changed = True

    elif count > TARGET_MAX_HAZARDS:
        tile = random.choice(active)
        clear_hazard(room.hazard_map, tile[0], tile[1])
        changed = True

    else:
        if random.random() < 0.5:
            tile = random.choice(active)
            clear_hazard(room.hazard_map, tile[0], tile[1])

            forbidden = _forbidden_tiles_for_room(room)
            new_tile = pick_random_tile(room.hazard_map, forbidden)
            if new_tile is not None:
                ch = random.choice(HAZARD_CHARS)
                put_hazard(room.hazard_map, new_tile[0], new_tile[1], ch)
                changed = True

    return changed


async def hazard_ticker():
    while True:
        try:
            for room in room_manager.all_rooms():
                if _tick_one_room(room):
                    await connection_manager.broadcast(
                        room.code,
                        {
                            "type": "HAZARDS_UPDATED",
                            "hazard_map": room.hazard_map,
                        },
                    )
        except Exception as e:
            print(f"[hazard_ticker] error: {e}")
        await asyncio.sleep(TICK_INTERVAL_SEC)


# ---------- respawn ticker ----------

async def respawn_ticker():
    while True:
        try:
            now = time.time()
            for room in room_manager.all_rooms():
                if room.status != "in_game":
                    continue

                for p in room.players:
                    if p.dead_until is None:
                        continue
                    if now < p.dead_until:
                        continue

                    p.row = p.spawn_row
                    p.col = p.spawn_col
                    p.dead_until = None

                    await connection_manager.broadcast(
                        room.code,
                        {
                            "type": "PLAYER_RESPAWNED",
                            "player_id": p.id,
                            "row": p.row,
                            "col": p.col,
                        },
                    )
        except Exception as e:
            print(f"[respawn_ticker] error: {e}")
        await asyncio.sleep(RESPAWN_TICK_SEC)


@app.on_event("startup")
async def _start_tickers():
    asyncio.create_task(hazard_ticker())
    asyncio.create_task(respawn_ticker())


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

    await websocket.send_json(
        {
            "type": "ROOM_STATE",
            "room": room.model_dump(mode="json"),
        }
    )

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

                room.hazard_map = generate_match_map()

                spawns = spawn_positions()
                for i, p in enumerate(room.players):
                    r, c = spawns[i % len(spawns)]
                    p.row = r
                    p.col = c
                    p.spawn_row = r
                    p.spawn_col = c
                    p.finished_at = None
                    p.dead_until = None

                room.status = "in_game"

                await connection_manager.broadcast(
                    room_code,
                    {
                        "type": "GAME_STARTED",
                        "room_code": room_code,
                        "room": room.model_dump(mode="json"),
                    },
                )

            # ---------- MOVE ----------
            elif msg_type == "MOVE":
                if player.finished_at is not None:
                    continue
                if player.dead_until is not None:
                    continue
                if room.hazard_map is None:
                    continue

                try:
                    drow = int(message.get("drow", 0))
                    dcol = int(message.get("dcol", 0))
                except (TypeError, ValueError):
                    await websocket.send_json(
                        {"type": "ERROR", "message": "Invalid move payload."}
                    )
                    continue

                if abs(drow) + abs(dcol) != 1:
                    await websocket.send_json(
                        {"type": "ERROR", "message": "Move must be exactly one tile."}
                    )
                    continue

                target_row = player.row + drow
                target_col = player.col + dcol

                target_ch = None
                if (0 <= target_row < len(room.hazard_map)
                        and 0 <= target_col < len(room.hazard_map[target_row])):
                    target_ch = room.hazard_map[target_row][target_col]

                # Walls and out-of-bounds always block.
                if target_ch is None or target_ch == "#":
                    continue

                # Cannot move onto a tile another living player is standing on.
                occupied = any(
                    other.row == target_row and other.col == target_col
                    for other in room.players
                    if other.id != player.id and other.dead_until is None
                )
                if occupied:
                    continue

                # Hazard tile? Roll for death (100% now).
                if is_hazard(target_ch):
                    clear_hazard(room.hazard_map, target_row, target_col)

                    if random.random() < DEATH_ROLL:
                        player.dead_until = time.time() + RESPAWN_DELAY_SEC

                        await connection_manager.broadcast(
                            room_code,
                            {
                                "type": "PLAYER_DIED",
                                "player_id": player.id,
                                "player_name": player.name,
                                "dead_until": player.dead_until,
                                "hazard_map": room.hazard_map,
                            },
                        )
                        continue

                    else:
                        # Survived — move through the now-cleared tile.
                        player.row = target_row
                        player.col = target_col

                        await connection_manager.broadcast(
                            room_code,
                            {
                                "type": "PLAYER_MOVED",
                                "player_id": player.id,
                                "row": player.row,
                                "col": player.col,
                                "hazard_map": room.hazard_map,
                            },
                        )
                        continue

                # Plain road — move as normal.
                player.row = target_row
                player.col = target_col

                await connection_manager.broadcast(
                    room_code,
                    {
                        "type": "PLAYER_MOVED",
                        "player_id": player.id,
                        "row": player.row,
                        "col": player.col,
                    },
                )

                # ---------- Safety net ----------
                # Did we land on a hazard that spawned in the same tick?
                landed_ch = room.hazard_map[player.row][player.col]
                if is_hazard(landed_ch):
                    clear_hazard(room.hazard_map, player.row, player.col)

                    if random.random() < DEATH_ROLL:
                        player.dead_until = time.time() + RESPAWN_DELAY_SEC

                        await connection_manager.broadcast(
                            room_code,
                            {
                                "type": "PLAYER_DIED",
                                "player_id": player.id,
                                "player_name": player.name,
                                "dead_until": player.dead_until,
                                "hazard_map": room.hazard_map,
                            },
                        )
                        continue

                # ---------- Finish check ----------
                if is_finish_tile(room.hazard_map, player.row, player.col) and player.finished_at is None:
                    player.finished_at = time.time()

                    await connection_manager.broadcast(
                        room_code,
                        {
                            "type": "PLAYER_FINISHED",
                            "player_id": player.id,
                            "player_name": player.name,
                            "finished_at": player.finished_at,
                        },
                    )

                    all_done = all(p.finished_at is not None for p in room.players)
                    if all_done:
                        room.status = "finished"
                        rankings = sorted(
                            room.players, key=lambda p: p.finished_at or 0
                        )
                        await connection_manager.broadcast(
                            room_code,
                            {
                                "type": "GAME_ENDED",
                                "rankings": [
                                    {
                                        "player_id": p.id,
                                        "player_name": p.name,
                                        "color": p.color,
                                        "finished_at": p.finished_at,
                                    }
                                    for p in rankings
                                ],
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