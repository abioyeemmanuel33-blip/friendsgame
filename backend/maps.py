"""
maps.py — server-side map definitions and match-map generation.
"""

import random


# ---------- base map ----------
# #  = wall / building / tree / water   (impassable)
# .  = grass / road                    (walkable)
# S  = spawn                            (walkable, row 1 only)
# F  = finish                           (walkable, row 19 col 9)
#
# Structure:
#   - Row 1: 9 spawn cells
#   - Rows 5, 9, 13: open crossing streets (full width walkable)
#   - Other rows: buildings forming corridors for 5 vertical routes
#   - Row 19: finish

BASE_MAP = [
    "####################",
    "#S.S.S.S.S.S.S.S.S.#",
    "#..................#",
    "#.###.##.##.###...#",
    "#.#...#....#.#.#...#",
    "#..................#",
    "#.#.###.##.###.#...#",
    "#.#.#.......#.#.#...#",
    "#...#.###.#.#.#.....#",
    "#..................#",
    "#.#.###.##.###.#...#",
    "#.#.#.......#.#.#...#",
    "#...#.###.#.#.#.....#",
    "#..................#",
    "#.#.###.##.###.#...#",
    "#.#...#....#.#.#...#",
    "#.###.##.##.###...#",
    "#..................#",
    "#..................#",
    "#########F##########",
]


# ---------- helpers ----------

def get_tile(hazard_map: list[str], row: int, col: int) -> str | None:
    if row < 0 or row >= len(hazard_map):
        return None
    line = hazard_map[row]
    if col < 0 or col >= len(line):
        return None
    return line[col]


BLOCKING_TILES = {"#", "X", "Y", "Z"}


def is_walkable(hazard_map: list[str], row: int, col: int) -> bool:
    ch = get_tile(hazard_map, row, col)
    if ch is None:
        return False
    return ch not in BLOCKING_TILES


def is_hazard(ch: str | None) -> bool:
    return ch in {"X", "Y", "Z"}


def is_finish_tile(hazard_map: list[str], row: int, col: int) -> bool:
    return get_tile(hazard_map, row, col) == "F"


def spawn_positions() -> list[tuple[int, int]]:
    positions = []
    for col, ch in enumerate(BASE_MAP[1]):
        if ch == "S":
            positions.append((1, col))
    return positions


# ---------- match map ----------

def generate_match_map() -> list[str]:
    """
    Return a copy of the base map. Dynamic hazards are added later.
    """
    return list(BASE_MAP)


# ---------- dynamic hazard helpers ----------

HAZARD_CHARS = ["X", "Y", "Z"]


def list_road_tiles(hazard_map: list[str]) -> list[tuple[int, int]]:
    tiles: list[tuple[int, int]] = []
    for r, line in enumerate(hazard_map):
        if r == 1:
            continue
        if r == len(hazard_map) - 1:
            continue
        for c, ch in enumerate(line):
            if ch == ".":
                if c == 0 or c == len(line) - 1:
                    continue
                tiles.append((r, c))
    return tiles


def list_active_hazards(hazard_map: list[str]) -> list[tuple[int, int]]:
    positions: list[tuple[int, int]] = []
    for r, line in enumerate(hazard_map):
        for c, ch in enumerate(line):
            if ch in HAZARD_CHARS:
                positions.append((r, c))
    return positions


def pick_random_tile(
    hazard_map: list[str],
    forbidden: set[tuple[int, int]] | None = None,
) -> tuple[int, int] | None:
    if forbidden is None:
        forbidden = set()
    candidates = [
        (r, c) for (r, c) in list_road_tiles(hazard_map)
        if (r, c) not in forbidden
    ]
    if not candidates:
        return None
    return random.choice(candidates)


def put_hazard(hazard_map: list[str], row: int, col: int, ch: str) -> None:
    line = list(hazard_map[row])
    line[col] = ch
    hazard_map[row] = "".join(line)


def clear_hazard(hazard_map: list[str], row: int, col: int) -> None:
    line = list(hazard_map[row])
    if line[col] in HAZARD_CHARS:
        line[col] = "."
        hazard_map[row] = "".join(line)