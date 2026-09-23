"""
models.py — data shapes for the Friends Game server.
"""

from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, Field


class Player(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str = Field(min_length=1, max_length=20)
    ready: bool = False
    is_host: bool = False
    joined_at: datetime = Field(default_factory=datetime.utcnow)

    row: int = 0
    col: int = 0
    color: str = "#5b7cfa"

    finished_at: float | None = None

    spawn_row: int = 0
    spawn_col: int = 0

    dead_until: float | None = None

    # ---------- power-up state ----------
    # Epoch seconds until each effect expires. None = not active.
    speed_until: float | None = None
    shield_until: float | None = None
    frozen_until: float | None = None


class Room(BaseModel):
    code: str
    host_id: str
    players: list[Player] = Field(default_factory=list)
    status: str = "lobby"
    created_at: datetime = Field(default_factory=datetime.utcnow)

    hazard_map: list[str] | None = None


# ---------- Request / response shapes for the API ----------

class CreateRoomRequest(BaseModel):
    host_name: str = Field(min_length=1, max_length=20)


class JoinRoomRequest(BaseModel):
    room_code: str = Field(min_length=1, max_length=20)
    player_name: str = Field(min_length=1, max_length=20)