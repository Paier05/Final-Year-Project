"""Issue #16, final report: tables and figures from the two v4 runs, with #15
for comparison. No new play.

    python -m analysis.issue16_report     # results/issue16/final.json, results/issue16/figures/

Inputs: runs/<game>-v4 (#16) and runs/<game> (#15) for ft09 and vc33, plus
results/issue16/from15.json (#15's repeat rate and no-effect clicks, made by
analysis/issue16_from15.py with the same frame diff used here).

Per game, figures:
- <game>_score_per_round.png    seeds 1-5 per version, mean +- spread, gate
                                decision, #15's mean (seeds 1-3) per round
- <game>_seed_scores.png        the score's one part per version and seed
- <game>_cost.png               cost per round; score vs cost per version
- <game>_lineage.png            v0 -> v5, gate decisions, Validate drops by check
- <game>_frame_evidence.png     where v0 and the final parent clicked, and the
                                rare on-screen changes the Meta LLM was shown
- <game>_click_map.png          v0 and the final parent's clicks, by whether
                                the click changed something (every-step
                                regions left out, as the player saw it)
- <game>_state_change.png       before/after frames of a skill the
                                state-change check dropped (if any)
- <game>_replay.png             one episode of the final parent
Both games: comparison.png (#15 vs #16), no_effect_clicks.png.
"""

from __future__ import annotations

import ast
import glob
import json
import os
import re
import sys
from collections import Counter
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch, Rectangle

os.environ.setdefault("OPERATION_MODE", "offline")

from analysis.evolution import DECISION_STYLE, _decision, _save  # noqa: E402
from analysis.figures import (  # noqa: E402
    GRID,
    ROUND_COLOUR,
    SEQUENTIAL,
    SLOT3,
    SURFACE,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    _style,
)
from analysis.issue16_from15 import click_counts  # noqa: E402
from analysis.movement import render_board  # noqa: E402
from evolve.action_loop import load_frames, read_records  # noqa: E402
from evolve.edits import EditError, normalise  # noqa: E402
from evolve.frame_diff import ActionRecorder, render  # noqa: E402
from evolve.rejected import edit_type  # noqa: E402
from evolve.replay import tool_calls  # noqa: E402

GAMES = ("ft09", "vc33")
OUT_DIR = os.path.join("results", "issue16")
FIG_DIR = os.path.join(OUT_DIR, "figures")
FROM15 = os.path.join(OUT_DIR, "from15.json")
PART_TEXT = {
    "ft09": "tiles: share of the tiles wrong at the start that were put right (best state in the episode)",
    "vc33": "alignment: how far each object moved toward its target (best state in the episode)",
}
CHANGED = ROUND_COLOUR[0]
NO_CHANGE = ROUND_COLOUR[1]
RUN15 = TEXT_SECONDARY


def root16(game: str) -> str:
    return os.path.join("runs", f"{game}-v4")


def root15(game: str) -> str:
    return os.path.join("runs", game)


def load_archive(root: str) -> dict[str, Any]:
    with open(os.path.join(root, "archive.json"), encoding="utf-8") as handle:
        return json.load(handle)


def _attempts(root: str, round_index: int) -> list[dict[str, Any]]:
    path = os.path.join(root, "reports", f"round_{round_index}", "attempts.json")
    if not os.path.exists(path):
        path = os.path.join(root, "reports", f"round_{round_index}", "validation.json")
    data = json.load(open(path, encoding="utf-8"))
    return data["attempts"] if isinstance(data, dict) else data


def _analysis(root: str, version: str) -> dict[str, Any] | None:
    for path in sorted(glob.glob(os.path.join(root, "reports", "round_*", "analysis.json"))):
        data = json.load(open(path, encoding="utf-8"))
        if data.get("version") == version:
            return data
    return None


def _mean(values: list[float]) -> float | None:
    return round(float(np.mean(values)), 4) if values else None


def _local(path: str, root: str) -> str:
    """Paths in the archive are relative to the repo on the cluster."""
    parts = path.replace("\\", "/").split("/")
    return os.path.join(root, *parts[parts.index("trajectories" if "trajectories" in parts else "frames"):])


def final_parent(archive: dict[str, Any]) -> str:
    return archive["rounds"][-1]["parent_after"]


def version(archive: dict[str, Any], name: str) -> dict[str, Any]:
    return next(v for v in archive["versions"] if v["version"] == name)


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------


def round_rows(archive: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for entry in archive["versions"]:
        gate = entry.get("gate") or {}
        episodes = entry["episodes"]
        rows.append({
            "round": entry["round"], "version": entry["version"], "parent": entry["parent"],
            "score_mean": entry["score_mean"], "score_std": entry["score_std"],
            "score_mean_seeds_1_3": _mean([e["score"] for e in episodes if e["seed"] in (1, 2, 3)]),
            "clears": entry["n_clears"], "n": entry["n_episodes"], "clear_rate": entry["clear_rate"],
            "clears_seeds_1_3": sum(1 for e in episodes if e["seed"] in (1, 2, 3) and e["solved"]),
            "avg_steps": entry["avg_steps"], "cost_mean": entry["cost_mean"], "gate_mean": entry["gate_mean"],
            "decision": gate.get("decision", "baseline"), "reason": gate.get("reason", "v0 is the starting parent"),
            "scores": {int(e["seed"]): e["score"] for e in episodes},
            "end_reasons": dict(Counter(e["end_reason"] for e in episodes)),
            "resets_mean": _mean([e["resets_used"] for e in episodes]),
            "tokens": entry.get("tokens") or 0, "meta_tokens": entry.get("meta_tokens") or 0,
            "factcheck_tokens": (entry.get("factcheck") or {}).get("extraction_tokens") or 0,
        })
    return rows


def edit_rows(root: str, archive: dict[str, Any]) -> list[dict[str, Any]]:
    """Per round: proposed edits by type and source, drops by Validate check."""
    rounds = {r["round"]: r for r in archive["rounds"]}
    rows = []
    for round_index in sorted(r for r in rounds if r > 0):
        types: Counter = Counter()
        meta_types: Counter = Counter()
        sources: Counter = Counter()
        stages: Counter = Counter()
        promotes = []
        attempts = _attempts(root, round_index)
        for attempt in attempts:
            passed = {p["id"] for p in attempt.get("passed") or []}
            for index, item in enumerate(attempt["rules"] + ((attempt.get("meta") or {}).get("edits") or []), 1):
                source = item.get("source", "meta")
                try:
                    kind = edit_type(normalise(item, source))
                except EditError:
                    kind = "malformed"
                types[kind] += 1
                sources[source] += 1
                if source == "meta":
                    meta_types[kind] += 1
                if kind == "promote":
                    promotes.append({"attempt": attempt["attempt"], "name": item.get("name"),
                                     "passed": f"r{round_index}-e{index}" in passed})
            for item in attempt.get("dropped") or []:
                stages[item["stage"]] += 1
        child = rounds[round_index].get("child")
        written = version(archive, child).get("edits_accepted") or [] if child else []
        rows.append({
            "round": round_index, "attempts": len(attempts), "child": child,
            "decision": rounds[round_index].get("decision"),
            "proposed": sum(types.values()), "by_type": dict(types), "meta_by_type": dict(meta_types),
            "by_source": dict(sources), "dropped_by_check": dict(stages), "written": len(written),
            "written_edits": [f"{e['what']} ({e['source']})" for e in written], "promotes": promotes,
        })
    return rows


def check_rows(archive: dict[str, Any]) -> dict[str, Any]:
    state_change, repeats = [], []
    for entry in archive["versions"]:
        for result in (entry.get("state_change") or {}).get("results") or []:
            state_change.append({
                "round": entry["round"], "version": entry["version"],
                **{k: result.get(k) for k in ("attempt", "id", "name", "verdict", "summary", "call", "env_steps")},
                "states": [{k: s.get(k) for k in ("seed", "turn", "verdict", "actions", "cells_changed",
                                                   "game_state_changed", "why")} for s in result.get("states") or []],
            })
        dropped = {d["id"]: d for d in entry.get("edits_dropped") or [] if d.get("stage") == "repeat"}
        for item in (entry.get("repeat") or {}).get("repeats") or []:
            repeats.append({"round": entry["round"], **item,
                            "what": (dropped.get(item["id"]) or {}).get("what"),
                            "source": (dropped.get(item["id"]) or {}).get("source")})
    return {"state_change": state_change, "repeats": repeats}


def store_rows(root: str) -> list[dict[str, Any]]:
    path = os.path.join(root, "rejected_edits.jsonl")
    rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
    return [{k: r.get(k) for k in ("id", "round", "version", "type", "target", "source", "what", "rejected_by")}
            for r in rows]


def section_rows(root: str, archive: dict[str, Any]) -> list[dict[str, Any]]:
    """What "Rejected since current parent" showed per round, and what the
    Meta LLM proposed next: how many of its edits were dropped as repeats."""
    rows = []
    for round_info in archive["rounds"]:
        if round_info["round"] == 0:
            continue
        round_index = round_info["round"]
        analysis = json.load(open(os.path.join(root, "reports", f"round_{round_index}", "analysis.json"),
                                  encoding="utf-8"))
        section = analysis.get("rejected_since_parent") or {}
        data = section.get("data") or {}
        meta_edits = meta_repeats = 0
        calls = []
        for attempt in _attempts(root, round_index):
            edits = (attempt.get("meta") or {}).get("edits") or []
            n_rules = len(attempt["rules"])
            ids = {f"r{round_index}-e{n_rules + i}" for i in range(1, len(edits) + 1)}
            repeated = [d for d in attempt.get("dropped") or [] if d["stage"] == "repeat" and d["id"] in ids]
            meta_edits += len(edits)
            meta_repeats += len(repeated)
            calls.append({"attempt": attempt["attempt"], "meta_edits": len(edits), "repeats": len(repeated),
                          "proposed": [f"{e.get('op')} {e.get('target')} {e.get('name')}" for e in edits]})
        rows.append({
            "round": round_index, "parent": analysis["version"],
            "versions_shown": [v.get("version") for v in data.get("versions") or []],
            "dropped_edits_shown": len(data.get("dropped") or []), "section_chars": len(section.get("text") or ""),
            "meta_edits": meta_edits, "meta_repeats": meta_repeats, "calls": calls,
        })
    return rows


def record_cost(root: str) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(glob.glob(os.path.join(root, "trajectories", "round_*", "seed_*.jsonl"))):
        calls = tool_calls(read_records(path))
        chars = sum(int(r.get("action_record_chars") or 0) for r in calls)
        tokens_in = sum(int(r.get("tokens_in") or 0) for r in calls)
        rows.append({
            "round": int(re.search(r"round_(\d+)", path).group(1)),
            "seed": int(re.search(r"seed_(\d+)", path).group(1)), "turns": len(calls),
            "record_chars": chars, "record_tokens_est": round(chars / 4), "tokens_in": tokens_in,
            "share_of_input_est": round(chars / 4 / tokens_in, 4) if tokens_in else None,
            "turns_using_action_log": sum(1 for r in calls if "action_log" in str(r.get("code") or "")),
        })
    return rows


def helper_rows(root: str, archive: dict[str, Any], edits: list[dict[str, Any]]) -> dict[str, Any]:
    inline = {}
    for round_info in archive["rounds"]:
        if round_info["round"] == 0:
            continue
        analysis = json.load(open(os.path.join(root, "reports", f"round_{round_info['round']}", "analysis.json"),
                                  encoding="utf-8"))
        inline[round_info["round"]] = sorted({h["name"] for h in analysis.get("inline_helpers") or []})
    promoted = []
    for entry in archive["versions"]:
        for edit in entry.get("edits_accepted") or []:
            if edit["source"] == "rule" and edit["what"].startswith("add skill "):
                name = edit["what"].split()[-1]
                later = [v for v in archive["versions"] if v["round"] >= entry["round"]
                         and name in (v.get("skill_usage") or {})]
                promoted.append({"name": name, "version": entry["version"],
                                 "decision": _decision(entry),
                                 "calls_after": {v["version"]: v["skill_usage"][name]["calls"] for v in later}})
    skills_with_log = sorted({os.path.relpath(p, root).replace(os.sep, "/")
                              for p in glob.glob(os.path.join(root, "harnesses", "*", "skills", "*.py"))
                              if "action_log" in open(p, encoding="utf-8").read()})
    return {"inline_by_round": inline, "promotes_proposed": sum(len(r["promotes"]) for r in edits),
            "promotes_passed": sum(p["passed"] for r in edits for p in r["promotes"]),
            "promoted_written": promoted, "skills_using_action_log": skills_with_log}


def failure_rows(root: str, archive: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for entry in archive["versions"]:
        analysis = _analysis(root, entry["version"]) or {}
        rows.append({
            "version": entry["version"],
            "end_reasons": dict(Counter(e["end_reason"] for e in entry["episodes"])),
            "resets_mean": _mean([e["resets_used"] for e in entry["episodes"]]),
            "cell_errors_mean": _mean([e["cell_errors"] for e in entry["episodes"]]),
            "common_errors": (analysis.get("common_errors") or [])[:3],
        })
    return rows


def action_record_example(root: str, archive: dict[str, Any]) -> dict[str, Any]:
    """The ACTION RECORD block one turn of the final parent's best episode
    showed, rebuilt from its saved frames; its length is checked against the
    action_record_chars the turn logged."""
    entry = version(archive, final_parent(archive))
    episode = max(entry["episodes"], key=lambda e: (e["score"], -e["actions_used"]))
    path = _local(episode["trajectory"], root)
    frames = load_frames(_local(episode["frames"], root))
    calls = tool_calls(read_records(path))
    # A turn about two thirds in with at least 4 actions behind it.
    candidates = [i for i, r in enumerate(calls)
                  if sum(len(c.get("actions") or []) for c in calls[:i]) >= 4]
    turn = candidates[min(len(candidates) - 1, len(candidates) * 2 // 3)] if candidates else len(calls) - 1
    recorder = ActionRecorder(())
    for record in calls[:turn]:
        for item in record.get("actions") or []:
            game_over = item.get("state") == "GAME_OVER" or "auto_reset_frame" in item
            recorder.add(item["action_index"], item["action"], item.get("args"),
                         np.asarray(frames[item["frame_before"]]), np.asarray(frames[item["frame_after"]]),
                         game_over=game_over, level_restarted="auto_reset_frame" in item)
    text = render(recorder, 20, 40)
    logged = int(calls[turn].get("action_record_chars") or 0)
    return {"version": entry["version"], "seed": episode["seed"], "turn": int(calls[turn]["turn"]),
            "text": text, "chars": len(text), "logged_chars": logged, "matches_log": len(text) == logged}


def comparison(rows: list[dict[str, Any]], archive: dict[str, Any], edits: list[dict[str, Any]],
               helpers: dict[str, Any] | None) -> dict[str, Any]:
    by_version = {r["version"]: r for r in rows}
    v0, best = by_version["v0"], by_version[final_parent(archive)]
    types: Counter = Counter()
    stages: Counter = Counter()
    for row in edits:
        types.update(row["by_type"])
        stages.update(row["dropped_by_check"])
    promoted = (len([p for p in helpers["promoted_written"]]) if helpers else
                sum(1 for r in archive["versions"] for e in r.get("edits_accepted") or []
                    if e["source"] == "rule" and e["what"].startswith("add skill ")))
    return {
        "rounds_done": max(r["round"] for r in archive["rounds"]), "final_parent": best["version"],
        "v0_score": v0["score_mean"], "v0_score_seeds_1_3": v0["score_mean_seeds_1_3"],
        "best_score": best["score_mean"], "best_score_seeds_1_3": best["score_mean_seeds_1_3"],
        "improvement": round(best["score_mean"] - v0["score_mean"], 4),
        "improvement_seeds_1_3": round(best["score_mean_seeds_1_3"] - v0["score_mean_seeds_1_3"], 4),
        "best_clears": f"{best['clears']}/{best['n']}", "best_clears_seeds_1_3": f"{best['clears_seeds_1_3']}/3",
        "v0_clears": f"{v0['clears']}/{v0['n']}",
        "accepted": [r["version"] for r in rows if r["decision"] == "accepted"],
        "edits_by_type": dict(types), "proposed": sum(types.values()), "dropped_by_check": dict(stages),
        "skills_promoted": promoted,
        "tokens_player": sum(r["tokens"] for r in rows),
        "tokens_meta": sum(r["meta_tokens"] + r["factcheck_tokens"] for r in rows),
        "tokens_total": sum(r["tokens"] + r["meta_tokens"] + r["factcheck_tokens"] for r in rows),
    }


def clicks_by_round(rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for row in rows:
        item = out.setdefault(int(row["round"]), {"episodes": 0, "clicks": 0, "no_effect": 0, "repeated_no_effect": 0})
        item["episodes"] += 1
        for key in ("clicks", "no_effect", "repeated_no_effect"):
            item[key] += row[key]
    for item in out.values():
        item["no_effect_per_episode"] = round(item["no_effect"] / item["episodes"], 1)
        item["repeated_per_episode"] = round(item["repeated_no_effect"] / item["episodes"], 1)
        item["no_effect_share"] = round(item["no_effect"] / item["clicks"], 4) if item["clicks"] else None
    return dict(sorted(out.items()))


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def _version_x(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {r["version"]: r["round"] for r in rows}


def figure_score(game: str, rows: list[dict[str, Any]], rows15: list[dict[str, Any]], archive: dict[str, Any]) -> str:
    figure, axes = plt.subplots(figsize=(8.8, 4.8), facecolor=SURFACE)
    _style(axes, grid_axis="y")
    by_version = {r["version"]: r for r in rows}
    steps = [(r["round"], by_version[r["parent_after"]]["score_mean"]) for r in archive["rounds"]]
    xs, ys = zip(*steps)
    axes.step(xs, ys, where="post", color=TEXT_SECONDARY, linewidth=1.2, linestyle=(0, (4, 3)), zorder=2)
    for row in rows:
        style = DECISION_STYLE[row["decision"]]
        scores = [row["scores"][s] for s in sorted(row["scores"])]
        jitter = np.linspace(-0.16, 0.16, len(scores))
        axes.scatter(row["round"] + jitter, scores, s=22, color=style["colour"], alpha=0.4, edgecolors="none", zorder=3)
        axes.errorbar(row["round"], row["score_mean"], yerr=row["score_std"], color=style["colour"], capsize=4,
                      linewidth=1.2, zorder=4)
        axes.scatter([row["round"]], [row["score_mean"]], s=110, marker=style["marker"], color=style["colour"],
                     edgecolors=SURFACE, linewidths=2, zorder=5)
        axes.annotate(f"{row['version']} {row['score_mean']:.2f}\n{row['clears']}/{row['n']} clear",
                      (row["round"], row["score_mean"]), textcoords="offset points", xytext=(10, -4),
                      fontsize=7.5, color=TEXT_PRIMARY, va="top")
    if rows15:
        axes.plot([r["round"] for r in rows15], [r["score_mean"] for r in rows15], color=RUN15, linewidth=1.2,
                  marker="D", markersize=5, markerfacecolor=SURFACE, zorder=3)
    axes.set_xticks([r["round"] for r in rows])
    axes.set_xticklabels([f"round {r['round']}" for r in rows], fontsize=8)
    axes.set_ylim(-0.04, 1.12)
    axes.set_xlim(-0.4, max(r["round"] for r in rows) + 0.75)
    axes.set_ylabel("goal-progress score (1 = Level 1 cleared)", fontsize=9, color=TEXT_PRIMARY)
    axes.set_title(f"{game}: score per round, seeds 1-5 (dots), mean +- spread (large marks)",
                   fontsize=11, color=TEXT_PRIMARY, loc="left")
    handles = [Line2D([], [], marker=s["marker"], linestyle="none", color=s["colour"], markersize=8, label=s["label"])
               for s in DECISION_STYLE.values()]
    handles.append(Line2D([], [], color=TEXT_SECONDARY, linestyle=(0, (4, 3)), label="parent's mean (score to beat)"))
    if rows15:
        handles.append(Line2D([], [], color=RUN15, marker="D", markerfacecolor=SURFACE, label="#15, same round (seeds 1-3)"))
    axes.legend(handles=handles, frameon=False, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.08), ncol=3)
    return _save(figure, FIG_DIR, f"{game}_score_per_round.png")


def figure_seed_scores(game: str, rows: list[dict[str, Any]], archive: dict[str, Any]) -> str:
    seeds = sorted({s for r in rows for s in r["scores"]})
    matrix = np.array([[r["scores"].get(s, np.nan) for s in seeds] for r in rows])
    solved = {(e["seed"], v["version"]) for v in archive["versions"] for e in v["episodes"] if e["solved"]}
    figure, axes = plt.subplots(figsize=(6.6, 0.5 * len(rows) + 1.6), facecolor=SURFACE)
    axes.imshow(matrix, cmap=SEQUENTIAL, vmin=0, vmax=1, aspect="auto")
    for i, row in enumerate(rows):
        for j, seed in enumerate(seeds):
            value = matrix[i, j]
            text = f"{value:.2f}" + (" clear" if (seed, row["version"]) in solved else "")
            axes.text(j, i, text, ha="center", va="center", fontsize=8,
                      color=SURFACE if value > 0.55 else TEXT_PRIMARY)
    axes.set_xticks(range(len(seeds)))
    axes.set_xticklabels([f"seed {s}" for s in seeds], fontsize=8)
    axes.set_yticks(range(len(rows)))
    axes.set_yticklabels([f"{r['version']} ({r['decision']})" for r in rows], fontsize=8)
    for side in axes.spines.values():
        side.set_visible(False)
    axes.set_title(f"{game}: the score's one part per version and seed\n{PART_TEXT[game]}",
                   fontsize=9.5, color=TEXT_PRIMARY, loc="left")
    return _save(figure, FIG_DIR, f"{game}_seed_scores.png")


def figure_cost(game: str, rows: list[dict[str, Any]], archive: dict[str, Any], rows15: list[dict[str, Any]]) -> str:
    figure, (left, right) = plt.subplots(1, 2, figsize=(11.5, 4.4), facecolor=SURFACE)
    _style(left, grid_axis="y")
    _style(right, grid_axis="both")
    placed: list[tuple[float, float]] = []
    for row in rows:
        style = DECISION_STYLE[row["decision"]]
        entry = version(archive, row["version"])
        costs = [e["cost"]["cost"] for e in entry["episodes"]]
        scores = [e["score"] for e in entry["episodes"]]
        jitter = np.linspace(-0.16, 0.16, len(costs))
        left.scatter(row["round"] + jitter, costs, s=20, color=style["colour"], alpha=0.4, edgecolors="none", zorder=3)
        left.errorbar(row["round"], row["cost_mean"], yerr=float(np.std(costs)), color=style["colour"], capsize=4,
                      linewidth=1.2, zorder=4)
        left.scatter([row["round"]], [row["cost_mean"]], s=100, marker=style["marker"], color=style["colour"],
                     edgecolors=SURFACE, linewidths=2, zorder=5)
        left.annotate(f"{row['version']} {row['cost_mean']:.2f}", (row["round"], row["cost_mean"]),
                      textcoords="offset points", xytext=(9, -3), fontsize=7.5, color=TEXT_PRIMARY)
        right.scatter(costs, scores, s=18, color=style["colour"], alpha=0.3, edgecolors="none", zorder=3)
        right.scatter([row["cost_mean"]], [row["score_mean"]], s=110, marker=style["marker"], color=style["colour"],
                      edgecolors=SURFACE, linewidths=2, zorder=5)
        # A version next to one already labelled gets its label below, or the two overprint.
        near = any(abs(row["cost_mean"] - c) < 0.05 and abs(row["score_mean"] - s) < 0.05 for c, s in placed)
        right.annotate(row["version"], (row["cost_mean"], row["score_mean"]), textcoords="offset points",
                       xytext=(7, -13) if near else (7, 5), fontsize=8, color=TEXT_PRIMARY)
        placed.append((row["cost_mean"], row["score_mean"]))
    if rows15:
        left.plot([r["round"] for r in rows15], [r["cost_mean"] for r in rows15], color=RUN15, linewidth=1.2,
                  marker="D", markersize=5, markerfacecolor=SURFACE, zorder=3, label="#15, same round (seeds 1-3)")
        left.legend(frameon=False, fontsize=8, loc="lower left")
    left.set_xticks([r["round"] for r in rows])
    left.set_xticklabels([f"round {r['round']}" for r in rows], fontsize=8)
    left.set_ylim(0, 1.0)
    left.set_ylabel("episode cost (0 = free; tokens, calls and steps, normalised)", fontsize=8.5, color=TEXT_PRIMARY)
    left.set_title("cost per round (lower is better)", fontsize=10, color=TEXT_PRIMARY, loc="left")
    right.set_xlim(0, 1.0)
    right.set_ylim(-0.04, 1.08)
    right.set_xlabel("episode cost", fontsize=8.5, color=TEXT_PRIMARY)
    right.set_ylabel("score", fontsize=8.5, color=TEXT_PRIMARY)
    right.set_title("score vs cost per version (top left is best)", fontsize=10, color=TEXT_PRIMARY, loc="left")
    handles = [Line2D([], [], marker=s["marker"], linestyle="none", color=s["colour"], markersize=8, label=s["label"])
               for s in DECISION_STYLE.values()]
    right.legend(handles=handles, frameon=False, fontsize=8, loc="lower right")
    figure.suptitle(f"{game}: cost", fontsize=11, color=TEXT_PRIMARY, x=0.01, ha="left")
    figure.tight_layout()
    return _save(figure, FIG_DIR, f"{game}_cost.png")


def figure_lineage(game: str, rows: list[dict[str, Any]], edits: list[dict[str, Any]]) -> str:
    by_version = {r["version"]: r for r in rows}
    level = {r["version"]: (1.0 if r["decision"] in ("accepted", "baseline") else 0.0) for r in rows}
    figure, axes = plt.subplots(figsize=(11.5, 4.6), facecolor=SURFACE)
    axes.set_axis_off()
    for row in rows:
        if row["parent"] is None:
            continue
        style = DECISION_STYLE[row["decision"]]
        start = (by_version[row["parent"]]["round"], level[row["parent"]])
        end = (row["round"], level[row["version"]])
        axes.annotate("", xy=(end[0] - 0.33, end[1]), xytext=(start[0] + 0.33, start[1]),
                      arrowprops={"arrowstyle": "-|>", "color": style["colour"], "linewidth": 1.6,
                                  "linestyle": "solid" if row["decision"] == "accepted" else (0, (4, 3)),
                                  "shrinkA": 0, "shrinkB": 0})
    for row in rows:
        style = DECISION_STYLE[row["decision"]]
        x, y = row["round"], level[row["version"]]
        axes.add_patch(FancyBboxPatch((x - 0.33, y - 0.17), 0.66, 0.34, boxstyle="round,pad=0.02",
                                      facecolor=SURFACE, edgecolor=style["colour"], linewidth=2, zorder=3))
        axes.text(x, y + 0.05, row["version"], ha="center", va="center", fontsize=10, fontweight="bold",
                  color=TEXT_PRIMARY, zorder=4)
        axes.text(x, y - 0.07, f"{row['score_mean']:.2f} · {row['clears']}/{row['n']} clear", ha="center",
                  va="center", fontsize=7.5, color=TEXT_SECONDARY, zorder=4)
    for row in edits:
        drops = row["dropped_by_check"]
        lines = [f"proposed {row['proposed']} · written {row['written']}"]
        if drops:
            lines += ["dropped at Validate:"] + [f"{stage} x{n}" for stage, n in sorted(drops.items(), key=lambda kv: -kv[1])]
        else:
            lines.append("dropped: none")
        if row["attempts"] > 1:
            lines.append(f"{row['attempts']} attempts")
        axes.text(row["round"], -0.42, "\n".join(lines), ha="center", va="top", fontsize=7.2, color=TEXT_PRIMARY,
                  linespacing=1.35)
        axes.text(row["round"], 1.36, f"round {row['round']}: {row['decision']}", ha="center", fontsize=8,
                  color=DECISION_STYLE[row["decision"]]["colour"])
    axes.text(0, 1.36, "round 0: baseline", ha="center", fontsize=8, color=DECISION_STYLE["baseline"]["colour"])
    axes.text(-0.55, 1.0, "parent line", ha="right", va="center", fontsize=8, color=TEXT_SECONDARY)
    axes.text(-0.55, 0.0, "rejected", ha="right", va="center", fontsize=8, color=TEXT_SECONDARY)
    axes.set_xlim(-1.2, max(r["round"] for r in rows) + 0.6)
    axes.set_ylim(-1.25, 1.5)
    axes.set_title(f"{game}: harness lineage, gate decision per round, and edits dropped at Validate by check",
                   fontsize=11, color=TEXT_PRIMARY, loc="left")
    return _save(figure, FIG_DIR, f"{game}_lineage.png")


def _episode_frames(root: str, entry: dict[str, Any], seed: int) -> np.ndarray:
    episode = next(e for e in entry["episodes"] if e["seed"] == seed)
    return load_frames(_local(episode["frames"], root))


def _board(axes: plt.Axes, grid: np.ndarray, alpha: float = 1.0) -> None:
    axes.imshow(render_board(np.asarray(grid)), alpha=alpha, interpolation="nearest")
    axes.set_xticks([])
    axes.set_yticks([])
    for side in axes.spines.values():
        side.set_color(GRID)


def figure_frame_evidence(game: str, root: str, archive: dict[str, Any]) -> str | None:
    names = ["v0", final_parent(archive)]
    figure, grid = plt.subplots(1, 2, figsize=(11, 5.6), facecolor=SURFACE)
    for axes, name in zip(grid, names):
        analysis = _analysis(root, name)
        if analysis is None:
            axes.set_visible(False)
            continue
        evidence = analysis["frame_evidence"]
        _board(axes, _episode_frames(root, version(archive, name), 1)[0], alpha=0.45)
        clicks = evidence.get("clicks") or []
        if clicks:
            top = max(c["times"] for c in clicks)
            axes.scatter([c["cell"][1] for c in clicks], [c["cell"][0] for c in clicks],
                         s=[12 + 260 * c["times"] / top for c in clicks], facecolors="none",
                         edgecolors=TEXT_PRIMARY, linewidths=1.1, zorder=3)
        rare = [r for r in evidence.get("regions") or [] if r.get("kind") == "rare"]
        for region in rare:
            (r0, r1), (c0, c1) = region["rows"], region["cols"]
            axes.add_patch(Rectangle((c0 - 0.5, r0 - 0.5), c1 - c0 + 1, r1 - r0 + 1, fill=False,
                                     edgecolor=SLOT3, linewidth=2, linestyle=(0, (3, 2)), zorder=4))
            axes.text(c0, r0 - 1, f"{region['id']} {region['steps_changed']}x", fontsize=7, color=TEXT_PRIMARY,
                      va="bottom", zorder=5, bbox={"facecolor": SURFACE, "edgecolor": "none", "pad": 0.6, "alpha": 0.8})
        n_clicks = sum(c["times"] for c in clicks)
        axes.set_title(f"{name}: {n_clicks} clicks on {len(clicks)} cells over {evidence['n_episodes']} episodes;\n"
                       f"{len(rare)} rare-change regions", fontsize=9, color=TEXT_PRIMARY, loc="left")
    handles = [
        Line2D([], [], marker="o", linestyle="none", markerfacecolor="none", markeredgecolor=TEXT_PRIMARY,
               markersize=9, label="click location (size = times clicked)"),
        Line2D([], [], color=SLOT3, linestyle=(0, (3, 2)), linewidth=2,
               label="rare on-screen change (region, times it changed)"),
    ]
    figure.legend(handles=handles, frameon=False, fontsize=8.5, ncol=2, loc="lower center", bbox_to_anchor=(0.5, 0.0))
    figure.suptitle(f"{game}: frame evidence the Meta LLM was shown (start frame of seed 1 behind)",
                    fontsize=11, color=TEXT_PRIMARY, x=0.01, ha="left")
    figure.subplots_adjust(bottom=0.09, top=0.86, wspace=0.05)
    return _save(figure, FIG_DIR, f"{game}_frame_evidence.png")


def _click_records(root: str, entry: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for episode in entry["episodes"]:
        for record in tool_calls(read_records(_local(episode["trajectory"], root))):
            for item in record.get("actions") or []:
                if "record" in item and "x" in item["record"]:
                    out.append(item["record"])
    return out


def figure_click_map(game: str, root: str, archive: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    names = ["v0", final_parent(archive)]
    figure, grid = plt.subplots(1, 2, figsize=(11, 5.8), facecolor=SURFACE)
    stats = {}
    for axes, name in zip(grid, names):
        entry = version(archive, name)
        records = _click_records(root, entry)
        _board(axes, _episode_frames(root, entry, 1)[0], alpha=0.4)
        changed: Counter = Counter()
        unchanged: Counter = Counter()
        for record in records:
            (changed if record["changed"] else unchanged)[(record["x"], record["y"])] += 1
        top = max(list(changed.values()) + list(unchanged.values()) + [1])
        if changed:
            axes.scatter([x for x, _ in changed], [y for _, y in changed],
                         s=[14 + 240 * n / top for n in changed.values()], color=CHANGED, alpha=0.75,
                         edgecolors=SURFACE, linewidths=0.6, zorder=3)
        if unchanged:
            axes.scatter([x for x, _ in unchanged], [y for _, y in unchanged],
                         s=[18 + 240 * n / top for n in unchanged.values()], color=NO_CHANGE, marker="X",
                         alpha=0.85, edgecolors=SURFACE, linewidths=0.6, zorder=4)
        n_no = sum(unchanged.values())
        stats[name] = {"clicks": len(records), "no_effect": n_no, "locations": len(set(changed) | set(unchanged)),
                       "no_effect_locations": len(unchanged)}
        share = f"{n_no / len(records):.0%}" if records else "n/a"
        axes.set_title(f"{name}: {len(records)} clicks, {n_no} changed nothing ({share});\n"
                       f"{stats[name]['locations']} locations clicked, {len(unchanged)} of them with no effect",
                       fontsize=9, color=TEXT_PRIMARY, loc="left")
    handles = [
        Line2D([], [], marker="o", linestyle="none", color=CHANGED, markersize=9, label="click changed something"),
        Line2D([], [], marker="X", linestyle="none", color=NO_CHANGE, markersize=9, label="click changed nothing"),
    ]
    figure.legend(handles=handles, frameon=False, fontsize=8.5, ncol=2, loc="lower center", bbox_to_anchor=(0.5, 0.0))
    figure.suptitle(f"{game}: where the player clicked, seeds 1-5 (size = times; changes every step left out)",
                    fontsize=11, color=TEXT_PRIMARY, x=0.01, ha="left")
    figure.subplots_adjust(bottom=0.09, top=0.86, wspace=0.05)
    return _save(figure, FIG_DIR, f"{game}_click_map.png"), stats


def _would_click(source: str, name: str, grid: np.ndarray) -> int | None:
    """How many actions a skill takes from one frame, with action() stubbed
    (the grid does not change): what it would try, not what it would do."""
    taken = []
    namespace: dict[str, Any] = {"np": np, "grid": lambda: np.asarray(grid).copy(),
                                 "action": lambda *a, **k: taken.append((a, k)) or {"effect": "", "n_changed": 0}}
    try:
        exec(compile(source, f"<{name}>", "exec"), namespace)
        namespace[name]()
    except Exception:
        return None
    return len(taken)


def figure_state_change(game: str, root: str, archive: dict[str, Any], checks: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    drop = next((c for c in checks["state_change"] if c["verdict"] == "no change"), None)
    if drop is None:
        return None, None
    entry = version(archive, next(r["version"] for r in round_rows(archive) if r["round"] == drop["round"]))
    parent = version(archive, entry["parent"])
    attempt = next(a for a in _attempts(root, drop["round"]) if a["attempt"] == drop["attempt"])
    raw = next(e for e in (attempt.get("meta") or {}).get("edits") or [] if e.get("name") == drop["name"])
    states = drop["states"]
    figure, grid = plt.subplots(3, len(states), figsize=(2.6 * len(states), 8.6), facecolor=SURFACE, squeeze=False)
    mid_counts = []
    for column, state in enumerate(states):
        episode = next(e for e in parent["episodes"] if e["seed"] == state["seed"])
        calls = tool_calls(read_records(_local(episode["trajectory"], root)))
        frames = load_frames(_local(episode["frames"], root))
        turn = next(i for i, r in enumerate(calls) if int(r["turn"]) == state["turn"])
        before = frames[int(calls[turn]["frame_index_before"])]
        would = _would_click(raw["content"], drop["name"], before)
        _board(grid[0][column], before)
        grid[0][column].set_title(f"before: seed {state['seed']}, turn {state['turn']}\n"
                                  f"(would try {would} actions)", fontsize=8, color=TEXT_PRIMARY)
        _board(grid[1][column], before)
        grid[1][column].set_title(f"after: {state['actions']} actions,\n{state['cells_changed']} cells changed",
                                  fontsize=8, color=TEXT_PRIMARY)
        middle = len(calls) // 2
        mid = frames[int(calls[middle]["frame_index_before"])]
        count = _would_click(raw["content"], drop["name"], mid)
        mid_counts.append({"seed": state["seed"], "turn": int(calls[middle]["turn"]), "would_try": count})
        _board(grid[2][column], mid)
        grid[2][column].set_title(f"not tested: seed {state['seed']}, turn {calls[middle]['turn']}\n"
                                  f"(would try {count} actions)", fontsize=8, color=NO_CHANGE)
    figure.suptitle(f"{game}: `{drop['name']}` (round {drop['round']}, attempt {drop['attempt']}) dropped by the "
                    f"state-change check\nrows 1-2: the {len(states)} states it was run from (parent "
                    f"{parent['version']}), before and after; row 3: mid-episode states the check did not try",
                    fontsize=10, color=TEXT_PRIMARY, x=0.01, ha="left")
    figure.subplots_adjust(top=0.86, hspace=0.32, wspace=0.08)
    return _save(figure, FIG_DIR, f"{game}_state_change.png"), {"skill": drop["name"], "mid_episode": mid_counts}


def figure_replay(game: str, root: str, archive: dict[str, Any], max_panels: int = 10) -> tuple[str, dict[str, Any]]:
    entry = version(archive, final_parent(archive))
    cleared = [e for e in entry["episodes"] if e["solved"]]
    episode = (min(cleared, key=lambda e: (e["actions_used"], e["seed"])) if cleared
               else max(entry["episodes"], key=lambda e: (e["score"], -e["seed"])))
    frames = load_frames(_local(episode["frames"], root))
    actions = [a for r in tool_calls(read_records(_local(episode["trajectory"], root))) for a in r.get("actions") or []]
    picks = sorted(set(np.linspace(0, len(actions) - 1, min(max_panels - 1, len(actions))).round().astype(int)))
    panels = [(int(actions[i]["frame_before"]), actions[i]) for i in picks]
    panels.append((len(frames) - 1, None))
    cols = min(5, len(panels))
    rows = int(np.ceil(len(panels) / cols))
    figure, grid = plt.subplots(rows, cols, figsize=(2.5 * cols, 2.8 * rows + 0.6), facecolor=SURFACE, squeeze=False)
    for index, (frame_index, action) in enumerate(panels):
        axes = grid[index // cols][index % cols]
        _board(axes, frames[frame_index])
        if action is None:
            axes.set_title(f"end ({episode['end_reason']})", fontsize=8, color=TEXT_PRIMARY)
            continue
        args = action.get("args") or {}
        label = f"step {action['action_index']}: "
        if "x" in args:
            axes.scatter([args["x"]], [args["y"]], s=90, facecolors="none", edgecolors="#ffffff", linewidths=2.2,
                         zorder=3)
            axes.scatter([args["x"]], [args["y"]], s=90, facecolors="none", edgecolors=TEXT_PRIMARY, linewidths=1,
                         zorder=4)
            label += f"click ({args['x']}, {args['y']})"
        else:
            label += action["action"]
        axes.set_title(label, fontsize=8, color=TEXT_PRIMARY)
    for index in range(len(panels), rows * cols):
        grid[index // cols][index % cols].set_visible(False)
    result = "cleared" if episode["solved"] else f"not cleared, score {episode['score']:.2f}"
    figure.suptitle(f"{game}: replay of {entry['version']}, seed {episode['seed']} ({result} in "
                    f"{episode['actions_used']} actions); frame before each shown action, ring = click",
                    fontsize=10, color=TEXT_PRIMARY, x=0.01, ha="left")
    figure.subplots_adjust(top=0.88 if rows > 1 else 0.8, hspace=0.3, wspace=0.06)
    return _save(figure, FIG_DIR, f"{game}_replay.png"), {
        "version": entry["version"], "seed": episode["seed"], "solved": episode["solved"],
        "actions": episode["actions_used"], "score": episode["score"]}


def figure_comparison(data: dict[str, Any]) -> str:
    figure, grid = plt.subplots(1, len(GAMES), figsize=(11.5, 4.2), facecolor=SURFACE)
    series = [("#15, seeds 1-3", RUN15, "15", "_seeds_1_3"), ("#16, seeds 1-3", ROUND_COLOUR[1], "16", "_seeds_1_3"),
              ("#16, seeds 1-5", ROUND_COLOUR[0], "16", "")]
    for axes, game in zip(grid, GAMES):
        _style(axes, grid_axis="y")
        for offset, (label, colour, run, suffix) in zip((-0.27, 0, 0.27), series):
            item = data[game]["comparison"][run]
            values = [item[f"v0_score{suffix}"], item[f"best_score{suffix}"]]
            bars = axes.bar(np.arange(2) + offset, values, width=0.25, color=colour, label=label, zorder=3)
            for bar, value in zip(bars, values):
                axes.annotate(f"{value:.2f}", (bar.get_x() + bar.get_width() / 2, value), textcoords="offset points",
                              xytext=(0, 2), ha="center", fontsize=7.5, color=TEXT_PRIMARY)
        c15, c16 = data[game]["comparison"]["15"], data[game]["comparison"]["16"]
        axes.set_xticks([0, 1])
        axes.set_xticklabels(["v0", f"final parent\n(#15: {c15['final_parent']}, #16: {c16['final_parent']})"], fontsize=8)
        axes.set_ylim(0, 1.12)
        axes.set_title(game, fontsize=10, color=TEXT_PRIMARY, loc="left")
    grid[0].set_ylabel("mean score", fontsize=9, color=TEXT_PRIMARY)
    grid[0].legend(frameon=False, fontsize=8, loc="upper left")
    figure.suptitle("v0 and the final parent, #15 vs #16 (#15's vc33 stopped after round 4)",
                    fontsize=11, color=TEXT_PRIMARY, x=0.01, ha="left")
    figure.tight_layout()
    return _save(figure, FIG_DIR, "comparison.png")


def figure_no_effect(data: dict[str, Any]) -> str:
    figure, grid = plt.subplots(1, len(GAMES), figsize=(11.5, 4.0), facecolor=SURFACE)
    for axes, game in zip(grid, GAMES):
        _style(axes, grid_axis="y")
        for run, colour, marker in (("15", RUN15, "D"), ("16", ROUND_COLOUR[0], "o")):
            rounds = data[game]["clicks_by_round"][run]
            xs = sorted(int(r) for r in rounds)
            axes.plot(xs, [rounds[r]["no_effect_per_episode"] for r in xs], color=colour, marker=marker,
                      linewidth=1.6, label=f"#{run}: no-effect clicks", zorder=3)
            axes.plot(xs, [rounds[r]["repeated_per_episode"] for r in xs], color=colour, marker=marker,
                      linewidth=1.2, linestyle=(0, (4, 3)), markerfacecolor=SURFACE,
                      label=f"#{run}: of those, at a location already tried", zorder=3)
        axes.set_xlabel("round (version evaluated)", fontsize=8.5, color=TEXT_PRIMARY)
        axes.set_title(game, fontsize=10, color=TEXT_PRIMARY, loc="left")
        axes.set_ylim(bottom=0)
    grid[0].set_ylabel("clicks per episode", fontsize=9, color=TEXT_PRIMARY)
    grid[1].legend(frameon=False, fontsize=7.5, loc="upper right")
    figure.suptitle("Clicks that changed nothing per episode (same frame diff for both runs, every-step regions left out)",
                    fontsize=11, color=TEXT_PRIMARY, x=0.01, ha="left")
    figure.tight_layout()
    return _save(figure, FIG_DIR, "no_effect_clicks.png")


# ---------------------------------------------------------------------------


def build_game(game: str, from15: dict[str, Any]) -> dict[str, Any]:
    root, root_15 = root16(game), root15(game)
    archive, archive15 = load_archive(root), load_archive(root_15)
    rows, rows15 = round_rows(archive), round_rows(archive15)
    edits, edits15 = edit_rows(root, archive), edit_rows(root_15, archive15)
    checks = check_rows(archive)
    helpers = helper_rows(root, archive, edits)
    clicks16 = click_counts(root)
    clicks15 = from15[game]["clicks"]
    v0_15 = [r for r in clicks15 if r["round"] == 0 and r["seed"] in (1, 2, 3)]
    v0_16 = [r for r in clicks16 if r["round"] == 0 and r["seed"] in (1, 2, 3)]
    cost = record_cost(root)
    repeats = len(checks["repeats"])
    proposed = sum(r["proposed"] for r in edits)
    figures = [
        figure_score(game, rows, rows15, archive),
        figure_seed_scores(game, rows, archive),
        figure_cost(game, rows, archive, rows15),
        figure_lineage(game, rows, edits),
        figure_frame_evidence(game, root, archive),
    ]
    click_map, click_stats = figure_click_map(game, root, archive)
    state_fig, state_info = figure_state_change(game, root, archive, checks)
    replay_fig, replay_info = figure_replay(game, root, archive)
    figures += [click_map, state_fig, replay_fig]
    return {
        "paths": {"archive": f"{root}/archive.json", "rejected_edits": f"{root}/rejected_edits.jsonl",
                  "trajectories": f"{root}/trajectories/", "frames": f"{root}/frames/",
                  "final_harness": f"{root}/harnesses/{final_parent(archive)}/", "changelog": f"{root}/CHANGELOG.md"},
        "rounds": rows, "rounds_15": rows15, "edits": edits, "edits_15": edits15, "checks": checks,
        "rejected_store": store_rows(root), "section": section_rows(root, archive), "helpers": helpers,
        "failures": failure_rows(root, archive),
        "repeat_rate": {"16": {"proposed": proposed, "dropped_as_repeats": repeats,
                               "rate": round(repeats / proposed, 4) if proposed else None},
                        "15": {k: from15[game]["repeat_check"][k] for k in ("proposed", "would_be_repeats", "repeat_rate")}},
        "clicks": clicks16,
        "clicks_by_round": {"16": clicks_by_round(clicks16), "15": clicks_by_round(clicks15)},
        "v0_seeds_1_3": {
            "15": {"score": next(r for r in rows15 if r["version"] == "v0")["score_mean_seeds_1_3"],
                   "no_effect_per_episode": round(sum(r["no_effect"] for r in v0_15) / len(v0_15), 1),
                   "repeated_per_episode": round(sum(r["repeated_no_effect"] for r in v0_15) / len(v0_15), 1),
                   "clicks_per_episode": round(sum(r["clicks"] for r in v0_15) / len(v0_15), 1)},
            "16": {"score": next(r for r in rows if r["version"] == "v0")["score_mean_seeds_1_3"],
                   "no_effect_per_episode": round(sum(r["no_effect"] for r in v0_16) / len(v0_16), 1),
                   "repeated_per_episode": round(sum(r["repeated_no_effect"] for r in v0_16) / len(v0_16), 1),
                   "clicks_per_episode": round(sum(r["clicks"] for r in v0_16) / len(v0_16), 1)},
        },
        "record_cost": cost,
        "record_cost_summary": {
            "episodes": len(cost), "record_chars_mean": _mean([c["record_chars"] for c in cost]),
            "record_tokens_est_mean": _mean([c["record_tokens_est"] for c in cost]),
            "share_of_input_est_mean": _mean([c["share_of_input_est"] for c in cost if c["share_of_input_est"]]),
            "turns_using_action_log": sum(c["turns_using_action_log"] for c in cost),
            "episodes_using_action_log": sum(1 for c in cost if c["turns_using_action_log"]),
        },
        "click_map": click_stats, "state_change_figure": state_info, "replay": replay_info,
        "action_record_example": action_record_example(root, archive),
        "comparison": {"16": comparison(rows, archive, edits, helpers), "15": comparison(rows15, archive15, edits15, None)},
        "figures": [f.replace(os.sep, "/") for f in figures if f],
    }


def main() -> int:
    from15 = json.load(open(FROM15, encoding="utf-8"))
    data = {game: build_game(game, from15) for game in GAMES}
    data["figures"] = [figure_comparison(data).replace(os.sep, "/"), figure_no_effect(data).replace(os.sep, "/")]
    with open(os.path.join(OUT_DIR, "final.json"), "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=1, default=str)
    for game in GAMES:
        for path in data[game]["figures"]:
            print("wrote", path)
        example = data[game]["action_record_example"]
        print(f"{game}: action record example {example['version']} seed {example['seed']} turn {example['turn']}: "
              f"{example['chars']} chars, logged {example['logged_chars']}, match {example['matches_log']}")
    for path in data["figures"]:
        print("wrote", path)
    print("wrote", os.path.join(OUT_DIR, "final.json"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
