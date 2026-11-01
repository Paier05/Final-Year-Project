"""Closest-approach metric and figure.

Neither round solves Level 1 on ls20, so a binary solve rate cannot separate
them -- it is 0/3 both times. Distance from the agent-controlled object to the
goal object is the graded version of the same question, and it does separate
them.

The metric is Manhattan distance between the centroid of the mover and that of
the target, minimised over the episode, computed from the saved `.npy` frames.

Frames rather than the logged `objects` list, for two reasons: the object list
is capped at `observation.max_objects` for prompt size, and -- the case that
actually bit -- re-deriving the target position per step is wrong once the mover
reaches it and partly occludes it. The target is therefore read once from frame
0 as a stable reference. Using the object list instead put Round 1 seed 0 at 3.5
cells when it was really 1.5.

Colour roles are per game. For ls20 the mover is the teal/maroon band and the
target is the blue/black cluster; these were read off the trajectories, not
assumed, and a game without an entry here is skipped rather than guessed at.
"""

from __future__ import annotations

import glob
import json
import os
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from analysis.figures import (
    GRID,
    ROUND_COLOUR,
    SLOT3,
    SURFACE,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    _save,
    _style,
)

# game short id -> (mover colours, target colours)
COLOUR_ROLES: dict[str, tuple[tuple[int, ...], tuple[int, ...]]] = {
    "ls20": ((12,), (1, 0)),
}


def centroid_of(grid: np.ndarray, colours: tuple[int, ...]):
    """Pixel centroid of every cell whose colour is in `colours`."""
    mask = np.isin(grid, list(colours))
    if not mask.any():
        return None
    rows, cols = np.nonzero(mask)
    return float(rows.mean()), float(cols.mean())


def episode_path(frames: np.ndarray, short_id: str):
    """(mover centroid per frame, target centroid from frame 0)."""
    roles = COLOUR_ROLES.get(short_id)
    if roles is None:
        return [], None
    mover_colours, target_colours = roles
    path = []
    for grid in frames:
        point = centroid_of(np.asarray(grid), mover_colours)
        if point is not None:
            path.append(point)
    return path, centroid_of(np.asarray(frames[0]), target_colours)


def approach_curve(frames: np.ndarray, short_id: str) -> list[float]:
    """Running best (minimum so far) distance to the target, per frame."""
    path, target = episode_path(frames, short_id)
    if target is None:
        return []
    curve: list[float] = []
    best = None
    for row, col in path:
        distance = abs(row - target[0]) + abs(col - target[1])
        best = distance if best is None else min(best, distance)
        curve.append(best)
    return curve


def collect(round_index: int, short_id: str = "ls20") -> dict[int, list[float]]:
    out: dict[int, list[float]] = {}
    pattern = os.path.join(
        "data", "frames", f"round{round_index}", f"{short_id}-*", "*.npy"
    )
    for path in sorted(glob.glob(pattern)):
        seed = int(os.path.basename(path).split(".")[0])
        curve = approach_curve(np.load(path), short_id)
        if curve:
            out[seed] = curve
    return out


def figure_approach(short_id: str = "ls20") -> str:
    rounds = {r: collect(r, short_id) for r in (0, 1)}
    figure, axes = plt.subplots(figsize=(8.4, 4.6), facecolor=SURFACE)
    _style(axes, grid_axis="both")

    # Round 0 is dashed and drawn on top: the two rounds sit at identical
    # distances for long stretches, and a solid line would simply be hidden
    # under Round 1, making the baseline look absent rather than flat.
    styles = {0: {"linestyle": (0, (5, 3)), "zorder": 4}, 1: {"linestyle": "-", "zorder": 3}}
    placed: list[float] = []
    for round_index in (1, 0):
        per_seed = rounds.get(round_index, {})
        colour = ROUND_COLOUR.get(round_index, SLOT3)
        for index, (seed, curve) in enumerate(sorted(per_seed.items())):
            axes.plot(
                range(len(curve)),
                curve,
                color=colour,
                linewidth=2,
                alpha=0.9,
                label=f"Round {round_index}" if index == 0 else None,
                **styles[round_index],
            )
            # Nudge a label off any already placed within ~1.2 cells, so the
            # overlapping endpoints stay individually readable.
            y = curve[-1]
            offset = 0.0
            while any(abs((y + offset) - p) < 1.2 for p in placed):
                offset += 1.3
            placed.append(y + offset)
            axes.annotate(
                f"R{round_index} seed {seed}: {y:.1f}",
                (len(curve) - 1, y),
                textcoords="offset points",
                xytext=(8, offset * 7),
                fontsize=7,
                color=colour,
                va="center",
            )

    axes.set_xlabel("Step", fontsize=9, color=TEXT_PRIMARY)
    axes.set_ylabel(
        "Best distance to target so far\n(Manhattan, grid cells)",
        fontsize=9,
        color=TEXT_PRIMARY,
    )
    axes.set_title(
        f"How close the agent ever got to the goal ({short_id.upper()}, lower is better)",
        fontsize=11,
        color=TEXT_PRIMARY,
        loc="left",
    )
    axes.set_ylim(bottom=0)
    axes.legend(frameon=False, fontsize=8, loc="upper right")
    return _save(figure, "approach_distance.png")


def summary_table(short_id: str = "ls20") -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for round_index in (0, 1):
        for seed, curve in sorted(collect(round_index, short_id).items()):
            rows.append(
                {
                    "round": round_index,
                    "seed": seed,
                    "closest_approach": round(min(curve), 1),
                    "final_best": round(curve[-1], 1),
                    "steps": len(curve),
                }
            )
    return rows


if __name__ == "__main__":
    for row in summary_table():
        print(row)
    print("wrote", figure_approach())
