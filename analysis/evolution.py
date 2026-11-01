"""Figures for issue #9's evolution run, built from archive.json.

Reuses #8's result-image code rather than re-implementing it: the styling,
palette and save conventions of analysis/figures.py, the approach-distance
metric of analysis/approach.py, and the movement panel of analysis/movement.py.

- score_per_round.png    every version's episode scores and mean, by round,
                         coloured and shaped by gate decision, with the
                         current parent's mean as a step line
- approach_by_version.png  #8's closest-approach curves, one panel per version
- movement_by_version.png  #8's movement traces, one row per version

Gate decision is encoded twice (colour and marker shape) and every mean is
direct-labelled: the third palette slot is below 3:1 contrast on the surface
(validator WARN), so colour never carries identity alone.
"""

from __future__ import annotations

import json
import os
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D

from analysis.approach import approach_curve
from analysis.figures import (
    ROUND_COLOUR,
    SEQUENTIAL,
    SLOT3,
    SURFACE,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    _style,
)
from analysis.movement import START_COLOUR, TARGET_COLOUR, _draw_panel, mover_path
from evolve.action_loop import load_frames

SHORT_ID = "ls20"

# Fixed slot order from #8's palette: slot 1 blue, slot 2 orange, slot 3 green.
DECISION_STYLE = {
    "accepted": {"colour": ROUND_COLOUR[0], "marker": "o", "label": "accepted"},
    "rejected": {"colour": ROUND_COLOUR[1], "marker": "X", "label": "rejected"},
    "baseline": {"colour": SLOT3, "marker": "s", "label": "baseline (v0)"},
}


def _decision(entry: dict[str, Any]) -> str:
    return (entry.get("gate") or {}).get("decision", "baseline")


def _save(figure: plt.Figure, out_dir: str, name: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, name)
    figure.savefig(path, dpi=160, bbox_inches="tight", facecolor=SURFACE)
    plt.close(figure)
    return path


def load_archive(root: str) -> dict[str, Any]:
    with open(os.path.join(root, "archive.json"), encoding="utf-8") as handle:
        return json.load(handle)


def figure_score_per_round(archive: dict[str, Any], out_dir: str) -> str:
    versions = archive["versions"]
    figure, axes = plt.subplots(figsize=(8.6, 4.6), facecolor=SURFACE)
    _style(axes, grid_axis="y")

    # Parent mean as a step line: the score the next child has to beat.
    parent_means = []
    for round_info in archive["rounds"]:
        parent = next((v for v in versions if v["version"] == round_info["parent_after"]), None)
        if parent is not None:
            parent_means.append((round_info["round"], parent["score_mean"]))
    if parent_means:
        xs, ys = zip(*parent_means)
        axes.step(xs, ys, where="post", color=TEXT_SECONDARY, linewidth=1.5,
                  linestyle=(0, (4, 3)), zorder=2, label="parent's mean (score to beat)")

    top = 0.0
    for entry in versions:
        decision = _decision(entry)
        style = DECISION_STYLE[decision]
        x = entry["round"]
        scores = [e["score"] for e in entry["episodes"]]
        top = max(top, *scores)
        jitter = np.linspace(-0.12, 0.12, len(scores)) if len(scores) > 1 else [0.0]
        axes.scatter(
            [x + j for j in jitter], scores, s=26, color=style["colour"], alpha=0.45,
            edgecolors="none", zorder=3,
        )
        axes.scatter(
            [x], [entry["score_mean"]], s=110, marker=style["marker"], color=style["colour"],
            edgecolors=SURFACE, linewidths=2, zorder=4,
        )
        axes.annotate(
            f"{entry['version']} {entry['score_mean']:.3f}",
            (x, entry["score_mean"]), textcoords="offset points", xytext=(9, 4),
            fontsize=8, color=TEXT_PRIMARY,
        )

    for round_info in archive["rounds"]:
        if round_info.get("child") is None:
            axes.annotate("no valid edits", (round_info["round"], 0.0), textcoords="offset points",
                          xytext=(0, 6), ha="center", fontsize=8, color=TEXT_SECONDARY)

    axes.axhline(0.5, color=TEXT_SECONDARY, linewidth=0.8, zorder=1)
    axes.annotate("a Level-1 clear scores >= 0.5", (1.0, 0.5), xycoords=("axes fraction", "data"),
                  textcoords="offset points", xytext=(-2, 4), ha="right", fontsize=7,
                  color=TEXT_SECONDARY)

    rounds = sorted({r["round"] for r in archive["rounds"]})
    axes.set_xticks(rounds)
    axes.set_xticklabels([f"round {r}" for r in rounds], fontsize=8)
    axes.set_ylim(0, max(0.55, top + 0.08))
    axes.set_ylabel("Episode score (dots) and version mean (large marks)", fontsize=9, color=TEXT_PRIMARY)
    axes.set_title(
        f"Score per round, {SHORT_ID.upper()} Level 1 ({archive['config']['episodes_per_round']} "
        "episodes per version)",
        fontsize=11, color=TEXT_PRIMARY, loc="left",
    )
    handles = [
        Line2D([], [], marker=s["marker"], linestyle="none", color=s["colour"], markersize=8,
               label=s["label"])
        for s in DECISION_STYLE.values()
    ] + [Line2D([], [], color=TEXT_SECONDARY, linestyle=(0, (4, 3)), label="parent's mean (score to beat)")]
    axes.legend(handles=handles, frameon=False, fontsize=8, loc="upper center",
                bbox_to_anchor=(0.5, -0.09), ncol=4)
    return _save(figure, out_dir, "score_per_round.png")


def figure_approach_by_version(archive: dict[str, Any], out_dir: str) -> str:
    versions = archive["versions"]
    n = len(versions)
    cols = min(3, n)
    rows = int(np.ceil(n / cols))
    figure, grid = plt.subplots(rows, cols, figsize=(3.6 * cols, 2.8 * rows), facecolor=SURFACE,
                                squeeze=False, sharey=True)
    for index, entry in enumerate(versions):
        axes = grid[index // cols][index % cols]
        _style(axes, grid_axis="both")
        style = DECISION_STYLE[_decision(entry)]
        for episode in entry["episodes"]:
            curve = approach_curve(load_frames(episode["frames"]), SHORT_ID)
            if not curve:
                continue
            axes.plot(range(len(curve)), curve, color=style["colour"], linewidth=2, alpha=0.85)
            axes.annotate(f"ep{episode['episode']} {curve[-1]:.1f}", (len(curve) - 1, curve[-1]),
                          textcoords="offset points", xytext=(3, 0), fontsize=6.5,
                          color=TEXT_SECONDARY, va="center")
        axes.set_title(f"{entry['version']} · {_decision(entry)} · mean {entry['score_mean']:.3f}",
                       fontsize=9, color=TEXT_PRIMARY, loc="left")
        axes.set_ylim(bottom=0)
        if index % cols == 0:
            axes.set_ylabel("best distance so far", fontsize=8, color=TEXT_PRIMARY)
        if index // cols == rows - 1:
            axes.set_xlabel("frame (one per action)", fontsize=8, color=TEXT_PRIMARY)
    for index in range(n, rows * cols):
        grid[index // cols][index % cols].set_visible(False)
    figure.suptitle(
        f"How close each episode got to the goal, per version ({SHORT_ID.upper()}, lower is better)",
        fontsize=11, color=TEXT_PRIMARY, x=0.02, ha="left",
    )
    figure.tight_layout()
    return _save(figure, out_dir, "approach_by_version.png")


def figure_movement_by_version(archive: dict[str, Any], out_dir: str) -> str:
    versions = archive["versions"]
    n_eps = max(len(v["episodes"]) for v in versions)
    figure, grid = plt.subplots(len(versions), n_eps, figsize=(2.9 * n_eps, 3.0 * len(versions)),
                                facecolor=SURFACE, squeeze=False)
    for row, entry in enumerate(versions):
        for col in range(n_eps):
            axes = grid[row][col]
            if col >= len(entry["episodes"]):
                axes.set_visible(False)
                continue
            episode = entry["episodes"][col]
            frames = load_frames(episode["frames"])
            path, target = mover_path(frames, SHORT_ID)
            label = f"{entry['version']} ({_decision(entry)}) · ep{episode['episode']}"
            if episode.get("closest_approach") is not None:
                label += f" · closest {episode['closest_approach']:.1f}"
            if episode.get("solved"):
                label += " · CLEARED"
            _draw_panel(axes, frames, path, target, label)
    handles = [
        Line2D([], [], marker="o", linestyle="none", markerfacecolor="none",
               markeredgecolor=START_COLOUR, markersize=7, label="start"),
        Line2D([], [], marker="s", linestyle="none", color="#0d366b", markersize=7, label="end"),
        Line2D([], [], marker="X", linestyle="none", color=TARGET_COLOUR, markersize=9, label="target"),
    ]
    figure.legend(handles=handles, frameon=False, fontsize=8, ncol=3, loc="lower center",
                  bbox_to_anchor=(0.5, -0.005))
    mappable = plt.cm.ScalarMappable(cmap=SEQUENTIAL, norm=plt.Normalize(0, 1))
    bar = figure.colorbar(mappable, ax=grid, fraction=0.025, pad=0.015, ticks=[0, 1])
    bar.ax.set_yticklabels(["first step", "last step"], fontsize=7, color=TEXT_SECONDARY)
    bar.outline.set_visible(False)
    figure.suptitle(f"Where the controlled object went, per version ({SHORT_ID.upper()}, Level 1)",
                    fontsize=12, color=TEXT_PRIMARY, x=0.02, ha="left")
    return _save(figure, out_dir, "movement_by_version.png")


def build_all(root: str) -> list[str]:
    archive = load_archive(root)
    out_dir = os.path.join(root, "figures")
    return [
        figure_score_per_round(archive, out_dir),
        figure_approach_by_version(archive, out_dir),
        figure_movement_by_version(archive, out_dir),
    ]


if __name__ == "__main__":
    import sys

    for written in build_all(sys.argv[1] if len(sys.argv) > 1 else os.path.join("results", "evolve")):
        print("wrote", written)
