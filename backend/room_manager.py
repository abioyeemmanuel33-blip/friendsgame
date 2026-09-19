"""
room_manager.py — in-memory room storage.
"""

import random

from models import Player, Room


ROOM_CODE_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXY"
ROOM_CODE_DIGITS = "3456789"

PLAYER_COLORS = [
    "#5b7cfa", "#3ddc84", "#ff5c5c", "#ffb84d", "#c084fc",
    "#22d3ee", "#f472b6", "#facc15", "#94a3b8",
]


class RoomManager:
    def __init__(self):
        self.rooms: dict[str, Room] = {}

    def _generate_room_code(self) -> str:
        while True:
            part1 = "".join(random.choices(ROOM_CODE_LETTERS, k=2))
            part2 = "".join(random.choices(ROOM_CODE_LETTERS + ROOM_CODE_DIGITS, k=2))
            code = f"FRD-{part1}{part2}"
            if code not in self.rooms:
                return code

    def _pick_color(self, room: Room) -> str:
        used = {p.color for p in room.players}
        for color in PLAYER_COLORS:
            if color not in used:
                return color
        return PLAYER_COLORS[len(room.players) % len(PLAYER_COLORS)]

    def create_room(self, host_name: str) -> Room:
        code = self._generate_room_code()
        host = Player(name=host_name, is_host=True)
        host.color = PLAYER_COLORS[0]
        room = Room(code=code, host_id=host.id, players=[host])
        self.rooms[code] = room
        return room

    def get_room(self, code: str) -> Room | None:
        return self.rooms.get(code.upper())

    def join_room(self, code: str, player_name: str) -> Room | None:
        room = self.get_room(code)
        if room is None:
            return None
        player = Player(name=player_name, is_host=False)
        player.color = self._pick_color(room)
        room.players.append(player)
        return room

    def all_rooms(self) -> list[Room]:
        """Return every room. Used by the background hazard ticker."""
        return list(self.rooms.values())


room_manager = RoomManager()