"""Code modules the agent can call as tools in Round 1 (Phase 3, "code modules").

These are deterministic, plain-Python helpers over the current grid. They are
derived rather than model-written: each one is a general ARC-AGI-3 perception
primitive whose *usefulness* is then validated against logged dev trajectories
in learning/mine.py before it is admitted to the skill library.

Every module takes (grid, params) and returns a short text string, because the
harness feeds the output straight back into the prompt.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Callable

import numpy as np

from harness.perception import (
    background_colour,
    colour_name,
    connected_components,
)


def _as_int(params: dict[str, Any], key: str, default: int | None = None) -> int | None:
    value = params.get(key, default)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def player_detector(grid: np.ndarray, params: dict[str, Any]) -> str:
    """Guess which object is the player: a small, colour-unique component.

    Heuristic: among non-background components, prefer ones whose colour occurs
    exactly once on the grid and whose size is small. Agent-controlled sprites
    in these games are almost always small and uniquely coloured.
    """
    if grid.size == 0:
        return "player_detector: empty grid"
    background = background_colour(grid)
    objects = connected_components(grid, background=background)
    if not objects:
        return "player_detector: no non-background objects"

    by_colour: dict[int, list[dict[str, Any]]] = {}
    for obj in objects:
        by_colour.setdefault(obj["colour"], []).append(obj)

    candidates = [
        objects_of[0]
        for colour, objects_of in by_colour.items()
        if len(objects_of) == 1 and objects_of[0]["size"] <= 16
    ]
    if not candidates:
        candidates = sorted(objects, key=lambda o: o["size"])[:3]

    candidates = sorted(candidates, key=lambda o: o["size"])[:3]
    lines = ["player_detector: ranked candidates (most likely first)"]
    for obj in candidates:
        r0, c0, r1, c1 = obj["bbox"]
        lines.append(
            f"  colour={obj['colour_name']}({obj['colour']}) size={obj['size']} "
            f"bbox=rows{r0}-{r1},cols{c0}-{c1} centroid={obj['centroid']} "
            f"(unique colour: {len(by_colour[obj['colour']]) == 1})"
        )
    return "\n".join(lines)


def obstacle_map(grid: np.ndarray, params: dict[str, Any]) -> str:
    """Summarise which colours form wall-like structures.

    Wall-like = a colour whose cells are numerous and concentrated in few
    components (long runs / borders), as opposed to scattered small items.
    """
    if grid.size == 0:
        return "obstacle_map: empty grid"
    background = background_colour(grid)
    objects = connected_components(grid, background=background)
    if not objects:
        return "obstacle_map: no non-background objects"

    stats: dict[int, dict[str, Any]] = {}
    for obj in objects:
        entry = stats.setdefault(
            obj["colour"], {"cells": 0, "components": 0, "largest": 0}
        )
        entry["cells"] += obj["size"]
        entry["components"] += 1
        entry["largest"] = max(entry["largest"], obj["size"])

    lines = [
        "obstacle_map: per-colour structure "
        "(high cells + few components => likely walls)"
    ]
    for colour, entry in sorted(stats.items(), key=lambda kv: -kv[1]["cells"]):
        ratio = entry["cells"] / max(entry["components"], 1)
        verdict = "wall-like" if entry["cells"] >= 20 and ratio >= 8 else "item-like"
        lines.append(
            f"  {colour_name(colour)}({colour}): cells={entry['cells']} "
            f"components={entry['components']} largest={entry['largest']} "
            f"-> {verdict}"
        )
    border = []
    height, width = grid.shape
    for colour in stats:
        mask = grid == colour
        if mask[0, :].any() or mask[-1, :].any() or mask[:, 0].any() or mask[:, -1].any():
            border.append(colour_name(colour))
    if border:
        lines.append(f"  touching the grid border: {', '.join(border)}")
    return "\n".join(lines)


def bfs_to_target(grid: np.ndarray, params: dict[str, Any]) -> str:
    """Shortest 4-connected path length from a start cell to a target cell.

    params: from_row, from_col, to_row, to_col, and optionally
    blocked_colours (list of colour ints treated as impassable).
    """
    if grid.size == 0:
        return "bfs_to_target: empty grid"
    height, width = grid.shape
    start_row = _as_int(params, "from_row")
    start_col = _as_int(params, "from_col")
    goal_row = _as_int(params, "to_row")
    goal_col = _as_int(params, "to_col")
    if None in (start_row, start_col, goal_row, goal_col):
        return (
            "bfs_to_target: needs from_row, from_col, to_row, to_col "
            "(optionally blocked_colours)"
        )
    for name, value, limit in (
        ("from_row", start_row, height),
        ("from_col", start_col, width),
        ("to_row", goal_row, height),
        ("to_col", goal_col, width),
    ):
        if not 0 <= int(value) <= limit - 1:
            return f"bfs_to_target: {name}={value} is outside 0..{limit - 1}"

    raw_blocked = params.get("blocked_colours") or params.get("blocked") or []
    if isinstance(raw_blocked, (int, float)):
        raw_blocked = [raw_blocked]
    try:
        blocked = {int(c) for c in raw_blocked}
    except (TypeError, ValueError):
        return "bfs_to_target: blocked_colours must be a list of integers"

    start = (int(start_row), int(start_col))
    goal = (int(goal_row), int(goal_col))
    if int(grid[goal]) in blocked:
        return "bfs_to_target: the target cell is itself a blocked colour"

    queue = deque([start])
    distance = {start: 0}
    while queue:
        cell = queue.popleft()
        if cell == goal:
            path_len = distance[cell]
            return (
                f"bfs_to_target: shortest 4-connected path from {start} to {goal} "
                f"is {path_len} steps (blocked colours: "
                f"{sorted(blocked) if blocked else 'none'})"
            )
        r, c = cell
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nr, nc = r + dr, c + dc
            if not (0 <= nr < height and 0 <= nc < width):
                continue
            if (nr, nc) in distance or int(grid[nr, nc]) in blocked:
                continue
            distance[(nr, nc)] = distance[cell] + 1
            queue.append((nr, nc))
    return (
        f"bfs_to_target: {goal} is UNREACHABLE from {start} with blocked colours "
        f"{sorted(blocked) if blocked else 'none'}"
    )


def grid_region(grid: np.ndarray, params: dict[str, Any]) -> str:
    """Print a rectangular slice of raw colour indices.

    Lets the agent zoom in when the object summary is too coarse to decide a
    click coordinate.
    """
    if grid.size == 0:
        return "grid_region: empty grid"
    height, width = grid.shape
    r0 = max(0, _as_int(params, "row0", 0) or 0)
    c0 = max(0, _as_int(params, "col0", 0) or 0)
    r1 = min(height - 1, _as_int(params, "row1", min(height, 16) - 1) or 0)
    c1 = min(width - 1, _as_int(params, "col1", min(width, 16) - 1) or 0)
    if r1 < r0 or c1 < c0:
        return "grid_region: empty range (need row0<=row1 and col0<=col1)"
    if (r1 - r0 + 1) * (c1 - c0 + 1) > 1024:
        return "grid_region: region too large; ask for at most 1024 cells"

    header = "     " + "".join(f"{c % 10}" for c in range(c0, c1 + 1))
    lines = [f"grid_region rows{r0}-{r1}, cols{c0}-{c1} (digits = colour index)", header]
    for r in range(r0, r1 + 1):
        row = "".join(
            format(int(v), "x") for v in grid[r, c0 : c1 + 1]
        )
        lines.append(f"r{r:>3} {row}")
    return "\n".join(lines)


MODULES: dict[str, dict[str, Any]] = {
    "player_detector": {
        "fn": player_detector,
        "description": (
            "Rank which object is most likely the agent-controlled sprite "
            "(small, uniquely coloured component)."
        ),
        "params": {},
        "returns": "ranked candidate objects with colour, size, bbox",
    },
    "obstacle_map": {
        "fn": obstacle_map,
        "description": (
            "Classify each colour as wall-like or item-like from how its cells "
            "clump, and report which colours touch the border."
        ),
        "params": {},
        "returns": "per-colour structure summary",
    },
    "bfs_to_target": {
        "fn": bfs_to_target,
        "description": (
            "Shortest 4-connected path length between two cells, treating the "
            "given colours as impassable. Use it to check reachability before "
            "committing to a route."
        ),
        "params": {
            "from_row": "int",
            "from_col": "int",
            "to_row": "int",
            "to_col": "int",
            "blocked_colours": "list[int], optional",
        },
        "returns": "path length in steps, or UNREACHABLE",
    },
    "grid_region": {
        "fn": grid_region,
        "description": (
            "Print raw colour indices for a rectangle of the grid, to pin down "
            "an exact click coordinate."
        ),
        "params": {
            "row0": "int",
            "col0": "int",
            "row1": "int",
            "col1": "int",
        },
        "returns": "hex digit map of the region",
    },
}


def run_module(name: str, params: dict[str, Any], grid: np.ndarray) -> str:
    entry = MODULES.get(name)
    if entry is None:
        return (
            f"unknown module {name!r}; available: {', '.join(sorted(MODULES))}"
        )
    fn: Callable[[np.ndarray, dict[str, Any]], str] = entry["fn"]
    return fn(grid, params or {})
