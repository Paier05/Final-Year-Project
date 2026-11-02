"""Rescore #9's episodes with #12's goal-progress score and cost (issue #12).

#9's trajectories carry no game state, so each episode's states are rebuilt by
replaying its logged actions through the same EpisodeAPI #9 used (ls20 is
deterministic; resets and auto-resets match). Cost uses #9's logged tokens,
turns (+1 call per format retry) and actions, with #12's normalisation, so
both runs sit on one scale.

#9's own gate decisions were made with its old score and are kept as they
were; this file only re-measures the same episodes.

    python evolve_run.py --stage rescore9   ->  results/evolve_12/rescored_9.json
"""

from __future__ import annotations

import json
import os
from typing import Any

from evolve.action_loop import read_records
from evolve.score import episode_metrics, summarise


def llm_calls(records: list[dict[str, Any]]) -> int:
    """#9 did not count calls: one per turn, two when the format was retried."""
    return sum(1 + int(bool(r.get("retried"))) for r in records if r.get("type") == "tool_call")


def rescore(cfg: dict[str, Any], root_9: str) -> dict[str, Any]:
    with open(os.path.join(root_9, "archive.json"), encoding="utf-8") as handle:
        archive = json.load(handle)
    versions = []
    for entry in archive["versions"]:
        episodes = []
        for episode in entry["episodes"]:
            records = read_records(episode["trajectory"])
            row = dict(episode, seed=episode["episode"], llm_calls=llm_calls(records))
            row |= episode_metrics(records, row, cfg)
            row["score_9"] = episode["score"]
            episodes.append(row)
        summary = summarise(episodes)
        versions.append({
            "version": entry["version"],
            "parent": entry["parent"],
            "round": entry["round"],
            "decision_9": (entry.get("gate") or {}).get("decision", "baseline"),
            "score_9_mean": entry["score_mean"],
            **summary,
            "episodes": [
                {k: e.get(k) for k in ("episode", "score", "score_9", "gate_score", "solved", "actions_used",
                                        "turns", "goal", "cost")}
                for e in episodes
            ],
        })
    best_by_progress = max(versions, key=lambda v: (v["score_mean"], v["gate_mean"]))
    final_parent = archive["rounds"][-1]["parent_after"]
    return {
        "note": ("#9's episodes rescored with #12's goal-progress score and cost (analysis/rescore_9.py). "
                 "#9's gate decisions used its own score and are unchanged."),
        "weights": cfg["score"]["weights"],
        "gate": {k: cfg["gate"][k] for k in ("lambda", "epsilon", "delta")},
        "final_parent_9": final_parent,
        "best_by_progress": best_by_progress["version"],
        "versions": versions,
    }


def main(cfg: dict[str, Any], root_9: str, root_12: str) -> str:
    result = rescore(cfg, root_9)
    os.makedirs(root_12, exist_ok=True)
    path = os.path.join(root_12, "rescored_9.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=1)
        handle.write("\n")
    print("wrote", path)
    for v in result["versions"]:
        parts = " ".join(f"{k[:3]}={x:.2f}" for k, x in v["parts_mean"].items())
        print(f"  {v['version']} (#9 {v['decision_9']:>8}, #9 score {v['score_9_mean']:.3f}): "
              f"progress {v['score_mean']:.3f} ± {v['score_std']:.3f} [{parts}] "
              f"cost {v['cost_mean']:.3f} gate {v['gate_mean']:.3f}")
        for e in v["episodes"]:
            ever = e["goal"]["ever"]
            print(f"      ep{e['episode']}: progress {e['score']:.3f} (#9 {e['score_9']:.3f}) "
                  f"failing {e['goal']['failing_parts']} best@{e['goal']['best_state']['action_index']} "
                  f"moves {e['goal']['best_state']['moves_to_goal']}; rotated ever={ever['rotation_matched']} "
                  f"closest-while-matched={ever['closest_moves_to_goal_attributes_matched']} "
                  f"cost {e['cost']['cost']:.3f}")
    print(f"  #9 final parent: {result['final_parent_9']}; best by #12 progress: {result['best_by_progress']}")
    return path
