"""Plain-code perception: ARC-AGI-3 frame -> text. No LLM involved.

Round 0 of issue #8 deliberately keeps this minimal: grid size, a colour-count
summary, and a list of connected-component objects {id, colour, bbox, size}.
"""

from __future__ import annotations

from collections import Counter, deque
from typing import Any, Iterable

import numpy as np

# ARC's 16-colour palette index -> readable name, so the model gets a stable
# vocabulary instead of bare integers.
COLOUR_NAMES = {
    0: "black",
    1: "blue",
    2: "red",
    3: "green",
    4: "yellow",
    5: "grey",
    6: "magenta",
    7: "orange",
    8: "cyan",
    9: "maroon",
    10: "pink",
    11: "lime",
    12: "teal",
    13: "brown",
    14: "navy",
    15: "white",
}


def colour_name(value: int) -> str:
    return COLOUR_NAMES.get(int(value), f"c{int(value)}")


def grid_from_frame(frame: Iterable[Any] | None) -> np.ndarray:
    """Pull the observation grid out of FrameDataRaw.frame.

    `frame` is a list of layers. Empty frames happen (e.g. before reset), so
    return an explicit empty grid rather than raising.
    """
    if frame is None:
        return np.zeros((0, 0), dtype=np.int16)
    layers = list(frame)
    if not layers:
        return np.zeros((0, 0), dtype=np.int16)
    # The last layer is the composited, visible one.
    return np.asarray(layers[-1], dtype=np.int16)


def background_colour(grid: np.ndarray) -> int:
    """Most frequent colour, treated as background for object extraction."""
    if grid.size == 0:
        return 0
    values, counts = np.unique(grid, return_counts=True)
    return int(values[int(np.argmax(counts))])


def colour_counts(grid: np.ndarray) -> dict[int, int]:
    if grid.size == 0:
        return {}
    values, counts = np.unique(grid, return_counts=True)
    return {int(v): int(c) for v, c in zip(values, counts)}


def connected_components(
    grid: np.ndarray, background: int | None = None, max_objects: int | None = None
) -> list[dict[str, Any]]:
    """4-connected same-colour components, excluding the background colour.

    Returns objects sorted largest-first so that truncation keeps the most
    salient ones. Each object is {id, colour, colour_name, bbox, size, centroid}
    with bbox as (row_min, col_min, row_max, col_max), inclusive.
    """
    if grid.size == 0:
        return []
    if background is None:
        background = background_colour(grid)

    height, width = grid.shape
    seen = np.zeros((height, width), dtype=bool)
    objects: list[dict[str, Any]] = []

    for row in range(height):
        for col in range(width):
            if seen[row, col]:
                continue
            colour = int(grid[row, col])
            if colour == background:
                seen[row, col] = True
                continue

            # BFS the component.
            queue = deque([(row, col)])
            seen[row, col] = True
            cells: list[tuple[int, int]] = []
            while queue:
                r, c = queue.popleft()
                cells.append((r, c))
                for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < height and 0 <= nc < width:
                        if not seen[nr, nc] and int(grid[nr, nc]) == colour:
                            seen[nr, nc] = True
                            queue.append((nr, nc))

            rows = [cell[0] for cell in cells]
            cols = [cell[1] for cell in cells]
            objects.append(
                {
                    "colour": colour,
                    "colour_name": colour_name(colour),
                    "bbox": [min(rows), min(cols), max(rows), max(cols)],
                    "size": len(cells),
                    "centroid": [
                        round(sum(rows) / len(cells), 1),
                        round(sum(cols) / len(cells), 1),
                    ],
                }
            )

    objects.sort(key=lambda o: (-o["size"], o["bbox"][0], o["bbox"][1]))
    for index, obj in enumerate(objects):
        obj["id"] = index
    if max_objects is not None and len(objects) > max_objects:
        objects = objects[:max_objects]
    return objects


def describe_grid(
    grid: np.ndarray, max_objects: int = 40, background: int | None = None
) -> tuple[str, list[dict[str, Any]]]:
    """Render the grid as the text observation, and return the object list too."""
    if grid.size == 0:
        return "GRID: empty (no frame data)", []

    if background is None:
        background = background_colour(grid)
    height, width = grid.shape
    counts = colour_counts(grid)
    objects = connected_components(grid, background=background)
    shown = objects[:max_objects]

    lines = [f"GRID: {height} rows x {width} cols (row 0 = top, col 0 = left)"]
    counts_text = ", ".join(
        f"{colour_name(v)}({v})={counts[v]}"
        for v in sorted(counts, key=lambda k: -counts[k])
    )
    lines.append(f"COLOUR COUNTS: {counts_text}")
    lines.append(
        f"BACKGROUND (most common colour): {colour_name(background)}({background})"
    )
    lines.append(f"OBJECTS: {len(objects)} non-background connected components")
    if len(shown) < len(objects):
        lines.append(
            f"  (showing the {len(shown)} largest of {len(objects)}; "
            "smaller ones omitted to bound prompt size)"
        )
    for obj in shown:
        r0, c0, r1, c1 = obj["bbox"]
        lines.append(
            f"  id={obj['id']} colour={obj['colour_name']}({obj['colour']}) "
            f"size={obj['size']} bbox=rows{r0}-{r1},cols{c0}-{c1} "
            f"centroid=({obj['centroid'][0]},{obj['centroid'][1]})"
        )
    return "\n".join(lines), objects


def frame_diff(
    previous: np.ndarray, current: np.ndarray, max_cells: int = 40
) -> dict[str, Any]:
    """Structured difference between two grids.

    Kept structured (not just text) because Phase 3 mines action-effect rules
    straight out of these records.
    """
    if previous.size == 0 or current.size == 0:
        return {"changed": None, "n_changed": 0, "note": "no comparable frame"}
    if previous.shape != current.shape:
        return {
            "changed": None,
            "n_changed": -1,
            "note": f"grid resized {previous.shape} -> {current.shape}",
        }

    mask = previous != current
    n_changed = int(mask.sum())
    if n_changed == 0:
        return {"changed": [], "n_changed": 0, "note": "no change"}

    rows, cols = np.nonzero(mask)
    # Colour-transition histogram: the signal action-effect rules key off.
    transitions = Counter(
        (int(previous[r, c]), int(current[r, c])) for r, c in zip(rows, cols)
    )
    changed = [
        {
            "row": int(r),
            "col": int(c),
            "from": int(previous[r, c]),
            "to": int(current[r, c]),
        }
        for r, c in list(zip(rows, cols))[:max_cells]
    ]
    return {
        "changed": changed,
        "n_changed": n_changed,
        "truncated": n_changed > max_cells,
        "bbox": [int(rows.min()), int(cols.min()), int(rows.max()), int(cols.max())],
        "transitions": [
            {"from": f, "to": t, "count": n} for (f, t), n in transitions.most_common()
        ],
    }


def describe_diff(diff: dict[str, Any], max_cells: int = 40) -> str:
    """Human/model-readable rendering of a frame_diff result."""
    if diff.get("n_changed") == 0:
        return "DIFF: nothing changed on the grid."
    if diff.get("changed") is None:
        return f"DIFF: {diff.get('note', 'unavailable')}"

    r0, c0, r1, c1 = diff["bbox"]
    lines = [
        f"DIFF: {diff['n_changed']} cells changed, within rows{r0}-{r1},cols{c0}-{c1}"
    ]
    for t in diff["transitions"][:8]:
        lines.append(
            f"  {t['count']} cells {colour_name(t['from'])}({t['from']})"
            f" -> {colour_name(t['to'])}({t['to']})"
        )
    for cell in diff["changed"][:max_cells]:
        lines.append(
            f"  ({cell['row']},{cell['col']}): {colour_name(cell['from'])}"
            f" -> {colour_name(cell['to'])}"
        )
    if diff.get("truncated"):
        lines.append("  (cell list truncated)")
    return "\n".join(lines)
