"""
models.py — data shapes for the Friends Game server.

This file defines what a Player and a Room *look like* in our system.
We use Pydantic (bundled with FastAPI) because it gives us:
  - automatic validation (wrong types raise errors)
  - automatic JSON conversion when sending data to clients

Nothing in this file has any behavior yet — no "create room" logic,
no "join room" logic. It only describes *shape*.
"""

from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, Field


class Player(BaseModel):
    """
    A single player inside a room.

    Fields:
      id         — a unique internal ID (never shown to users)
      name       — the display name the player typed
      ready      — has the player pressed "ready"?
      is_host    — is this player the room's host?
      joined_at  — when they joined (useful for sorting / debugging)
    """

    # `default_factory=uuid4` means: "when creating a Player without
    # specifying an id, call uuid4() to generate a fresh one."
    # We use a lambda-free form so Pydantic calls the function each time.
    id: str = Field(default_factory=lambda: str(uuid4()))

    # The display name. Minimum 1 character, max 20.
    name: str = Field(min_length=1, max_length=20)

    # Ready flag defaults to False.
    ready: bool = False

    # Only one player per room has this True.
    is_host: bool = False

    # Automatically set to the moment the Player is created.
    joined_at: datetime = Field(default_factory=datetime.utcnow)


class Room(BaseModel):
    """
    A private game room identified by a short code, e.g. "FRD-7284".

    Fields:
      code       — the short code that players type to join
      host_id    — the player id of the host
      players    — a list of all players currently in the room
      status     — "lobby", "in_game", or "finished" (more later)
      created_at — when the room was created
    """

    code: str
    host_id: str
    players: list[Player] = Field(default_factory=list)
    status: str = "lobby"
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ---------- Request / response shapes for the API ----------
# These are small helper models that describe what the *client* sends
# and what the *server* sends back. Keeping them separate from Player/Room
# is a good habit — it means we can change one without breaking the other.

class CreateRoomRequest(BaseModel):
    """Body of POST /rooms/create."""
    host_name: str = Field(min_length=1, max_length=20)


class JoinRoomRequest(BaseModel):
    """Body of POST /rooms/join."""
    room_code: str = Field(min_length=1, max_length=20)
    player_name: str = Field(min_length=1, max_length=20)