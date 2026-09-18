"""
room_manager.py — the in-memory brain that keeps track of all rooms.

Right now rooms live only in RAM. When the server restarts, rooms vanish.
That's OK for development; we'll add a real database in a later step.
"""

import random
import string

from models import Player, Room


# These are the letters we'll use for room codes.
# We deliberately exclude:
#   - 0 and O  (look the same)
#   - 1 and I  (look the same)
#   - 2 and Z  (look the same in some fonts)
# This makes room codes easier to read aloud and type.
ROOM_CODE_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXY"   # 23 letters
ROOM_CODE_DIGITS = "3456789"                     # 7 digits


class RoomManager:
    """
    A single object that holds every active room.

    Think of it as a dictionary keyed by room code:
        "FRD-7284" -> Room(...)
    """

    def __init__(self):
        # The actual storage. Plain dict, room_code -> Room object.
        self.rooms: dict[str, Room] = {}

    # ---------- code generation ----------

    def _generate_room_code(self) -> str:
        """
        Return a fresh code like 'FRD-7284' that isn't already in use.

        The 'FRD-' prefix is cosmetic — it makes codes feel like room IDs
        rather than random strings. The four characters after the dash
        are random letters+digits.
        """

        # Loop forever until we find a code that isn't taken.
        # (Practically, this will succeed on the first try almost always.)
        while True:
            part1 = "".join(random.choices(ROOM_CODE_LETTERS, k=2))
            part2 = "".join(random.choices(ROOM_CODE_LETTERS + ROOM_CODE_DIGITS, k=2))
            code = f"FRD-{part1}{part2}"

            if code not in self.rooms:
                return code

    # ---------- room operations ----------

    def create_room(self, host_name: str) -> Room:
        """
        Create a new room with the given player as host.

        Returns the new Room object.
        """
        code = self._generate_room_code()

        # Create the host player. is_host=True on this one.
        host = Player(name=host_name, is_host=True)

        # Create the room, giving it the host's id.
        room = Room(code=code, host_id=host.id, players=[host])

        # Store it.
        self.rooms[code] = room

        return room

    def get_room(self, code: str) -> Room | None:
        """
        Return the Room with this code, or None if it doesn't exist.

        Normalizing to uppercase so 'frd-7284' and 'FRD-7284' are the same.
        """
        return self.rooms.get(code.upper())

    def join_room(self, code: str, player_name: str) -> Room | None:
        """
        Add a new player to the room with this code.

        Returns:
          - the Room on success
          - None if the room doesn't exist
        """
        room = self.get_room(code)
        if room is None:
            return None

        # Create a regular (non-host) player.
        player = Player(name=player_name, is_host=False)

        room.players.append(player)
        return room


# ---------- singleton instance ----------
# This is the ONE RoomManager the whole server will use.
# Every module that does `from room_manager import room_manager`
# gets the exact same object, and therefore the exact same rooms.
room_manager = RoomManager()