"""Spatial visualisation of agent control: where the controlled object went.

The action tape (`analysis/figures.py`) shows *when* the agent acted and *what*
it pressed. It cannot show whether those actions achieved anything in space.
This module answers the complementary question -- *where did the thing it
controls actually go?* -- which is what makes a control failure legible: a
fixation loop and a purposeful approach produce very different pictures even
when both end in "unsolved".

Two outputs:

- `figure_movement_traces()`  a static grid of panels, one per (round, seed),
  with the mover's path drawn over the board and coloured by step.
- `write_movement_gif()`      an animated replay of one episode.

Both read only the committed `.npy` frames and trajectory JSONL, so they need
no environment access and no re-run.
"""

from __future__ import annotations

import json
import os
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D

from analysis.approach import COLOUR_ROLES, centroid_of, episode_path
from analysis.figures import (
    FIG_DIR,
    SEQUENTIAL,
    SURFACE,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    _save,
)
from harness.model import _PALETTE_RGB
from harness.trajectory import frames_path, trajectory_path

# Accent colours for annotation, kept off the sequential time ramp so they
# never read as "a point in time".
TARGET_COLOUR = "#e34948"
START_COLOUR = "#1baf7a"


def load_episode(round_index: int, game_id: str, seed: int):
    """Return (frames, records) for one episode, or (None, None) if absent."""
    fpath = frames_path(round_index, game_id, seed)
    tpath = trajectory_path(round_index, game_id, seed)
    if not os.path.exists(fpath) or not os.path.exists(tpath):
        return None, None
    frames = np.load(fpath)
    records = [json.loads(l) for l in open(tpath, encoding="utf-8")]
    return frames, records


def render_board(grid: np.ndarray) -> np.ndarray:
    """Colour grid -> RGB image using the ARC palette."""
    height, width = grid.shape
    rgb = np.zeros((height, width, 3), dtype=np.uint8)
    for value in np.unique(grid):
        rgb[grid == value] = _PALETTE_RGB.get(int(value), (80, 80, 80))
    return rgb


def mover_path(
    frames: np.ndarray, short_id: str
) -> tuple[list[tuple[float, float]], tuple[float, float] | None]:
    """Centroid of the controlled object per frame, plus the target position.

    Delegates to analysis.approach so the picture and the reported metric can
    never disagree -- they did once, and the figure was the one telling the
    truth.
    """
    return episode_path(frames, short_id)


def _draw_panel(axes, frames, path, target, title: str) -> None:
    board = render_board(np.asarray(frames[0]))
    # Wash the board out so the path reads as the figure's subject and the
    # board as context, rather than the two competing.
    axes.imshow(board, interpolation="nearest")
    axes.imshow(
        np.ones_like(board) * 255, interpolation="nearest", alpha=0.55
    )

    if len(path) >= 2:
        points = np.array([[c, r] for r, c in path])  # (x=col, y=row)
        segments = np.concatenate(
            [points[:-1, None, :], points[1:, None, :]], axis=1
        )
        collection = LineCollection(
            segments,
            cmap=SEQUENTIAL,
            norm=plt.Normalize(0, len(path)),
            linewidth=2.0,
            alpha=0.95,
        )
        collection.set_array(np.arange(len(segments)))
        axes.add_collection(collection)

    if path:
        axes.plot(
            path[0][1], path[0][0], "o", markersize=7,
            markerfacecolor="none", markeredgecolor=START_COLOUR,
            markeredgewidth=2, zorder=5,
        )
        axes.plot(
            path[-1][1], path[-1][0], "s", markersize=7,
            color="#0d366b", zorder=5,
        )
    if target is not None:
        axes.plot(
            target[1], target[0], "X", markersize=11, color=TARGET_COLOUR,
            markeredgecolor="white", markeredgewidth=1.2, zorder=6,
        )

    axes.set_title(title, fontsize=9, color=TEXT_PRIMARY, loc="left")
    axes.set_xlim(0, frames[0].shape[1] - 1)
    axes.set_ylim(frames[0].shape[0] - 1, 0)
    axes.set_xticks([])
    axes.set_yticks([])
    for spine in axes.spines.values():
        spine.set_color("#e4e3df")


def figure_movement_traces(
    game_id: str = "ls20-9607627b",
    seeds: tuple[int, ...] = (0, 1, 2),
    rounds: tuple[int, ...] = (0, 1),
) -> str:
    """One panel per (round, seed): the mover's path over the board."""
    short_id = game_id.split("-", 1)[0]
    figure, axes_grid = plt.subplots(
        len(rounds),
        len(seeds),
        figsize=(3.1 * len(seeds), 3.4 * len(rounds)),
        facecolor=SURFACE,
        squeeze=False,
    )

    for row, round_index in enumerate(rounds):
        for col, seed in enumerate(seeds):
            axes = axes_grid[row][col]
            frames, records = load_episode(round_index, game_id, seed)
            if frames is None:
                axes.text(
                    0.5, 0.5, "no data", ha="center", va="center",
                    fontsize=9, color=TEXT_SECONDARY, transform=axes.transAxes,
                )
                axes.set_xticks([])
                axes.set_yticks([])
                continue
            path, target = mover_path(frames, short_id)
            closest = None
            if target is not None and path:
                closest = min(
                    abs(r - target[0]) + abs(c - target[1]) for r, c in path
                )
            label = f"Round {round_index} · seed {seed}"
            if closest is not None:
                label += f"  ·  closest {closest:.1f}"
            _draw_panel(axes, frames, path, target, label)

    handles = [
        Line2D([], [], marker="o", linestyle="none", markerfacecolor="none",
               markeredgecolor=START_COLOUR, markersize=7, label="start"),
        Line2D([], [], marker="s", linestyle="none", color="#0d366b",
               markersize=7, label="end"),
        Line2D([], [], marker="X", linestyle="none", color=TARGET_COLOUR,
               markersize=9, label="target"),
    ]
    figure.legend(
        handles=handles, frameon=False, fontsize=8, ncol=3,
        loc="lower center", bbox_to_anchor=(0.5, -0.015),
    )

    mappable = plt.cm.ScalarMappable(cmap=SEQUENTIAL, norm=plt.Normalize(0, 1))
    bar = figure.colorbar(
        mappable, ax=axes_grid, fraction=0.025, pad=0.015, ticks=[0, 1]
    )
    bar.ax.set_yticklabels(["first step", "last step"], fontsize=7,
                           color=TEXT_SECONDARY)
    bar.outline.set_visible(False)

    figure.suptitle(
        f"Where the controlled object actually went ({short_id.upper()}, Level 1)",
        fontsize=12, color=TEXT_PRIMARY, x=0.02, ha="left",
    )
    return _save(figure, "movement_traces.png")


def write_movement_gif(
    round_index: int,
    seed: int,
    game_id: str = "ls20-9607627b",
    stride: int = 2,
    scale: int = 6,
    frame_ms: int = 90,
) -> str | None:
    """Animated replay of one episode, with the mover's recent trail drawn on.

    `stride` subsamples frames so a 200-step episode stays a reasonable file
    size; `scale` upscales the 64x64 board with nearest-neighbour so cells stay
    crisp.
    """
    from PIL import Image, ImageDraw

    short_id = game_id.split("-", 1)[0]
    frames, records = load_episode(round_index, game_id, seed)
    if frames is None:
        return None
    path, target = mover_path(frames, short_id)

    images: list[Image.Image] = []
    for index in range(0, len(frames), stride):
        board = render_board(np.asarray(frames[index]))
        image = Image.fromarray(board, mode="RGB").resize(
            (board.shape[1] * scale, board.shape[0] * scale), Image.NEAREST
        )
        draw = ImageDraw.Draw(image)

        # Trail of where the mover has been, fading into the past.
        trail = path[max(0, index - 40) : index + 1]
        if len(trail) >= 2:
            points = [((c + 0.5) * scale, (r + 0.5) * scale) for r, c in trail]
            draw.line(points, fill=(255, 255, 255), width=2)
        if index < len(path):
            r, c = path[index]
            x, y = (c + 0.5) * scale, (r + 0.5) * scale
            draw.ellipse(
                [x - scale, y - scale, x + scale, y + scale],
                outline=(255, 255, 255), width=2,
            )
        if target is not None:
            tr, tc = target
            x, y = (tc + 0.5) * scale, (tr + 0.5) * scale
            draw.line([x - scale, y - scale, x + scale, y + scale],
                      fill=(227, 73, 72), width=2)
            draw.line([x - scale, y + scale, x + scale, y - scale],
                      fill=(227, 73, 72), width=2)

        action = ""
        if index < len(records):
            action = str(records[index].get("action", ""))
        draw.text((4, 4), f"R{round_index} seed {seed}  step {index}  {action}",
                  fill=(255, 255, 255))
        images.append(image)

    if not images:
        return None
    os.makedirs(FIG_DIR, exist_ok=True)
    out = os.path.join(FIG_DIR, f"movement_r{round_index}_seed{seed}.gif")
    images[0].save(
        out, save_all=True, append_images=images[1:],
        duration=frame_ms, loop=0, optimize=True,
    )
    return out


if __name__ == "__main__":
    print("wrote", figure_movement_traces())
    for round_index in (0, 1):
        out = write_movement_gif(round_index, 0)
        if out:
            size_kb = os.path.getsize(out) // 1024
            print(f"wrote {out} ({size_kb} KB)")
