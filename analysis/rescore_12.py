"""Rescore #12's episodes with #14's scorer (issue #14, fix 3).

#14 rewrites the rotation part of the goal-progress score as a cyclic
distance between the held rotation index and the goal's. This file re-scores
every #12 episode (rounds 0-5, and the round 6-7 extension) from its logged
game states with the current scorer and compares with what #12 stored, so the
two runs sit on one scale before they are compared.

It also records what the rotation part reads, per episode: the held and the
required index at the best state, the touches still needed, and whether the
episode ever went one touch too far.

    python -m analysis.rescore_12   ->  results/evolve_14/rescored_12.json
"""

from __future__ import annotations

import json
import os
from typing import Any

import yaml

from evolve.action_loop import read_records
from evolve.goal_score import states_from_records, touches_needed
from evolve.score import episode_metrics, summarise

ROOTS = (os.path.join("results", "evolve_12"), os.path.join("results", "evolve_12_round6"))
OUT = os.path.join("results", "evolve_14", "rescored_12.json")


def rescore(cfg: dict[str, Any]) -> dict[str, Any]:
    versions, seen = [], set()
    worst = 0.0
    for root in ROOTS:
        with open(os.path.join(root, "archive.json"), encoding="utf-8") as handle:
            archive = json.load(handle)
        for entry in archive["versions"]:
            if entry["version"] in seen:  # the extension's archive repeats v0-v5
                continue
            seen.add(entry["version"])
            episodes = []
            for episode in entry["episodes"]:
                records = read_records(episode["trajectory"])
                row = dict(episode)
                row |= episode_metrics(records, row, cfg)
                states, _cleared = states_from_records(records)
                held = sorted({s["rotation"] for s in states if s.get("level", 0) == 0})
                row["score_12"] = episode["score"]
                row["rotation_12"] = episode["goal"]["parts"]["rotation"]
                row["rotation_read"] = {
                    "held_indices_seen": held,
                    "goal_index": states[0]["goals"][0]["rotation"],
                    "touches_needed_at_start": touches_needed(states[0]["rotation"], states[0]["goals"][0]["rotation"]),
                }
                worst = max(worst, abs(row["score"] - row["score_12"]),
                            abs(row["goal"]["parts"]["rotation"] - row["rotation_12"]))
                episodes.append(row)
            summary = summarise(episodes)
            versions.append({
                "version": entry["version"], "parent": entry["parent"], "round": entry["round"],
                "root": root.replace(os.sep, "/"),
                "decision_12": (entry.get("gate") or {}).get("decision", "baseline"),
                "score_12_mean": entry["score_mean"],
                "rotation_12_mean": (entry.get("parts_mean") or {}).get("rotation"),
                **summary,
                "episodes": [
                    {k: e.get(k) for k in ("seed", "score", "score_12", "rotation_12", "rotation_read",
                                            "gate_score", "solved", "goal", "cost")}
                    for e in episodes
                ],
            })
    return {
        "note": ("#12's episodes rescored with #14's scorer (analysis/rescore_12.py). The rotation part is "
                 "now a cyclic distance between the held and the required rotation index; #12 compared the "
                 "same two indices for equality."),
        "max_abs_difference_from_12": round(worst, 6),
        "weights": cfg["score"]["weights"],
        "versions": versions,
    }


def main(config: str = "config_evolve.yaml") -> str:
    with open(config, encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle)
    result = rescore(cfg)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=1)
        handle.write("\n")
    print("wrote", OUT)
    for v in result["versions"]:
        overshot = sum(1 for e in v["episodes"] if e["goal"]["ever"]["rotation_overshot"])
        matched = sum(1 for e in v["episodes"] if e["goal"]["ever"]["rotation_matched"])
        print(f"  {v['version']} ({v['decision_12']:>8}): progress {v['score_mean']:.4f} (#12 {v['score_12_mean']:.4f}) "
              f"rotation part {v['parts_mean']['rotation']:.2f} (#12 {v['rotation_12_mean']:.2f}); "
              f"ever matched {matched}/{v['n_episodes']}, ever overshot {overshot}/{v['n_episodes']}")
    print(f"  largest difference from #12's stored scores: {result['max_abs_difference_from_12']}")
    return OUT


if __name__ == "__main__":
    main()
