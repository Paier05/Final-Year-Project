"""Build results/summary.csv: one row per game x seed x round.

Also produces results/aggregate.json with the dev/test breakdown that the
report quotes, so no number in REPORT.md is typed by hand.
"""

from __future__ import annotations

import json
import os
from typing import Any

import pandas as pd

RESULTS_DIR = "results"
EPISODES_PATH = os.path.join(RESULTS_DIR, "episodes.jsonl")
SUMMARY_PATH = os.path.join(RESULTS_DIR, "summary.csv")
AGGREGATE_PATH = os.path.join(RESULTS_DIR, "aggregate.json")

COLUMNS = [
    "game",
    "short_id",
    "seed",
    "round",
    "split",
    "solved",
    "end_reason",
    "actions_used",
    "resets_used",
    "steps",
    "human_baseline_actions",
    "level_score",
    "tokens_in",
    "tokens_out",
    "wall_time_s",
    "parse_failures",
    "parse_failure_rate",
    "fallback_actions",
    "module_calls",
    "levels_completed",
    "final_state",
    "error",
]


def load_episodes(path: str = EPISODES_PATH) -> pd.DataFrame:
    if not os.path.exists(path):
        raise SystemExit(
            f"{path} not found. Run a round first (python run.py --round 0)."
        )
    rows: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    if not rows:
        raise SystemExit(f"{path} is empty.")

    frame = pd.DataFrame(rows)
    # A later re-run of the same episode supersedes the earlier record.
    frame = frame.drop_duplicates(subset=["game", "seed", "round"], keep="last")
    frame["tokens_total"] = frame["tokens_in"] + frame["tokens_out"]
    return frame


def build_summary(
    episodes_path: str = EPISODES_PATH, summary_path: str = SUMMARY_PATH
) -> str:
    frame = load_episodes(episodes_path)
    present = [c for c in COLUMNS if c in frame.columns]
    out = frame[present + ["tokens_total"]].sort_values(
        ["round", "split", "game", "seed"]
    )
    os.makedirs(os.path.dirname(summary_path) or ".", exist_ok=True)
    out.to_csv(summary_path, index=False)
    _write_aggregate(frame)
    return summary_path


def _write_aggregate(frame: pd.DataFrame, path: str = AGGREGATE_PATH) -> dict[str, Any]:
    aggregate: dict[str, Any] = {"by_round_split": [], "by_round": []}

    for (round_index, split), group in frame.groupby(["round", "split"]):
        solved = group[group["solved"] == 1]
        aggregate["by_round_split"].append(
            {
                "round": int(round_index),
                "split": str(split),
                "n_episodes": int(len(group)),
                "n_games": int(group["game"].nunique()),
                "solve_rate": round(float(group["solved"].mean()), 4),
                "n_solved": int(group["solved"].sum()),
                "mean_actions_when_solved": (
                    round(float(solved["actions_used"].mean()), 1)
                    if len(solved)
                    else None
                ),
                "mean_level_score_when_solved": (
                    round(float(solved["level_score"].dropna().mean()), 4)
                    if len(solved) and solved["level_score"].notna().any()
                    else None
                ),
                "mean_resets": round(float(group["resets_used"].mean()), 2),
                "tokens_total": int(group["tokens_total"].sum()),
                "wall_time_h": round(float(group["wall_time_s"].sum()) / 3600, 2),
                "parse_failure_rate": round(
                    float(group["parse_failures"].sum())
                    / max(int(group["steps"].sum()), 1),
                    4,
                ),
                "module_calls": int(group.get("module_calls", pd.Series([0])).sum()),
                "n_errors": int((group["error"].astype(str).str.len() > 0).sum()),
            }
        )

    for round_index, group in frame.groupby("round"):
        aggregate["by_round"].append(
            {
                "round": int(round_index),
                "n_episodes": int(len(group)),
                "solve_rate": round(float(group["solved"].mean()), 4),
                "tokens_total": int(group["tokens_total"].sum()),
                "wall_time_h": round(float(group["wall_time_s"].sum()) / 3600, 2),
            }
        )

    # Per-game solve counts, both rounds side by side: the table the report uses.
    per_game: list[dict[str, Any]] = []
    for (game, split), group in frame.groupby(["game", "split"]):
        entry: dict[str, Any] = {
            "game": str(game),
            "short_id": str(game).split("-", 1)[0],
            "split": str(split),
            "human_baseline_actions": (
                int(group["human_baseline_actions"].dropna().iloc[0])
                if group["human_baseline_actions"].notna().any()
                else None
            ),
        }
        for round_index in sorted(frame["round"].unique()):
            sub = group[group["round"] == round_index]
            entry[f"round{int(round_index)}_solved"] = int(sub["solved"].sum())
            entry[f"round{int(round_index)}_seeds"] = int(len(sub))
            solved_sub = sub[sub["solved"] == 1]
            entry[f"round{int(round_index)}_mean_actions_when_solved"] = (
                round(float(solved_sub["actions_used"].mean()), 1)
                if len(solved_sub)
                else None
            )
        per_game.append(entry)
    aggregate["per_game"] = sorted(per_game, key=lambda e: (e["split"], e["short_id"]))

    with open(path, "w", encoding="utf-8") as handle:
        json.dump(aggregate, handle, indent=2)
        handle.write("\n")
    return aggregate
