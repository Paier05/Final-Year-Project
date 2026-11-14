"""Stage 1 · Analyze, frame evidence (issue #14, fix 2).

#12's Analyze told the Meta LLM how each episode scored but nothing about
where the player went or what else happened on screen. This module measures
both from the saved frames, by comparing each frame with the one before it:

A. Player movement. The player's block is found, not given: it is the patch
   that keeps re-appearing shifted while what it leaves behind is the common
   background. Per step: the action, the block's position before and after,
   and whether it moved. Per episode: path, cells visited, blocked moves,
   final position. Across episodes: visit counts, and open cells never
   visited.
B. Other on-screen changes: every changed cell the block's move does not
   explain. Changed cells are grouped into regions; a region that changes on
   most steps is "regular" and gets one line, one that changes on few steps is
   "rare" and every change is an event with the cell values before and after.
C. The link: for each rare event the action, the block's position before and
   after, and what was on the cell it stepped onto; and per cell, how often
   the block entered it and how often the change followed.

Rules this module keeps (the issue's):

- Frames only. Nothing here reads the game's state or source, and no screen
  location is written into the code: the block and the regions are whatever
  the frame comparison finds, so the same code runs on another level.
- Observations only. The rendered section reports what changed and where. It
  does not say what a change means and gives no advice.
- Deterministic, no model.

Limit: the block is found from moves that shift it by at least its own size
(the old and the new patch do not overlap), which is how ls20 moves.
"""

from __future__ import annotations

import csv
import os
from collections import Counter, defaultdict
from typing import Any

import numpy as np

SEARCH = 12            # largest shift (cells, per axis) tried when finding the block
MIN_BLOCK_CELLS = 4    # a moving patch smaller than this is not taken for the block
TEMPLATE_VOTES = 3     # detections that must agree on the block's pattern
REGION_GAP = 2         # changed cells this close (Chebyshev) are one region
REGULAR_SHARE = 0.5    # a region changing on at least this share of changing steps is regular
MAX_GRID_CELLS = 144   # larger regions are summarised, not printed cell by cell
MAX_EVENTS_SHOWN = 12  # rare events printed in the report (all are in the data)
MAX_PATH_POINTS = 40   # path waypoints printed per episode (all are in the per-step file)


# ---------------------------------------------------------------------------
# Finding the block
# ---------------------------------------------------------------------------


def _moved_patch(before: np.ndarray, after: np.ndarray) -> tuple[np.ndarray, tuple[int, int]] | None:
    """(cells of the patch in `before`, shift) if a patch moved rigidly.

    A cell p belongs to a patch moved by s if p and p+s both changed and what
    was at p is now at p+s. The same test also fits the reverse reading ("the
    background moved by -s"), so of the two the patch whose colours are rarer
    on screen is taken: a moving object is small, the floor it crosses is not.
    """
    changed = before != after
    if int(changed.sum()) < 2 * MIN_BLOCK_CELLS:
        return None
    height, width = before.shape
    rows, cols = np.nonzero(changed)
    frequency = np.bincount(before.ravel(), minlength=256)
    best: tuple[float, int, np.ndarray, tuple[int, int]] | None = None
    for dr in range(-SEARCH, SEARCH + 1):
        for dc in range(-SEARCH, SEARCH + 1):
            if dr == 0 and dc == 0:
                continue
            r2, c2 = rows + dr, cols + dc
            inside = (r2 >= 0) & (r2 < height) & (c2 >= 0) & (c2 < width)
            if int(inside.sum()) < MIN_BLOCK_CELLS:
                continue
            r1, c1, r2, c2 = rows[inside], cols[inside], r2[inside], c2[inside]
            keep = changed[r2, c2] & (before[r1, c1] == after[r2, c2])
            n = int(keep.sum())
            if n < MIN_BLOCK_CELLS:
                continue
            cells = np.stack([r1[keep], c1[keep]], axis=1)
            rarity = float(frequency[before[cells[:, 0], cells[:, 1]]].mean())
            # Most cells explained first; between a patch and its mirror
            # reading (same count), the rarer colours win.
            key = (-n, rarity)
            if best is None or key < (best[0], best[1]):
                best = (-n, rarity, cells, (dr, dc))
    if best is None:
        return None
    return best[2], best[3]


class Block:
    """The player's block: a pattern of cell values and which cells carry it."""

    def __init__(self, values: np.ndarray, mask: np.ndarray) -> None:
        self.values, self.mask = values, mask
        self.height, self.width = values.shape

    def signature(self) -> bytes:
        return self.values.tobytes() + self.mask.tobytes() + bytes(self.values.shape)

    def at(self, grid: np.ndarray, row: int, col: int) -> bool:
        if row < 0 or col < 0 or row + self.height > grid.shape[0] or col + self.width > grid.shape[1]:
            return False
        patch = grid[row:row + self.height, col:col + self.width]
        return bool(np.all((patch == self.values) | ~self.mask))

    def find(self, grid: np.ndarray) -> list[tuple[int, int]]:
        if grid.shape[0] < self.height or grid.shape[1] < self.width:
            return []
        windows = np.lib.stride_tricks.sliding_window_view(grid, (self.height, self.width))
        hits = np.all((windows == self.values) | ~self.mask, axis=(2, 3))
        return [(int(r), int(c)) for r, c in np.argwhere(hits)]

    def cells(self, row: int, col: int) -> np.ndarray:
        offsets = np.argwhere(self.mask)
        return offsets + np.array([row, col])


def find_block(episodes: list[dict[str, Any]]) -> Block | None:
    """The pattern most often seen moving, from the first agreeing detections."""
    votes: Counter = Counter()
    blocks: dict[bytes, Block] = {}
    for episode in episodes:
        for step in episode["transitions"]:
            found = _moved_patch(step["before"], step["after"])
            if found is None:
                continue
            cells, _shift = found
            r0, c0 = cells.min(axis=0)
            r1, c1 = cells.max(axis=0)
            mask = np.zeros((r1 - r0 + 1, c1 - c0 + 1), dtype=bool)
            mask[cells[:, 0] - r0, cells[:, 1] - c0] = True
            values = np.where(mask, step["before"][r0:r1 + 1, c0:c1 + 1], 0).astype(np.int16)
            block = Block(values, mask)
            votes[block.signature()] += 1
            blocks.setdefault(block.signature(), block)
            if votes[block.signature()] >= TEMPLATE_VOTES:
                return block
    return blocks[votes.most_common(1)[0][0]] if votes else None


# ---------------------------------------------------------------------------
# Steps of one episode
# ---------------------------------------------------------------------------


def load_transitions(records: list[dict[str, Any]], frames: Any) -> list[dict[str, Any]]:
    """One item per frame change: every action, and every level reset the
    harness made after a game over (which adds a frame of its own)."""
    out = []
    for record in records:
        if record.get("type") != "tool_call":
            continue
        for item in record.get("actions") or []:
            out.append({
                "step": int(item["action_index"]), "turn": int(item.get("turn", record.get("turn", 0))),
                "action": item["action"],
                "before": np.asarray(frames[item["frame_before"]]), "after": np.asarray(frames[item["frame_after"]]),
            })
            if item.get("auto_reset_frame") is not None:
                out.append({
                    "step": int(item["action_index"]), "turn": int(item.get("turn", record.get("turn", 0))),
                    "action": "LEVEL RESTART (by the harness, after game over)",
                    "before": np.asarray(frames[item["frame_after"]]),
                    "after": np.asarray(frames[item["auto_reset_frame"]]),
                })
    return out


def _nearest(points: list[tuple[int, int]], to: tuple[int, int] | None) -> tuple[int, int] | None:
    if not points:
        return None
    if to is None:
        return points[0] if len(points) == 1 else None
    return min(points, key=lambda p: (abs(p[0] - to[0]) + abs(p[1] - to[1]), p))


def _start_position(block: Block, transitions: list[dict[str, Any]]) -> tuple[int, int] | None:
    """Where the block is in the first frame. If the pattern appears more than
    once, the copy that moves away first is the block."""
    if not transitions:
        return None
    candidates = block.find(transitions[0]["before"])
    if len(candidates) <= 1:
        return candidates[0] if candidates else None
    for step in transitions:
        gone = [p for p in candidates if not block.at(step["after"], *p)]
        if len(gone) == 1:
            return gone[0]
    return None


def track(block: Block, transitions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per step: the block's position before and after, and the changed cells
    its move does not explain."""
    position = _start_position(block, transitions)
    rows = []
    for step in transitions:
        before, after = step["before"], step["after"]
        changed = before != after
        if position is None:  # lost (or never found): look again
            position = _nearest(block.find(before), None)
        start = position
        if before.shape != after.shape:
            end = None
        elif start is not None and block.at(after, *start):
            end = start
        else:
            end = _nearest(block.find(after), start)
        explained = np.zeros(changed.shape, dtype=bool)
        for point in (start, end):
            if point is not None and before.shape == after.shape:
                cells = block.cells(*point)
                explained[cells[:, 0], cells[:, 1]] = True
        other = changed & ~explained if before.shape == after.shape else changed
        entered = None
        if end is not None and end != start and before.shape == after.shape:
            entered = before[end[0]:end[0] + block.height, end[1]:end[1] + block.width].copy()
        rows.append({
            "step": step["step"], "turn": step["turn"], "action": step["action"],
            "before": start, "after": end, "moved": start is not None and end is not None and end != start,
            "n_changed": int(changed.sum()) if before.shape == after.shape else None,
            "other": np.argwhere(other), "entered": entered,
            "frame_before": before, "frame_after": after,
        })
        position = end
    return rows


# ---------------------------------------------------------------------------
# Regions of other changes
# ---------------------------------------------------------------------------


def _regions(cells: set[tuple[int, int]]) -> list[tuple[int, int, int, int]]:
    """Bounding boxes of the clusters of `cells` (cells within REGION_GAP of
    each other are one cluster), top-left first."""
    remaining = set(cells)
    boxes = []
    while remaining:
        seed = remaining.pop()
        stack, cluster = [seed], [seed]
        while stack:
            r, c = stack.pop()
            for dr in range(-REGION_GAP, REGION_GAP + 1):
                for dc in range(-REGION_GAP, REGION_GAP + 1):
                    nxt = (r + dr, c + dc)
                    if nxt in remaining:
                        remaining.remove(nxt)
                        stack.append(nxt)
                        cluster.append(nxt)
        rs, cs = [p[0] for p in cluster], [p[1] for p in cluster]
        boxes.append((min(rs), min(cs), max(rs), max(cs)))
    return sorted(boxes)


def _in_box(cells: np.ndarray, box: tuple[int, int, int, int]) -> np.ndarray:
    r0, c0, r1, c1 = box
    return cells[(cells[:, 0] >= r0) & (cells[:, 0] <= r1) & (cells[:, 1] >= c0) & (cells[:, 1] <= c1)]


def _hex_rows(grid: np.ndarray, box: tuple[int, int, int, int]) -> list[str]:
    r0, c0, r1, c1 = box
    return ["".join(format(int(v), "x") for v in row) for row in grid[r0:r1 + 1, c0:c1 + 1]]


# ---------------------------------------------------------------------------
# The evidence
# ---------------------------------------------------------------------------


def _pos(point: Any) -> list[int] | None:
    return None if point is None else [int(point[0]), int(point[1])]


def build(episodes: list[dict[str, Any]]) -> dict[str, Any]:
    """Frame evidence for one version.

    `episodes`: [{"seed", "records", "frames"}], `frames` being the array (or
    list) of the episode's frames in the order the trajectory indexes them.
    Returns the evidence as plain data; `per_step` holds the full table.
    """
    loaded = []
    for episode in episodes:
        loaded.append({"seed": episode["seed"],
                       "transitions": load_transitions(episode["records"], episode["frames"])})
    n_steps = sum(len(e["transitions"]) for e in loaded)
    evidence: dict[str, Any] = {"n_episodes": len(loaded), "n_steps": n_steps, "block": None,
                                "episodes": [], "per_step": []}
    block = find_block(loaded)
    if block is None:
        evidence["note"] = "no moving block was found in the frames"
        return evidence
    evidence["block"] = {"height": block.height, "width": block.width,
                         "pattern": ["".join(format(int(v), "x") if m else "." for v, m in zip(vr, mr))
                                     for vr, mr in zip(block.values, block.mask)]}

    tracked = {e["seed"]: track(block, e["transitions"]) for e in loaded}

    # Step vectors: a displacement seen at least twice is a normal move; any
    # other displacement is a jump.
    vectors: Counter = Counter()
    for rows in tracked.values():
        for row in rows:
            if row["moved"]:
                vectors[(row["after"][0] - row["before"][0], row["after"][1] - row["before"][1])] += 1
    lengths = Counter(abs(v[0]) + abs(v[1]) for v, n in vectors.items() for _ in range(n))
    step_length = lengths.most_common(1)[0][0] if lengths else None
    step_vectors = sorted(v for v in vectors if abs(v[0]) + abs(v[1]) == step_length)
    evidence["block"]["typical_move_cells"] = step_length

    # ---- B: regions of change outside the block, pooled over the episodes ----
    all_other: set[tuple[int, int]] = set()
    changing_steps = 0
    for rows in tracked.values():
        for row in rows:
            if row["n_changed"]:
                changing_steps += 1
            all_other.update((int(r), int(c)) for r, c in row["other"])
    def hits_for(candidates: list[tuple[int, int, int, int]]) -> dict[int, list]:
        found: dict[int, list[tuple[int, dict[str, Any], np.ndarray]]] = defaultdict(list)
        for seed, rows in tracked.items():
            for row in rows:
                if len(row["other"]) == 0:
                    continue
                for index, box in enumerate(candidates):
                    cells = _in_box(row["other"], box)
                    if len(cells):
                        found[index].append((seed, row, cells))
        return found

    # Clusters that change on exactly the same steps are one region: parts of
    # one thing that is redrawn as a whole.
    clusters = _regions(all_other)
    together: dict[frozenset, list[tuple[int, int, int, int]]] = defaultdict(list)
    for index, found in hits_for(clusters).items():
        together[frozenset((seed, row["step"], row["action"]) for seed, row, _c in found)].append(clusters[index])
    boxes = sorted(
        (min(b[0] for b in group), min(b[1] for b in group), max(b[2] for b in group), max(b[3] for b in group))
        for group in together.values()
    )
    hits = hits_for(boxes)
    regions = []
    for index, box in enumerate(boxes):
        share = len(hits[index]) / changing_steps if changing_steps else 0.0
        sizes = Counter(len(cells) for _s, _r, cells in hits[index])
        regions.append({
            "id": f"R{index + 1}", "rows": [box[0], box[2]], "cols": [box[1], box[3]],
            "steps_changed": len(hits[index]), "share_of_changing_steps": round(share, 3),
            "kind": "regular" if share >= REGULAR_SHARE else "rare",
            "typical_cells_per_change": sizes.most_common(1)[0][0] if sizes else 0,
        })
    evidence["changing_steps"] = changing_steps
    evidence["regions"] = regions

    # ---- B + C: one event per rare change, with what the block was doing -----
    entries: Counter = Counter()  # times the block moved onto each cell
    for rows in tracked.values():
        for row in rows:
            if row["moved"]:
                entries[tuple(row["after"])] += 1
    events = []
    for index, box in enumerate(boxes):
        if regions[index]["kind"] != "rare":
            continue
        for seed, row, cells in hits[index]:
            size = (box[2] - box[0] + 1) * (box[3] - box[1] + 1)
            event = {
                "region": regions[index]["id"], "rows": [box[0], box[2]], "cols": [box[1], box[3]],
                "seed": seed, "step": row["step"], "action": row["action"], "cells_changed": int(len(cells)),
                "block_before": _pos(row["before"]), "block_after": _pos(row["after"]),
                "block_move": _move_kind(row, step_length),
            }
            if size <= MAX_GRID_CELLS:
                event["values_before"] = _hex_rows(row["frame_before"], box)
                event["values_after"] = _hex_rows(row["frame_after"], box)
            else:
                pairs = Counter((int(row["frame_before"][r, c]), int(row["frame_after"][r, c])) for r, c in cells)
                event["value_changes"] = [{"from": a, "to": b, "cells": n} for (a, b), n in pairs.most_common(6)]
            if row["entered"] is not None:
                event["cell_stepped_onto_before"] = ["".join(format(int(v), "x") for v in r) for r in row["entered"]]
            events.append(event)
    events.sort(key=lambda e: (e["seed"], e["step"], e["region"]))
    evidence["rare_events"] = events

    links = []
    for region in regions:
        if region["kind"] != "rare":
            continue
        mine = [e for e in events if e["region"] == region["id"]]
        by_cell: Counter = Counter()
        elsewhere = 0
        for event in mine:
            if event["block_move"] == "moved" and event["block_after"] is not None:
                by_cell[tuple(event["block_after"])] += 1
            else:
                elsewhere += 1
        links.append({
            "region": region["id"], "rows": region["rows"], "cols": region["cols"], "events": len(mine),
            "after_block_entered_cell": [
                {"cell": list(cell), "times_entered": entries[cell], "times_change_followed": n}
                for cell, n in sorted(by_cell.items(), key=lambda kv: (-kv[1], kv[0]))
            ],
            "events_without_a_normal_move": elsewhere,
        })
    evidence["links"] = links
    rare_seeds = {e["seed"] for e in events}

    # ---- A: movement ------------------------------------------------------
    visits: Counter = Counter()
    floor: Counter = Counter()
    for episode in loaded:
        seed = episode["seed"]
        rows = tracked[seed]
        path: list[list[int]] = []
        blocked: Counter = Counter()
        counts = Counter()
        for row in rows:
            kind = _move_kind(row, step_length)
            counts[kind] += 1
            if not path and row["before"] is not None:
                path.append(_pos(row["before"]))
                visits[tuple(row["before"])] += 1
            if row["moved"]:
                path.append(_pos(row["after"]))
                visits[tuple(row["after"])] += 1
                vacated = block.cells(*row["before"])
                for value in row["frame_after"][vacated[:, 0], vacated[:, 1]]:
                    floor[int(value)] += 1
            elif kind == "blocked":
                blocked[(row["action"], tuple(row["before"]))] += 1
            evidence["per_step"].append({
                "seed": seed, "step": row["step"], "turn": row["turn"], "action": row["action"],
                "block_before": _pos(row["before"]), "block_after": _pos(row["after"]), "move": kind,
                "cells_changed": row["n_changed"], "cells_changed_outside_block": int(len(row["other"])),
                "regions_changed": [regions[i]["id"] for i, box in enumerate(boxes) if len(_in_box(row["other"], box))]
                if len(row["other"]) else [],
            })
        final = next((row["after"] for row in reversed(rows) if row["after"] is not None), None)
        evidence["episodes"].append({
            "seed": seed, "steps": len(rows), "moved": counts["moved"], "blocked": counts["blocked"],
            "jumps": counts["jump"], "cells_visited": len({tuple(p) for p in path}),
            "start": path[0] if path else None, "final": _pos(final), "path": path,
            "blocked_moves": [{"action": a, "at": list(p), "times": n} for (a, p), n in blocked.most_common(6)],
            "rare_changes": sum(1 for e in events if e["seed"] == seed),
        })
    evidence["visits"] = [{"cell": list(cell), "times": n} for cell, n in sorted(visits.items(), key=lambda kv: (-kv[1], kv[0]))]
    evidence["moved_without_rare_change"] = sorted(
        e["seed"] for e in evidence["episodes"] if e["moved"] and e["seed"] not in rare_seeds
    )

    # Open cells never visited: cells one normal move from a visited or open
    # cell, where the first frame shows only what the block leaves behind.
    never: list[list[int]] = []
    if floor and step_vectors and loaded and loaded[0]["transitions"]:
        floor_values = {value for value, n in floor.items() if n >= 0.05 * sum(floor.values())}
        first = loaded[0]["transitions"][0]["before"]
        seen = set(visits)
        frontier = list(seen)
        open_cells: set[tuple[int, int]] = set()
        while frontier:
            r, c = frontier.pop()
            for dr, dc in step_vectors:
                nxt = (r + dr, c + dc)
                if nxt in seen or nxt in open_cells:
                    continue
                if not (0 <= nxt[0] <= first.shape[0] - block.height and 0 <= nxt[1] <= first.shape[1] - block.width):
                    continue
                cells = block.cells(*nxt)
                if all(int(v) in floor_values for v in first[cells[:, 0], cells[:, 1]]):
                    open_cells.add(nxt)
                    frontier.append(nxt)
        never = [list(p) for p in sorted(open_cells)]
    evidence["open_cells_never_visited"] = never
    return evidence


def _move_kind(row: dict[str, Any], step_length: int | None) -> str:
    if row["before"] is None or row["after"] is None:
        return "unknown"
    if not row["moved"]:
        return "blocked" if row["action"].startswith("ACTION") else "none"
    length = abs(row["after"][0] - row["before"][0]) + abs(row["after"][1] - row["before"][1])
    return "moved" if length == step_length and row["action"].startswith("ACTION") else "jump"


# ---------------------------------------------------------------------------
# Report section (what the Meta LLM reads) and the per-step file
# ---------------------------------------------------------------------------


def _cell(point: Any) -> str:
    return "?" if point is None else f"({point[0]},{point[1]})"


def _path_text(path: list[list[int]]) -> str:
    shown = " > ".join(_cell(p) for p in path[:MAX_PATH_POINTS])
    if len(path) > MAX_PATH_POINTS:
        shown += f" > ... ({len(path) - MAX_PATH_POINTS} more positions; last {_cell(path[-1])})"
    return shown


def render(evidence: dict[str, Any], version: str = "") -> str:
    """The Frame evidence section of the Analyze report. Observations only."""
    head = (f"FRAME EVIDENCE{' for ' + version if version else ''} ({evidence['n_episodes']} episodes, "
            f"{evidence['n_steps']} steps). Measured by plain code from the saved frames, by comparing each "
            "frame with the one before it. Positions are (row, col); row 0 is the top.")
    block = evidence.get("block")
    if not block:
        return head + "\n" + evidence.get("note", "no moving block was found in the frames")
    lines = [
        head,
        f"The block that moves when the player acts is {block['height']}x{block['width']} cells "
        f"(pattern, one hex digit per cell: {' / '.join(block['pattern'])}). Its position is its top-left "
        f"cell. A normal move shifts it {block['typical_move_cells']} cells.",
        "",
        "A. PLAYER MOVEMENT",
    ]
    for episode in evidence["episodes"]:
        lines.append(
            f"- seed {episode['seed']}: {episode['steps']} steps: {episode['moved']} moved the block, "
            f"{episode['blocked']} were blocked (action taken, block did not move), {episode['jumps']} jump(s) "
            f"(block re-appeared elsewhere); {episode['cells_visited']} cells visited; start "
            f"{_cell(episode['start'])}, final {_cell(episode['final'])}"
        )
        lines.append(f"    path: {_path_text(episode['path'])}")
        if episode["blocked_moves"]:
            lines.append("    blocked most: " + ", ".join(
                f"{b['action']} at {_cell(b['at'])} x{b['times']}" for b in episode["blocked_moves"]))
    lines.append("- all episodes, times the block was on each cell: " + ", ".join(
        f"{_cell(v['cell'])} {v['times']}" for v in evidence["visits"]))
    never = evidence["open_cells_never_visited"]
    lines.append("- open cells never visited (one normal move from a visited or open cell, showing only what "
                 "the block leaves behind): " + (", ".join(_cell(p) for p in never) if never else "none"))

    lines += ["", "B. OTHER ON-SCREEN CHANGES (cells that changed and are not the block's old or new position)"]
    regular = [r for r in evidence["regions"] if r["kind"] == "regular"]
    rare = [r for r in evidence["regions"] if r["kind"] == "rare"]
    for region in regular:
        lines.append(
            f"- regular: rows {region['rows'][0]}-{region['rows'][1]}, cols {region['cols'][0]}-"
            f"{region['cols'][1]} changed on {region['steps_changed']} of {evidence['changing_steps']} steps "
            f"that changed anything ({region['share_of_changing_steps']:.0%}); usually "
            f"{region['typical_cells_per_change']} cells at a time"
        )
    if not regular:
        lines.append("- regular: none")
    events = evidence["rare_events"]
    if not events:
        lines.append("- rare: none")
    else:
        lines.append(f"- rare: {len(events)} change(s) in {len(rare)} region(s):")
        for region in rare:
            lines.append(f"    {region['id']}: rows {region['rows'][0]}-{region['rows'][1]}, cols "
                         f"{region['cols'][0]}-{region['cols'][1]}: changed on {region['steps_changed']} step(s)")
        for event in events[:MAX_EVENTS_SHOWN]:
            lines.append(_event_text(event))
        if len(events) > MAX_EVENTS_SHOWN:
            lines.append(f"    ... {len(events) - MAX_EVENTS_SHOWN} more rare changes, counted in part C")

    lines += ["", "C. RARE CHANGES AND THE BLOCK'S POSITION"]
    if not events:
        lines.append("- no rare change in these episodes")
    for link in evidence["links"]:
        lines.append(f"- {link['region']} (rows {link['rows'][0]}-{link['rows'][1]}, cols {link['cols'][0]}-"
                     f"{link['cols'][1]}), {link['events']} change(s):")
        for item in link["after_block_entered_cell"]:
            lines.append(f"    the block entered {_cell(item['cell'])} on {item['times_entered']} step(s) in "
                         f"all episodes; this region changed on {item['times_change_followed']} of them")
        if link["events_without_a_normal_move"]:
            lines.append(f"    {link['events_without_a_normal_move']} change(s) came on steps where the block "
                         "did not make a normal move (blocked, jumped, or restarted)")
    quiet = evidence["moved_without_rare_change"]
    lines.append("- episodes where the block moved and no rare change happened: "
                 + (", ".join(f"seed {s}" for s in quiet) if quiet else "none"))
    return "\n".join(lines)


def _event_text(event: dict[str, Any]) -> str:
    move = {"moved": "moved", "blocked": "did not move", "jump": "jumped", "none": "did not move",
            "unknown": "position unknown"}[event["block_move"]]
    text = (f"    {event['region']} seed {event['seed']} step {event['step']}: after {event['action']}, block "
            f"{_cell(event['block_before'])} -> {_cell(event['block_after'])} ({move}); "
            f"{event['cells_changed']} cells changed")
    if "values_before" in event:
        text += f"; values before {'/'.join(event['values_before'])} after {'/'.join(event['values_after'])}"
    else:
        text += "; " + ", ".join(f"{c['cells']} cells {c['from']:x}->{c['to']:x}" for c in event["value_changes"])
    if event.get("cell_stepped_onto_before"):
        text += f"; the cell stepped onto held {'/'.join(event['cell_stepped_onto_before'])} before"
    return text


STEP_COLUMNS = ("seed", "step", "turn", "action", "block_before", "block_after", "move", "cells_changed",
                "cells_changed_outside_block", "regions_changed")


def write_per_step(evidence: dict[str, Any], trajectory_paths: dict[int, str]) -> list[str]:
    """The full per-step table, one CSV next to each trajectory."""
    written = []
    for seed, path in trajectory_paths.items():
        out = os.path.splitext(path)[0] + ".frame_steps.csv"
        with open(out, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(STEP_COLUMNS)
            for row in evidence["per_step"]:
                if row["seed"] != seed:
                    continue
                writer.writerow([
                    row["seed"], row["step"], row["turn"], row["action"],
                    "" if row["block_before"] is None else f"{row['block_before'][0]},{row['block_before'][1]}",
                    "" if row["block_after"] is None else f"{row['block_after'][0]},{row['block_after'][1]}",
                    row["move"], row["cells_changed"], row["cells_changed_outside_block"],
                    " ".join(row["regions_changed"]),
                ])
        written.append(out.replace(os.sep, "/"))
    return written
