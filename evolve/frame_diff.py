"""Frame-diff code shared by the action record, the state-change check and
the frame evidence (issue #16).

Three things are built here from pairs of frames, with no game knowledge and
no model:

- change regions: the cells that differ between two frames, grouped into
  clusters (cells within REGION_GAP of each other are one cluster). The frame
  evidence (#14/#15) groups changes the same way;
- the every-step detector: the regions that change after (almost) every
  action, whatever the action was, such as a step counter. They are listed
  once and left out of each action's line;
- the action record (#16 change 5): per action, what changed on screen.

Every-step regions are found per episode, from the steps so far. Pooling every
changed cell, as the frame evidence does after the fact, does not work for
this: in vc33 the step bar (row 0) sits one row above the columns a button
click moves, so the pooled region holds both (WORK_LOG-15). Instead each
changing step contributes its smallest cluster to a pool (on a click that does
nothing else that is the counter), and a pooled region is every-step when it
changed on at least EVERY_STEP_SHARE of the actions, after at least
EVERY_STEP_MIN_ACTIONS actions, and on at least two different actions (so a
tile clicked over and over is not taken for a counter).
"""

from __future__ import annotations

import copy
from collections import Counter
from collections.abc import Sequence
from typing import Any

import numpy as np

REGION_GAP = 2               # changed cells this close (Chebyshev) are one cluster
SEARCH = 12                  # largest shift (cells, per axis) tried when finding a moved block
MIN_BLOCK_CELLS = 4          # a moving patch smaller than this is not taken for a block
EVERY_STEP_SHARE = 0.9       # a region changing on at least this share of actions is every-step
EVERY_STEP_MIN_ACTIONS = 3   # ... once there have been at least this many actions
MAX_VALUE_PAIRS = 3          # value changes (before -> after) kept per region

Box = tuple[int, int, int, int]  # (r0, c0, r1, c1), inclusive


# ---------------------------------------------------------------------------
# Change regions
# ---------------------------------------------------------------------------


def clusters(cells: set[tuple[int, int]]) -> list[list[tuple[int, int]]]:
    """The clusters of `cells`: cells within REGION_GAP of each other are one."""
    remaining = set(cells)
    out = []
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
        out.append(cluster)
    return out


def bbox(cells: list[tuple[int, int]]) -> Box:
    rs, cs = [p[0] for p in cells], [p[1] for p in cells]
    return (min(rs), min(cs), max(rs), max(cs))


def regions(cells: set[tuple[int, int]]) -> list[Box]:
    """Bounding boxes of the clusters of `cells`, top-left first."""
    return sorted(bbox(cluster) for cluster in clusters(cells))


def changed_cells(before: np.ndarray, after: np.ndarray) -> set[tuple[int, int]]:
    rows, cols = np.nonzero(before != after)
    return set(zip(rows.tolist(), cols.tolist()))


def in_box(cell: tuple[int, int], box: Box, margin: int = 0) -> bool:
    return box[0] - margin <= cell[0] <= box[2] + margin and box[1] - margin <= cell[1] <= box[3] + margin


def grow(box: Box) -> Box:
    """`box` extended by REGION_GAP along its long side (both sides if square).

    A counter grows at its edge, one or two cells past what the box has seen.
    Only along its length: vc33's bar is row 0 and the column a button moves
    starts at row 1, so growing it across would take in the column's top.
    """
    r0, c0, r1, c1 = box
    height, width = r1 - r0 + 1, c1 - c0 + 1
    if width > height:
        return (r0, c0 - REGION_GAP, r1, c1 + REGION_GAP)
    if height > width:
        return (r0 - REGION_GAP, c0, r1 + REGION_GAP, c1)
    return (r0 - REGION_GAP, c0 - REGION_GAP, r1 + REGION_GAP, c1 + REGION_GAP)


def split_every_step(cells: set[tuple[int, int]], boxes: list[Box]) -> tuple[set, list[list[tuple[int, int]]]]:
    """(cells that belong to every-step regions, clusters of the rest)."""
    grown = [grow(box) for box in boxes]
    every = {cell for cell in cells if any(in_box(cell, box) for box in grown)}
    return every, sorted(clusters(cells - every), key=bbox)


def moved_patch(before: np.ndarray, after: np.ndarray) -> tuple[np.ndarray, tuple[int, int]] | None:
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


# ---------------------------------------------------------------------------
# The action record
# ---------------------------------------------------------------------------


class ActionRecorder:
    """What each action of one episode changed on screen (#16 change 5).

    `add` is called once per action with the frame before and after it, in
    order. Each record is fixed when it is made: it uses the every-step
    regions known from the actions before it. `known_every_step` are regions
    found elsewhere (the state-change check passes the ones found in the
    parent's episodes, so a state restored at step 0 already knows the
    counter).
    """

    def __init__(self, known_every_step: list[Box] | tuple = ()) -> None:
        self.records: list[dict[str, Any]] = []
        self.known = [tuple(int(v) for v in box) for box in known_every_step]
        self.excluded: list[set[tuple[int, int]]] = []  # per action: cells left out as every-step
        self._steps: list[tuple[tuple, np.ndarray]] = []  # (action key, changed cells) per action
        self._pool: set[tuple[int, int]] = set()

    def every_step(self) -> list[Box]:
        """Every-step regions as of now: the known ones and those found here."""
        found = []
        n = len(self._steps)
        if n >= EVERY_STEP_MIN_ACTIONS and self._pool:
            for box in regions(self._pool):
                keys = [key for key, cells in self._steps if _any_in_box(cells, box)]
                if len(keys) >= EVERY_STEP_SHARE * n and len(set(keys)) >= 2:
                    found.append(box)
        return self.known + [box for box in found if box not in self.known]

    def add(self, step: int, action: str, args: dict[str, Any] | None, before: np.ndarray,
            after: np.ndarray, game_over: bool = False, level_restarted: bool = False) -> dict[str, Any]:
        args = args or {}
        click = "x" in args and "y" in args
        record: dict[str, Any] = {"step": int(step), "action": action}
        if click:
            x, y = int(args["x"]), int(args["y"])
            record |= {"x": x, "y": y}
            if 0 <= y < before.shape[0] and 0 <= x < before.shape[1]:
                record["value_at_click"] = int(before[y, x])
        boxes = self.every_step()
        if before.shape != after.shape:
            cells: set[tuple[int, int]] = set()
            record |= {"changed": True, "n_changed": int(after.size), "regions": [], "frame_size_changed": True,
                       "every_step_cells": 0}
            every: set[tuple[int, int]] = set()
        else:
            cells = changed_cells(before, after)
            every, rest = split_every_step(cells, boxes)
            record |= {
                "changed": bool(rest),
                "n_changed": sum(len(cluster) for cluster in rest),
                "regions": [_region(cluster, before, after) for cluster in rest],
                "every_step_cells": len(every),
            }
            if not click and rest:
                found = moved_patch(before, after)
                if found is not None:
                    patch, shift = found
                    r0, c0 = (int(v) for v in patch.min(axis=0))
                    record |= {"block_before": [r0, c0], "block_after": [r0 + int(shift[0]), c0 + int(shift[1])]}
        if game_over:
            record["game_over"] = True
        if level_restarted:
            record["level_restarted"] = True
        self.records.append(record)
        self.excluded.append(every)
        # Detection state for later actions: this step's changed cells, and
        # for the pool its every-step cells or, while none are known, its
        # smallest cluster(s). Never both: a cluster that holds the counter's
        # next cell and a column next to it would join the two for good.
        key = (action, args.get("x"), args.get("y")) if click else (action,)
        self._steps.append((key, np.array(sorted(cells), dtype=np.int16).reshape(-1, 2)))
        if every:
            self._pool.update(every)
        elif cells:
            parts = clusters(cells)
            smallest = min(len(p) for p in parts)
            for part in parts:
                if len(part) == smallest:
                    self._pool.update(part)
        return record


def _any_in_box(cells: np.ndarray, box: Box) -> bool:
    if not len(cells):
        return False
    return bool(np.any((cells[:, 0] >= box[0]) & (cells[:, 0] <= box[2])
                       & (cells[:, 1] >= box[1]) & (cells[:, 1] <= box[3])))


def _region(cluster: list[tuple[int, int]], before: np.ndarray, after: np.ndarray) -> dict[str, Any]:
    r0, c0, r1, c1 = bbox(cluster)
    pairs = Counter((int(before[r, c]), int(after[r, c])) for r, c in cluster)
    return {"rows": [r0, r1], "cols": [c0, c1], "cells": len(cluster),
            "values": [[a, b, n] for (a, b), n in sorted(pairs.items(), key=lambda kv: (-kv[1], kv[0]))
                       [:MAX_VALUE_PAIRS]]}


class ActionLog(Sequence):
    """`action_log` in the sandbox: the episode's action records, read-only.

    Indexing returns copies, so code that changes an entry changes only its
    copy, and there is nothing to append to. (The sandbox refuses attributes
    starting with "_", so the list behind it cannot be reached.)
    """

    def __init__(self, records: list[dict[str, Any]]) -> None:
        self._records = records

    def __len__(self) -> int:
        return len(self._records)

    def __getitem__(self, index: Any) -> Any:
        if isinstance(index, slice):
            return [copy.deepcopy(r) for r in self._records[index]]
        return copy.deepcopy(self._records[index])

    def __repr__(self) -> str:
        return f"<action_log: {len(self._records)} records, read-only>"


# ---------------------------------------------------------------------------
# What the player reads
# ---------------------------------------------------------------------------


def _span(name: str, lo: int, hi: int) -> str:
    return f"{name} {lo}" if lo == hi else f"{name}s {lo}–{hi}"


def box_text(box: Box | list[int]) -> str:
    return f"{_span('row', box[0], box[2])}, {_span('col', box[1], box[3])}"


def record_line(record: dict[str, Any]) -> str:
    """One action, one line. Observations only."""
    if "x" in record:
        head = f"step {record['step']} · click ({record['x']}, {record['y']})"
        if "value_at_click" in record:
            head += f" on {record['value_at_click']}"
    else:
        head = f"step {record['step']} · {record['action']}"
    parts = [head]
    if record.get("frame_size_changed"):
        parts.append("frame size changed")
    elif not record["changed"]:
        parts.append("no change")
    else:
        parts.append(f"{record['n_changed']} cell{'s' if record['n_changed'] != 1 else ''} changed")
        shown = []
        for region in record["regions"][:3]:
            values = region["values"]
            if len(values) == 1:
                change = f"{values[0][0]}→{values[0][1]}"
            else:
                change = ", ".join(f"{a}→{b} ×{n}" for a, b, n in values)
            shown.append(f"{_span('row', *region['rows'])}, {_span('col', *region['cols'])} · {change}")
        if len(record["regions"]) > 3:
            shown.append(f"+{len(record['regions']) - 3} more regions")
        parts.append("; ".join(shown))
        if "block_before" in record:
            parts.append(f"block ({record['block_before'][0]}, {record['block_before'][1]})→"
                         f"({record['block_after'][0]}, {record['block_after'][1]})")
    if record.get("game_over"):
        parts.append("game over" + (", the harness restarted the level" if record.get("level_restarted") else ""))
    return " · ".join(parts)


def render(recorder: ActionRecorder, last_n: int = 20, max_locations: int = 40) -> str:
    """The ACTION RECORD block of the player's turn message."""
    records = recorder.records
    if not records:
        return "ACTION RECORD: no actions yet."
    lines = ["ACTION RECORD (what each action changed on screen, measured by comparing the frame before and "
             "after it; clicks as (x, y), the order action() takes them, \"on N\" = the cell's value before "
             "the click)"]
    every = recorder.every_step()
    lines.append("Changes every step (left out below): "
                 + ("; ".join(box_text(box) for box in every) if every else "none found"))
    shown = records[-last_n:]
    lines.append(f"Last {len(shown)} of {len(records)} actions:")
    lines.extend(record_line(r) for r in shown)

    clicks: Counter = Counter()
    clicks_changed: Counter = Counter()
    others: Counter = Counter()
    others_changed: Counter = Counter()
    for record in records:
        if "x" in record:
            where = (record["x"], record["y"])
            clicks[where] += 1
            clicks_changed[where] += bool(record["changed"])
        else:
            others[record["action"]] += 1
            others_changed[record["action"]] += bool(record["changed"])
    if clicks:
        ranked = sorted(clicks.items(), key=lambda kv: (-kv[1], kv[0]))
        items = [f"({x}, {y}) ×{n} ({clicks_changed[(x, y)]} changed)" for (x, y), n in ranked[:max_locations]]
        tail = ranked[max_locations:]
        if tail:
            items.append(f"... {len(tail)} more locations ({sum(n for _w, n in tail)} clicks, "
                         f"{sum(clicks_changed[w] for w, _n in tail)} changed)")
        lines.append(f"Clicks this episode: {sum(clicks.values())} on {len(clicks)} locations, "
                     f"{sum(clicks_changed.values())} changed something. By location: " + ", ".join(items))
    if others:
        lines.append("Other actions this episode: " + ", ".join(
            f"{name} ×{n} ({others_changed[name]} changed)" for name, n in sorted(others.items())))
    return "\n".join(lines)
