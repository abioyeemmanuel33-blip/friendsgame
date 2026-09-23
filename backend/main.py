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
    POWERUP_CHARS,
    clear_dynamic_tile,
    generate_match_map,
    is_finish_tile,
    is_hazard,
    is_powerup,
    is_walkable,
    list_active_hazards,
    list_active_powerups,
    pick_random_tile,
    put_tile,
    spawn_positions,
)
from models import CreateRoomRequest, JoinRoomRequest
from room_manager import room_manager

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"

app = FastAPI(title="Friends Game API", version="0.12.0")


# ---------- constants ----------

TICK_INTERVAL_SEC = 2.0        # hazard churn
POWERUP_TICK_INTERVAL_SEC = 4.0

TARGET_MIN_HAZARDS = 8
TARGET_MAX_HAZARDS = 12
TARGET_POWERUPS = 3

DEATH_ROLL = 1.0
RESPAWN_DELAY_SEC = 5.0
RESPAWN_TICK_SEC = 0.25

SPEED_DURATION_SEC = 5.0
SHIELD_DURATION_SEC = 10.0
FREEZE_DURATION_SEC = 2.0


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


# ---------- room endpoints ----------

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


# ---------- shared room helpers ----------

def _forbidden_tiles_for_room(room) -> set[tuple[int, int]]:
    """Tiles that must NOT receive a hazard or power-up this tick."""
    forbidden: set[tuple[int, int]] = set()
    for p in room.players:
        forbidden.add((p.row, p.col))
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            forbidden.add((p.row + dr, p.col + dc))
    return forbidden


# ---------- hazard ticker ----------

def _tick_hazards(room) -> bool:
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
            put_tile(room.hazard_map, tile[0], tile[1], ch)
            changed = True

    elif count > TARGET_MAX_HAZARDS:
        tile = random.choice(active)
        clear_dynamic_tile(room.hazard_map, tile[0], tile[1])
        changed = True

    else:
        if random.random() < 0.5:
            tile = random.choice(active)
            clear_dynamic_tile(room.hazard_map, tile[0], tile[1])

            forbidden = _forbidden_tiles_for_room(room)
            new_tile = pick_random_tile(room.hazard_map, forbidden)
            if new_tile is not None:
                ch = random.choice(HAZARD_CHARS)
                put_tile(room.hazard_map, new_tile[0], new_tile[1], ch)
                changed = True

    return changed


async def hazard_ticker():
    while True:
        try:
            for room in room_manager.all_rooms():
                if _tick_hazards(room):
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


# ---------- power-up ticker ----------

def _tick_powerups(room) -> bool:
    if room.hazard_map is None or room.status != "in_game":
        return False

    active = list_active_powerups(room.hazard_map)
    count = len(active)
    changed = False

    if count < TARGET_POWERUPS:
        forbidden = _forbidden_tiles_for_room(room)
        # Also avoid stacking a power-up directly next to a hazard (feels unfair).
        for hr, hc in list_active_hazards(room.hazard_map):
            forbidden.add((hr, hc))
        tile = pick_random_tile(room.hazard_map, forbidden)
        if tile is not None:
            ch = random.choice(POWERUP_CHARS)
            put_tile(room.hazard_map, tile[0], tile[1], ch)
            changed = True

    elif count > TARGET_POWERUPS:
        tile = random.choice(active)
        clear_dynamic_tile(room.hazard_map, tile[0], tile[1])
        changed = True

    else:
        # Occasionally relocate one.
        if random.random() < 0.4:
            tile = random.choice(active)
            clear_dynamic_tile(room.hazard_map, tile[0], tile[1])

            forbidden = _forbidden_tiles_for_room(room)
            for hr, hc in list_active_hazards(room.hazard_map):
                forbidden.add((hr, hc))
            new_tile = pick_random_tile(room.hazard_map, forbidden)
            if new_tile is not None:
                ch = random.choice(POWERUP_CHARS)
                put_tile(room.hazard_map, new_tile[0], new_tile[1], ch)
                changed = True

    return changed


async def powerup_ticker():
    while True:
        try:
            for room in room_manager.all_rooms():
                if _tick_powerups(room):
                    await connection_manager.broadcast(
                        room.code,
                        {
                            "type": "HAZARDS_UPDATED",
                            "hazard_map": room.hazard_map,
                        },
                    )
        except Exception as e:
            print(f"[powerup_ticker] error: {e}")
        await asyncio.sleep(POWERUP_TICK_INTERVAL_SEC)


# ---------- respawn & expiry ticker ----------

async def maintenance_ticker():
    """
    Handles two things every 0.25s:
      1. Respawn players whose dead_until has elapsed.
      2. Clear expired speed / shield / freeze effects and notify clients.
    """
    while True:
        try:
            now = time.time()
            for room in room_manager.all_rooms():
                if room.status != "in_game":
                    continue

                # Respawn check
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

                # Effect expiry check
                for p in room.players:
                    expired = []
                    if p.speed_until is not None and now >= p.speed_until:
                        p.speed_until = None
                        expired.append("speed")
                    if p.shield_until is not None and now >= p.shield_until:
                        p.shield_until = None
                        expired.append("shield")
                    if p.frozen_until is not None and now >= p.frozen_until:
                        p.frozen_until = None
                        expired.append("frozen")
                    if expired:
                        await connection_manager.broadcast(
                            room.code,
                            {
                                "type": "POWERUP_EXPIRED",
                                "player_id": p.id,
                                "effects": expired,
                            },
                        )
        except Exception as e:
            print(f"[maintenance_ticker] error: {e}")
        await asyncio.sleep(RESPAWN_TICK_SEC)


@app.on_event("startup")
async def _start_tickers():
    asyncio.create_task(hazard_ticker())
    asyncio.create_task(powerup_ticker())
    asyncio.create_task(maintenance_ticker())


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
                    p.speed_until = None
                    p.shield_until = None
                    p.frozen_until = None

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
                if player.frozen_until is not None and time.time() < player.frozen_until:
                    # Frozen — silently ignore.
                    continue
                if room.hazard_map is None:
                    continue

                try:
                    drow = int(message.get("drow", 0))
                    dcol = int(message.get("dcol", 0))
                except (TypeError, ValueError):
                    continue

                if abs(drow) + abs(dcol) != 1:
                    continue

                # If speed is active, allow up to 2 steps in this direction.
                steps = 1
                if player.speed_until is not None and time.time() < player.speed_until:
                    steps = 2

                for _ in range(steps):
                    if player.finished_at is not None:
                        break
                    if player.dead_until is not None:
                        break

                    target_row = player.row + drow
                    target_col = player.col + dcol

                    target_ch = None
                    if (0 <= target_row < len(room.hazard_map)
                            and 0 <= target_col < len(room.hazard_map[target_row])):
                        target_ch = room.hazard_map[target_row][target_col]

                    if target_ch is None or target_ch == "#":
                        break

                    occupied = any(
                        other.row == target_row and other.col == target_col
                        for other in room.players
                        if other.id != player.id and other.dead_until is None
                    )
                    if occupied:
                        break

                    # Hazard?
                    if is_hazard(target_ch):
                        clear_dynamic_tile(room.hazard_map, target_row, target_col)

                        # Shield absorbs.
                        if player.shield_until is not None and time.time() < player.shield_until:
                            player.shield_until = None
                            await connection_manager.broadcast(
                                room_code,
                                {
                                    "type": "POWERUP_EXPIRED",
                                    "player_id": player.id,
                                    "effects": ["shield"],
                                },
                            )
                            await connection_manager.broadcast(
                                room_code,
                                {
                                    "type": "HAZARDS_UPDATED",
                                    "hazard_map": room.hazard_map,
                                },
                            )
                            # The shield absorbed the hazard — no death, no move.
                            break

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
                            break
                        else:
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

                    # Power-up?
                    if is_powerup(target_ch):
                        clear_dynamic_tile(room.hazard_map, target_row, target_col)
                        player.row = target_row
                        player.col = target_col

                        now = time.time()
                        effect = None
                        if target_ch == "A":
                            player.speed_until = now + SPEED_DURATION_SEC
                            effect = "speed"
                        elif target_ch == "B":
                            player.shield_until = now + SHIELD_DURATION_SEC
                            effect = "shield"
                        elif target_ch == "C":
                            # Freeze all OTHER players.
                            for other in room.players:
                                if other.id == player.id:
                                    continue
                                if other.finished_at is not None:
                                    continue
                                if other.dead_until is not None:
                                    continue
                                other.frozen_until = now + FREEZE_DURATION_SEC
                            effect = "freeze"

                        await connection_manager.broadcast(
                            room_code,
                            {
                                "type": "POWERUP_GRANTED",
                                "player_id": player.id,
                                "player_name": player.name,
                                "effect": effect,
                                "hazard_map": room.hazard_map,
                                "frozen_others_until": (
                                    now + FREEZE_DURATION_SEC if effect == "freeze" else None
                                ),
                            },
                        )
                        continue

                    # Plain road.
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

                    # Finish check.
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
                        break

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