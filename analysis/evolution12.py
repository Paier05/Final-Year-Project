"""Figures for issue #12's run, from archive.json (+ #9 rescored).

Built on #8's figure code (analysis/figures.py: styling, palette, save
conventions), as #9's analysis/evolution.py was. One PNG per report picture:

- score_per_round.png   goal progress per version, by round: per-seed dots,
                        mean +- SD across seeds 1-5, gate decision by colour
                        AND marker shape, the parent's mean as a step line
- parts_per_round.png   the mean score split into its weighted goal parts
                        (stacked contributions sum to the mean score)
- cost_per_round.png    left: mean normalised cost split into its three
                        components; right: score vs cost per version, with
                        lines of equal gate score
- lineage.png           harness lineage v0 -> vN with each gate decision
- replay_<v>_seed<S>.png/.gif  one episode of the best version, key frames
                        with the rotation step marked
- vs_issue9.png         progress per round, this run vs #9 rescored, both v0
                        baselines marked

Palette: #8's categorical slots in fixed order (validated, dataviz skill:
slots 1-4 pass adjacent-pair CVD and normal-vision checks; aqua and yellow are
below 3:1 on the surface, so every mark that carries identity is also
direct-labelled or legend-labelled, and the report gives the numbers in
tables). One y-axis per panel.
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
from matplotlib.patches import FancyBboxPatch, Patch, Rectangle

from analysis.figures import ROUND_COLOUR, SLOT3, SURFACE, TEXT_PRIMARY, TEXT_SECONDARY, _style
from evolve.action_loop import load_frames, read_records
from evolve.goal_score import PARTS, level1_maze, states_from_records
from harness.model import _PALETTE_RGB

SLOT4 = "#eda100"
PART_COLOUR = {"position": ROUND_COLOUR[0], "rotation": ROUND_COLOUR[1], "shape": SLOT3, "colour": SLOT4}
COST_COLOUR = {"tokens": ROUND_COLOUR[0], "llm_calls": ROUND_COLOUR[1], "env_steps": SLOT3}
COST_LABEL = {"tokens": "tokens / 1.2M", "llm_calls": "LLM calls / 200", "env_steps": "env steps / 200"}
DECISION_STYLE = {
    "accepted": {"colour": ROUND_COLOUR[0], "marker": "o", "label": "accepted"},
    "rejected": {"colour": ROUND_COLOUR[1], "marker": "X", "label": "rejected"},
    "baseline": {"colour": SLOT3, "marker": "s", "label": "baseline (v0)"},
}
RUN_COLOUR = {"#12": ROUND_COLOUR[0], "#9": ROUND_COLOUR[1]}


def _decision(entry: dict[str, Any]) -> str:
    return (entry.get("gate") or {}).get("decision", "baseline")


def _save(figure: plt.Figure, out_dir: str, name: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, name)
    figure.savefig(path, dpi=160, bbox_inches="tight", facecolor=SURFACE)
    plt.close(figure)
    return path


def load_json(path: str) -> Any:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def best_version(archive: dict[str, Any]) -> dict[str, Any]:
    """Highest mean goal progress; ties go to the higher mean gate score."""
    return max(archive["versions"], key=lambda v: (v["score_mean"], v["gate_mean"]))


def player_models(archive: dict[str, Any]) -> str:
    """The run's player model, plus any version that used another one (the
    round-6 extension switched models; entries without the field are the run's)."""
    default = archive["config"]["player_model"]
    other = [f"{v['version']}: {v['player_model']}" for v in archive["versions"]
             if v.get("player_model", default) != default]
    return "; ".join([default] + other)


def _legend_handles() -> list[Line2D]:
    return [Line2D([], [], marker=s["marker"], linestyle="none", color=s["colour"], markersize=8,
                   label=s["label"]) for s in DECISION_STYLE.values()]


# ---------------------------------------------------------------------------
# 1. Goal progress per round
# ---------------------------------------------------------------------------


def figure_score_per_round(archive: dict[str, Any], out_dir: str) -> str:
    versions = archive["versions"]
    figure, axes = plt.subplots(figsize=(8.8, 4.8), facecolor=SURFACE)
    _style(axes, grid_axis="y")
    parent_means = []
    for info in archive["rounds"]:
        parent = next((v for v in versions if v["version"] == info["parent_after"]), None)
        if parent is not None:
            parent_means.append((info["round"], parent["score_mean"]))
    if parent_means:
        xs, ys = zip(*parent_means)
        axes.step(list(xs) + [xs[-1] + 0.4], list(ys) + [ys[-1]], where="post", color=TEXT_SECONDARY,
                  linewidth=1.5, linestyle=(0, (4, 3)), zorder=2)
    for entry in versions:
        style = DECISION_STYLE[_decision(entry)]
        x = entry["round"]
        # Dots are seeds 1..5 left to right; per-seed values are in the report's table.
        scores = [e["score"] for e in entry["episodes"]]
        jitter = np.linspace(-0.16, 0.16, len(scores)) if len(scores) > 1 else [0.0]
        axes.scatter([x + j for j in jitter], scores, s=22, color=style["colour"], alpha=0.5,
                     edgecolors="none", zorder=3)
        axes.errorbar([x + 0.3], [entry["score_mean"]], yerr=[entry["score_std"]], fmt="none",
                      ecolor=style["colour"], elinewidth=2, capsize=4, zorder=3)
        axes.scatter([x + 0.3], [entry["score_mean"]], s=110, marker=style["marker"], color=style["colour"],
                     edgecolors=SURFACE, linewidths=2, zorder=4)
        axes.annotate(f"{entry['version']} {entry['score_mean']:.3f}\n±{entry['score_std']:.3f}",
                      (x + 0.3, entry["score_mean"]), textcoords="offset points", xytext=(9, -4),
                      fontsize=7.5, color=TEXT_PRIMARY, va="top")
    for info in archive["rounds"]:
        if info.get("child") is None:
            axes.annotate("no valid edits", (info["round"], 0.05), ha="center", fontsize=8, color=TEXT_SECONDARY)
    axes.axhline(1.0, color=TEXT_SECONDARY, linewidth=0.8, zorder=1)
    axes.annotate("Level-1 clear = 1.0", (0.0, 1.0), xycoords=("axes fraction", "data"),
                  textcoords="offset points", xytext=(2, 4), fontsize=7, color=TEXT_SECONDARY)
    rounds = sorted({r["round"] for r in archive["rounds"]})
    axes.set_xticks(rounds)
    axes.set_xticklabels([f"round {r}" for r in rounds], fontsize=8)
    axes.set_xlim(min(rounds) - 0.4, max(rounds) + 0.9)
    axes.set_ylim(0, 1.08)
    axes.set_ylabel("Goal progress (dots: seeds 1-5, left to right; mark: mean ± SD)", fontsize=9,
                    color=TEXT_PRIMARY)
    axes.set_title(f"Goal progress per round, ls20 Level 1 ({player_models(archive)}, "
                   f"{len(archive['config']['seeds'])} seeds per version)",
                   fontsize=11, color=TEXT_PRIMARY, loc="left")
    handles = _legend_handles() + [Line2D([], [], color=TEXT_SECONDARY, linestyle=(0, (4, 3)),
                                          label="parent's mean progress")]
    axes.legend(handles=handles, frameon=False, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.09), ncol=4)
    return _save(figure, out_dir, "score_per_round.png")


# ---------------------------------------------------------------------------
# 2. Goal parts per round
# ---------------------------------------------------------------------------


def figure_parts_per_round(archive: dict[str, Any], out_dir: str) -> str:
    versions = archive["versions"]
    weights = archive["config"]["score"]["weights"]
    figure, axes = plt.subplots(figsize=(8.8, 4.6), facecolor=SURFACE)
    _style(axes, grid_axis="y")
    xs = np.arange(len(versions))
    bottom = np.zeros(len(versions))
    for part in PARTS:
        # Mean contribution at each episode's best state (sums to the mean
        # score; a clear contributes the full weight of every part).
        values = np.array([np.mean([e["goal"]["contributions"][part] for e in v["episodes"]]) for v in versions])
        axes.bar(xs, values, bottom=bottom, width=0.62, color=PART_COLOUR[part], edgecolor=SURFACE,
                 linewidth=2, zorder=3, label=f"{part} (weight {weights[part]})")
        bottom += values
    for x, v, total in zip(xs, versions, bottom):
        rotated = sum(1 for e in v["episodes"] if e["goal"]["ever"]["rotation_matched"])
        axes.annotate(f"{total:.3f}", (x, total), textcoords="offset points", xytext=(0, 3), ha="center",
                      fontsize=8, color=TEXT_PRIMARY)
        axes.annotate(f"rotated in\n{rotated}/{len(v['episodes'])}", (x, 0), textcoords="offset points",
                      xytext=(0, -30), ha="center", fontsize=7, color=TEXT_SECONDARY, annotation_clip=False)
    axes.set_xticks(xs)
    axes.set_xticklabels([f"{v['version']} (r{v['round']}, {_decision(v)})" for v in versions], fontsize=8)
    axes.tick_params(axis="x", pad=2)
    axes.set_ylim(0, 1.05)
    axes.set_ylabel("Mean weighted contribution at the best state", fontsize=9, color=TEXT_PRIMARY)
    axes.set_title("Goal progress split into goal parts (bars sum to the mean score)",
                   fontsize=11, color=TEXT_PRIMARY, loc="left")
    axes.legend(frameon=False, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=4)
    return _save(figure, out_dir, "parts_per_round.png")


# ---------------------------------------------------------------------------
# 3. Cost
# ---------------------------------------------------------------------------


def figure_cost(archive: dict[str, Any], out_dir: str) -> str:
    versions = archive["versions"]
    lam = float(archive["config"]["gate"]["lambda"])
    figure, (left, right) = plt.subplots(1, 2, figsize=(11.6, 4.6), facecolor=SURFACE,
                                         gridspec_kw={"width_ratios": [1.15, 1]})
    _style(left, grid_axis="y")
    _style(right, grid_axis="both")
    xs = np.arange(len(versions))
    bottom = np.zeros(len(versions))
    for part in ("tokens", "llm_calls", "env_steps"):
        values = np.array([np.mean([e["cost"]["normalised"][part] for e in v["episodes"]]) / 3 for v in versions])
        left.bar(xs, values, bottom=bottom, width=0.62, color=COST_COLOUR[part], edgecolor=SURFACE, linewidth=2,
                 zorder=3, label=COST_LABEL[part])
        bottom += values
    for x, v in zip(xs, versions):
        left.annotate(f"{v['cost_mean']:.3f}\n{v['tokens_mean'] / 1e3:.0f}k tok", (x, v["cost_mean"]),
                      textcoords="offset points", xytext=(0, 3), ha="center", fontsize=7, color=TEXT_PRIMARY)
    left.set_xticks(xs)
    left.set_xticklabels([f"{v['version']}\n{_decision(v)}" for v in versions], fontsize=8)
    left.set_ylim(0, 1.05)
    left.set_ylabel("Mean normalised cost (sum of thirds)", fontsize=9, color=TEXT_PRIMARY)
    left.set_title("Cost per round", fontsize=11, color=TEXT_PRIMARY, loc="left")
    left.legend(frameon=False, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=3)

    costs = [e["cost"]["cost"] for v in versions for e in v["episodes"]]
    lo, hi = max(0.0, min(costs) - 0.08), min(1.0, max(costs) + 0.08)
    grid_c = np.linspace(lo, hi, 50)
    for g in np.round(np.arange(-0.5, 1.01, 0.1), 1) + 0.0:  # + 0.0 turns -0.0 into 0.0
        ys = g + lam * grid_c  # equal gate score: progress = g + lambda * cost
        if (ys >= 0).any() and (ys <= 1.05).any():
            right.plot(grid_c, ys, color=TEXT_SECONDARY, linewidth=0.6, alpha=0.35, zorder=1)
            if 0 <= ys[-1] <= 1.03:
                right.annotate(f"g={g:.1f}", (grid_c[-1], ys[-1]), fontsize=6, color=TEXT_SECONDARY,
                               textcoords="offset points", xytext=(2, -2))
    means = [(v["cost_mean"], v["score_mean"]) for v in versions]
    placed: list[tuple[float, float]] = []
    for v in versions:
        style = DECISION_STYLE[_decision(v)]
        right.scatter([e["cost"]["cost"] for e in v["episodes"]], [e["score"] for e in v["episodes"]], s=16,
                      color=style["colour"], alpha=0.35, edgecolors="none", zorder=2)
        right.scatter([v["cost_mean"]], [v["score_mean"]], s=100, marker=style["marker"], color=style["colour"],
                      edgecolors=SURFACE, linewidths=2, zorder=4)
        # Versions can land close together: put each label on the side (of
        # four) farthest from the other versions' marks and labels placed so far.
        x, y = v["cost_mean"], v["score_mean"]
        span_x, span_y = (hi + 0.04 - lo), 1.05
        options = [((8, 5), (0.03, 0.025)), ((8, -13), (0.03, -0.03)), ((-24, 5), (-0.03, 0.025)),
                   ((-24, -13), (-0.03, -0.03))]

        def clearance(offset: tuple[float, float]) -> float:
            lx, ly = x + offset[0] * span_x, y + offset[1] * span_y / 1.05
            others = [p for p in means if p != (x, y)] + placed
            return min((((lx - px) / span_x) ** 2 + ((ly - py) / span_y) ** 2 for px, py in others), default=1.0)

        points, data_offset = max(options, key=lambda option: clearance(option[1]))
        placed.append((x + data_offset[0] * span_x, y + data_offset[1]))
        right.annotate(v["version"], (x, y), textcoords="offset points", xytext=points, fontsize=8,
                       color=TEXT_PRIMARY, zorder=5)
    right.set_xlim(lo, hi + 0.04)
    right.set_ylim(0, 1.05)
    right.set_xlabel("Normalised cost per episode", fontsize=9, color=TEXT_PRIMARY)
    right.set_ylabel("Goal progress", fontsize=9, color=TEXT_PRIMARY)
    right.set_title(f"Score vs cost (grey lines: equal gate score g = progress − {lam}·cost)",
                    fontsize=10, color=TEXT_PRIMARY, loc="left")
    right.legend(handles=_legend_handles(), frameon=False, fontsize=8, loc="upper center",
                 bbox_to_anchor=(0.5, -0.16), ncol=3)
    figure.tight_layout()
    return _save(figure, out_dir, "cost_per_round.png")


# ---------------------------------------------------------------------------
# 4. Lineage
# ---------------------------------------------------------------------------


def figure_lineage(archive: dict[str, Any], out_dir: str) -> str:
    versions = {v["version"]: v for v in archive["versions"]}
    final_parent = archive["rounds"][-1]["parent_after"]
    chain, name = [], final_parent
    while name:
        chain.append(name)
        name = versions[name]["parent"]
    figure, axes = plt.subplots(figsize=(13.2, 3.9), facecolor=SURFACE)
    axes.set_facecolor(SURFACE)
    axes.axis("off")
    pos: dict[str, tuple[float, float]] = {}
    for v in archive["versions"]:
        pos[v["version"]] = (v["round"] * 2.4, 0.0 if v["version"] in chain else -1.25)
    for v in archive["versions"]:
        if v["parent"] is None:
            continue
        (x0, y0), (x1, y1) = pos[v["parent"]], pos[v["version"]]
        decision = _decision(v)
        style = DECISION_STYLE[decision]
        axes.annotate("", xy=(x1 - 0.62, y1), xytext=(x0 + 0.62, y0),
                      arrowprops={"arrowstyle": "-|>", "color": style["colour"], "linewidth": 1.6,
                                  "linestyle": "solid" if decision == "accepted" else (0, (3, 2)),
                                  "connectionstyle": "arc3,rad=0.0" if y0 == y1 else "arc3,rad=-0.15"})
        gate = v.get("gate") or {}
        rule = "tie-break" if gate.get("rule", "").startswith("tie") else "gate score"
        label = (f"{decision}\n({rule})\nΔprog {gate.get('progress_diff', 0):+.3f}\n"
                 f"Δcost {gate.get('cost_diff', 0):+.3f}")
        if y0 == y1:  # in the gap between the two boxes, above the arrow
            axes.annotate(label, ((x0 + x1) / 2, y0 + 0.06), ha="center", va="bottom", fontsize=6.3,
                          color=TEXT_SECONDARY, zorder=5)
        else:  # off the chain: label under the child box, clear of the arrow
            axes.annotate(label, (x1, y1 - 0.42), ha="center", va="top", fontsize=6.3, color=TEXT_SECONDARY,
                          zorder=5)
    for v in archive["versions"]:
        x, y = pos[v["version"]]
        decision = _decision(v)
        style = DECISION_STYLE[decision]
        box = FancyBboxPatch((x - 0.6, y - 0.36), 1.2, 0.72, boxstyle="round,pad=0.02,rounding_size=0.08",
                             facecolor=SURFACE, edgecolor=style["colour"],
                             linewidth=2.6 if v["version"] == final_parent else 1.4, zorder=3)
        axes.add_patch(box)
        axes.text(x, y + 0.14, f"{v['version']}  ({decision})", ha="center", va="center", fontsize=8,
                  color=TEXT_PRIMARY, weight="bold", zorder=4)
        axes.text(x, y - 0.13, f"progress {v['score_mean']:.3f}\ncost {v['cost_mean']:.3f}  g {v['gate_mean']:.3f}",
                  ha="center", va="center", fontsize=6.8, color=TEXT_SECONDARY, zorder=4)
    for info in archive["rounds"]:
        if info.get("child") is None:
            axes.text(info["round"] * 2.0, -1.25, f"round {info['round']}\nno valid edits", ha="center",
                      va="center", fontsize=7, color=TEXT_SECONDARY)
    xs = [p[0] for p in pos.values()]
    axes.set_xlim(min(xs) - 0.8, max(xs) + 0.8)
    axes.set_ylim(-2.15, 0.75)
    axes.set_title(f"Harness lineage (top row: the accepted chain to the final parent {final_parent}, bold)",
                   fontsize=11, color=TEXT_PRIMARY, loc="left")
    handles = [Line2D([], [], color=DECISION_STYLE["accepted"]["colour"], linewidth=1.6, label="accepted"),
               Line2D([], [], color=DECISION_STYLE["rejected"]["colour"], linewidth=1.6, linestyle=(0, (3, 2)),
                      label="rejected")]
    axes.legend(handles=handles, frameon=False, fontsize=8, loc="upper right")
    return _save(figure, out_dir, "lineage.png")


# ---------------------------------------------------------------------------
# 5. Replay of the best version
# ---------------------------------------------------------------------------


def _rgb(grid: np.ndarray) -> np.ndarray:
    out = np.zeros(grid.shape + (3,), dtype=np.uint8)
    for value in np.unique(grid):
        out[grid == value] = _PALETTE_RGB.get(int(value), (80, 80, 80))
    return out


def _episode_states(episode: dict[str, Any]) -> list[dict[str, Any]]:
    """One state per frame: state 0 = start, then one per action (an
    auto-reset adds the reset state, as it adds a frame)."""
    states, _ = states_from_records(read_records(episode["trajectory"]))
    return states


def figure_replay(archive: dict[str, Any], out_dir: str, gif: bool = True) -> list[str]:
    best = best_version(archive)
    episode = max(best["episodes"], key=lambda e: (e["score"], -e["goal"]["best_state"]["action_index"]))
    frames = load_frames(episode["frames"])
    states = _episode_states(episode)
    n = min(len(frames), len(states))
    maze = level1_maze(archive["config"]["game"])
    need = states[0]["goals"][0]["rotation"]
    rotation_changes = [i for i in range(1, n) if states[i]["rotation"] != states[i - 1]["rotation"]
                        and states[i]["lives"] == states[i - 1]["lives"]]
    # A life ends when the move counter runs out; ls20 then puts the player
    # back at the start AND resets its rotation, which undoes a rotation step.
    life_lost = [i for i in range(1, n) if states[i]["lives"] != states[i - 1]["lives"]]
    best_i = next(i for i in range(n) if states[i]["action_index"] == episode["goal"]["best_state"]["action_index"])
    keys = [0]
    for i in rotation_changes[:1]:
        keys += [max(0, i - 1), i]
    keys.append(best_i)
    after_best = [i for i in life_lost if i > best_i][:1]
    for i in after_best:
        keys += [i - 1, i]
    keys.append(n - 1)
    keys = sorted(dict.fromkeys(k for k in keys if 0 <= k < n))[:8]

    def caption(i: int) -> str:
        s = states[i]
        moves = maze.moves_to_goal(s["x"], s["y"])
        rot = "matches" if s["rotation"] == need else f"needs {need}"
        tag = ""
        if i in rotation_changes:
            tag = "  ← ROTATED (stepped on the switch)"
        elif i == best_i:
            tag = "  ← best state"
        elif i in life_lost:
            tag = "  ← counter ran out: life lost, rotation reset"
        return (f"after action {s['action_index']}{tag}\nrotation {s['rotation']} ({rot}), "
                f"{moves} move{'' if moves == 1 else 's'} to goal, counter {s['moves_left']} left")

    def draw(axes: plt.Axes, i: int) -> None:
        axes.imshow(_rgb(np.asarray(frames[i])), interpolation="nearest")
        axes.set_xticks([])
        axes.set_yticks([])
        for spine in axes.spines.values():
            spine.set_color(TEXT_SECONDARY)
        # The bottom-left HUD shows the player's current rotation; the switch
        # and the goal are outlined so the rotation step can be followed.
        for (r0, c0, h, w), colour in (((53, 1, 10, 10), "#ffffff"), ((30, 19, 5, 5), "#ffffff"),
                                       ((10, 34, 5, 5), "#ffffff")):
            axes.add_patch(Rectangle((c0 - 0.5, r0 - 0.5), w, h, fill=False, edgecolor=colour, linewidth=1.0,
                                     linestyle=(0, (2, 1))))
        axes.set_title(caption(i), fontsize=6.5, color=TEXT_PRIMARY, loc="left")

    paths = []
    cols = min(4, len(keys))
    rows = int(np.ceil(len(keys) / cols))
    figure, grid_axes = plt.subplots(rows, cols, figsize=(3.0 * cols, 3.35 * rows), facecolor=SURFACE)
    flat = np.atleast_1d(grid_axes).ravel()
    for axes, i in zip(flat, keys):
        draw(axes, i)
    for axes in flat[len(keys):]:
        axes.axis("off")
    figure.suptitle(f"Replay: {best['version']} (highest mean progress {best['score_mean']:.3f}; gate: {_decision(best)}), "
                    f"seed {episode['seed']}, episode progress {episode['score']:.3f}. "
                    "Dashed: HUD (shows the rotation), switch, goal.",
                    fontsize=9, color=TEXT_PRIMARY, x=0.01, ha="left")
    figure.tight_layout()
    name = f"replay_{best['version']}_seed{episode['seed']}"
    paths.append(_save(figure, out_dir, name + ".png"))

    if gif:
        from PIL import Image

        end = min(n, best_i + 12)
        step = max(1, end // 90)
        indices = sorted(set(range(0, end, step)) | set(rotation_changes) | {best_i})
        images = []
        for i in indices:
            fig, axes = plt.subplots(figsize=(3.4, 3.8), facecolor=SURFACE)
            draw(axes, i)
            fig.tight_layout()
            fig.canvas.draw()
            images.append(Image.fromarray(np.asarray(fig.canvas.buffer_rgba())[..., :3]))
            plt.close(fig)
        durations = [1400 if (i in rotation_changes or i == best_i) else 120 for i in indices]
        path = os.path.join(out_dir, name + ".gif")
        images[0].save(path, save_all=True, append_images=images[1:], duration=durations, loop=0, optimize=True)
        paths.append(path)
    return paths


# ---------------------------------------------------------------------------
# 6. This run vs #9 rescored
# ---------------------------------------------------------------------------


def figure_vs_issue9(archive: dict[str, Any], rescored: dict[str, Any], out_dir: str) -> str:
    figure, axes = plt.subplots(figsize=(8.8, 4.6), facecolor=SURFACE)
    _style(axes, grid_axis="y")
    runs = (("#12", archive["versions"], f"#12: {player_models(archive)}, 5 seeds", -0.08),
            ("#9", rescored["versions"], "#9 rescored: Qwen3.8-27B, 3 episodes", 0.08))
    for key, versions, label, offset in runs:
        colour = RUN_COLOUR[key]
        xs = [v["round"] + offset for v in versions]
        ys = [v["score_mean"] for v in versions]
        axes.plot(xs, ys, color=colour, linewidth=2, zorder=2, label=label)
        axes.errorbar(xs, ys, yerr=[v["score_std"] for v in versions], fmt="none", ecolor=colour,
                      elinewidth=1.2, capsize=3, alpha=0.7, zorder=2)
        for v, x, y in zip(versions, xs, ys):
            decision = v.get("decision_9") or _decision(v)
            marker = DECISION_STYLE[decision]["marker"]
            axes.scatter([x], [y], s=70, marker=marker, color=colour, edgecolors=SURFACE, linewidths=1.5, zorder=4)
        v0 = versions[0]["score_mean"]
        axes.axhline(v0, color=colour, linewidth=1, linestyle=(0, (4, 3)), zorder=1)
        axes.annotate(f"{key} v0 baseline {v0:.3f}", (1.0, v0), xycoords=("axes fraction", "data"),
                      textcoords="offset points", xytext=(-2, 3 if key == "#12" else -10), ha="right", fontsize=7.5,
                      color=TEXT_PRIMARY)
    rounds = sorted({v["round"] for _k, vs, _l, _o in runs for v in vs})
    axes.set_xticks(rounds)
    axes.set_xticklabels([f"round {r}" for r in rounds], fontsize=8)
    axes.set_ylim(0, 1.05)
    axes.set_ylabel("Mean goal progress (± SD)", fontsize=9, color=TEXT_PRIMARY)
    axes.set_title("Goal progress per round: this run vs #9 (rescored with #12's score)",
                   fontsize=11, color=TEXT_PRIMARY, loc="left")
    handles = [Line2D([], [], color=RUN_COLOUR[k], linewidth=2, label=l) for k, _v, l, _o in runs]
    handles += [Line2D([], [], marker=DECISION_STYLE[d]["marker"], linestyle="none", color=TEXT_SECONDARY,
                       markersize=7, label=DECISION_STYLE[d]["label"]) for d in ("baseline", "accepted", "rejected")]
    axes.legend(handles=handles, frameon=False, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.09), ncol=3)
    return _save(figure, out_dir, "vs_issue9.png")


def build_all(root: str, gif: bool = True) -> list[str]:
    archive = load_json(os.path.join(root, "archive.json"))
    out_dir = os.path.join(root, "figures")
    paths = [
        figure_score_per_round(archive, out_dir),
        figure_parts_per_round(archive, out_dir),
        figure_cost(archive, out_dir),
        figure_lineage(archive, out_dir),
        *figure_replay(archive, out_dir, gif=gif),
    ]
    rescored_path = os.path.join(root, "rescored_9.json")
    if os.path.exists(rescored_path):
        paths.append(figure_vs_issue9(archive, load_json(rescored_path), out_dir))
    return paths
