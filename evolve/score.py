"""Per-episode score, per-version summary, and the gate (stage 5).

Score in [0, 1], agreed with the user on 2026-11-01:

    cleared:     0.5 + 0.5 * min(1, human_baseline / actions_to_clear) ** 2
    not cleared: 0.5 * progress,  progress = max(0, 1 - closest / start)

`closest` and `start` are the mover-to-target distances from #8's
approach-distance code (analysis/approach.py), read from the saved frames. A
clear therefore always outscores a non-clear, and among non-clears, getting
closer scores higher. For reference, #8's six ls20 episodes would score
0.21 / 0.09 / 0.09 (Round 0) and 0.47 / 0.09 / 0.26 (Round 1).

Gate: accept the child iff  gain = mean(child) - mean(parent) > 0  and
drop = worst(parent) - worst(child) <= delta.
"""

from __future__ import annotations

import statistics
from typing import Any

from analysis.approach import approach_curve


def episode_metrics(
    frames: Any, solved: bool, steps_to_clear: int | None, human_baseline: int,
    short_id: str = "ls20",
) -> dict[str, Any]:
    curve = approach_curve(frames, short_id)
    start = curve[0] if curve else None
    closest = min(curve) if curve else None
    progress = (
        max(0.0, 1.0 - closest / start) if start and closest is not None else 0.0
    )
    if solved and steps_to_clear:
        score = 0.5 + 0.5 * min(1.0, human_baseline / steps_to_clear) ** 2
    else:
        score = 0.5 * progress
    return {
        "score": round(score, 4),
        "progress": round(progress, 4),
        "start_distance": start,
        "closest_approach": closest,
    }


def summarise(episodes: list[dict[str, Any]]) -> dict[str, Any]:
    scores = [e["score"] for e in episodes]
    clears = [e for e in episodes if e.get("solved")]
    return {
        "n_episodes": len(episodes),
        "score_mean": round(statistics.fmean(scores), 4) if scores else None,
        "score_worst": round(min(scores), 4) if scores else None,
        "score_best": round(max(scores), 4) if scores else None,
        "clear_rate": round(len(clears) / len(episodes), 4) if episodes else None,
        "n_clears": len(clears),
        "avg_steps_to_clear": (
            round(statistics.fmean(e["steps_to_clear"] for e in clears), 1) if clears else None
        ),
        "mean_closest_approach": (
            round(statistics.fmean(e["closest_approach"] for e in episodes
                                   if e.get("closest_approach") is not None), 2)
            if any(e.get("closest_approach") is not None for e in episodes) else None
        ),
    }


def gate(child: dict[str, Any], parent: dict[str, Any], delta: float) -> dict[str, Any]:
    gain = child["score_mean"] - parent["score_mean"]
    drop = parent["score_worst"] - child["score_worst"]
    accept = gain > 0 and drop <= delta
    if accept:
        reason = f"gain {gain:+.4f} > 0 and drop {drop:+.4f} <= {delta}"
    elif gain <= 0:
        reason = f"no dev gain ({gain:+.4f})"
    else:
        reason = f"worst-episode drop {drop:+.4f} > delta {delta}"
    return {
        "gain": round(gain, 4),
        "drop": round(drop, 4),
        "delta": delta,
        "decision": "accepted" if accept else "rejected",
        "reason": reason,
    }
