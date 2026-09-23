"""
maps.py — server-side map definitions and match-map generation.
"""

import random


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


# Hazard chars block movement; power-up chars do NOT block (you walk onto them).
BLOCKING_TILES = {"#", "X", "Y", "Z"}


def is_walkable(hazard_map: list[str], row: int, col: int) -> bool:
    ch = get_tile(hazard_map, row, col)
    if ch is None:
        return False
    return ch not in BLOCKING_TILES


HAZARD_CHARS = ["X", "Y", "Z"]
POWERUP_CHARS = ["A", "B", "C"]


def is_hazard(ch: str | None) -> bool:
    return ch in {"X", "Y", "Z"}


def is_powerup(ch: str | None) -> bool:
    return ch in {"A", "B", "C"}


def is_finish_tile(hazard_map: list[str], row: int, col: int) -> bool:
    return get_tile(hazard_map, row, col) == "F"


def spawn_positions() -> list[tuple[int, int]]:
    positions = []
    for col, ch in enumerate(BASE_MAP[1]):
        if ch == "S":
            positions.append((1, col))
    return positions


def generate_match_map() -> list[str]:
    return list(BASE_MAP)


# ---------- dynamic tile helpers ----------

def list_road_tiles(hazard_map: list[str]) -> list[tuple[int, int]]:
    """Tiles that are plain road and can receive a hazard or power-up."""
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


def list_active_powerups(hazard_map: list[str]) -> list[tuple[int, int]]:
    positions: list[tuple[int, int]] = []
    for r, line in enumerate(hazard_map):
        for c, ch in enumerate(line):
            if ch in POWERUP_CHARS:
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


def put_tile(hazard_map: list[str], row: int, col: int, ch: str) -> None:
    line = list(hazard_map[row])
    line[col] = ch
    hazard_map[row] = "".join(line)


def clear_dynamic_tile(hazard_map: list[str], row: int, col: int) -> None:
    """Reset a tile to plain road if it currently holds a hazard or power-up."""
    line = list(hazard_map[row])
    if line[col] in HAZARD_CHARS or line[col] in POWERUP_CHARS:
        line[col] = "."
        hazard_map[row] = "".join(line)


# ---------- legacy aliases (kept for main.py compatibility) ----------

def put_hazard(hazard_map: list[str], row: int, col: int, ch: str) -> None:
    put_tile(hazard_map, row, col, ch)


def clear_hazard(hazard_map: list[str], row: int, col: int) -> None:
    clear_dynamic_tile(hazard_map, row, col)