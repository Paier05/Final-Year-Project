"""Per-episode score and cost, per-version summary, and the gate (stage 5).

Issue #12 replaces #9's score (distance to the rotation switch) with the
goal-progress score of evolve/goal_score.py, in [0, 1], clear = 1.0, and makes
the gate cost-aware. Settings agreed with the user on 2026-11-02:

    cost  (per episode, 0..1) = mean( min(1, tokens / max_tokens_per_episode),
                                      min(1, llm_calls / max_turns),
                                      min(1, env_steps / max_actions) )
          Wall time is recorded but not penalised: it measures server load,
          not the harness.
    gate score (per episode)  g = progress - lambda * cost,  lambda = 0.5

Gate, child vs parent, over the same seeds:

    |mean progress(child) - mean progress(parent)| > epsilon (0.05):
        accept iff mean g(child) - mean g(parent) > 0
               and worst g(parent) - worst g(child) <= delta (0.1)
    within epsilon (a tie on progress):
        accept iff mean cost(child) < mean cost(parent)
               and worst g(parent) - worst g(child) <= delta

So the cheaper version wins a tie, which #9 (where ties were rejected) could
not do. delta is #9's unchanged worst-episode guard.
"""

from __future__ import annotations

import statistics
from typing import Any

from evolve.goal_score import score_episode


def episode_cost(row: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    budget = cfg["budget"]
    tokens = int(row["tokens_in"]) + int(row["tokens_out"])
    calls = int(row["llm_calls"])
    steps = int(row["actions_used"])
    parts = {
        "tokens": min(1.0, tokens / int(budget["max_tokens_per_episode"])),
        "llm_calls": min(1.0, calls / int(budget["max_turns"])),
        "env_steps": min(1.0, steps / int(budget["max_actions"])),
    }
    return {
        "tokens_in": int(row["tokens_in"]),
        "tokens_out": int(row["tokens_out"]),
        "tokens": tokens,
        "llm_calls": calls,
        "env_steps": steps,
        "wall_time_s": float(row.get("wall_time_s") or 0.0),
        "normalised": {k: round(v, 4) for k, v in parts.items()},
        "cost": round(statistics.fmean(parts.values()), 4),
    }


def episode_metrics(records: list[dict[str, Any]], row: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    """Goal progress, cost and gate score of one finished episode."""
    progress = score_episode(records, cfg["game"], cfg["score"]["weights"])
    cost = episode_cost(row, cfg)
    lam = float(cfg["gate"]["lambda"])
    return {
        "score": progress["score"],
        "goal": progress,
        "cost": cost,
        "gate_score": round(progress["score"] - lam * cost["cost"], 4),
    }


def _mean(values: list[float]) -> float | None:
    return round(statistics.fmean(values), 4) if values else None


def summarise(episodes: list[dict[str, Any]]) -> dict[str, Any]:
    scores = [e["score"] for e in episodes]
    gates = [e["gate_score"] for e in episodes]
    costs = [e["cost"]["cost"] for e in episodes]
    clears = [e for e in episodes if e.get("solved")]
    parts = {p: _mean([e["goal"]["parts"][p] for e in episodes]) for p in episodes[0]["goal"]["parts"]} if episodes else {}
    return {
        "n_episodes": len(episodes),
        "seeds": [e.get("seed") for e in episodes],
        "score_mean": _mean(scores),
        "score_std": round(statistics.pstdev(scores), 4) if len(scores) > 1 else 0.0,
        "score_worst": round(min(scores), 4) if scores else None,
        "score_best": round(max(scores), 4) if scores else None,
        "parts_mean": parts,
        "cost_mean": _mean(costs),
        "gate_mean": _mean(gates),
        "gate_worst": round(min(gates), 4) if gates else None,
        "clear_rate": round(len(clears) / len(episodes), 4) if episodes else None,
        "n_clears": len(clears),
        "avg_steps": _mean([e["actions_used"] for e in episodes]),
        "avg_steps_to_clear": (
            round(statistics.fmean(e["steps_to_clear"] for e in clears), 1) if clears else None
        ),
        "tokens_mean": _mean([e["cost"]["tokens"] for e in episodes]),
        "llm_calls_mean": _mean([e["cost"]["llm_calls"] for e in episodes]),
        "wall_time_mean_s": _mean([e["cost"]["wall_time_s"] for e in episodes]),
    }


def gate(child: dict[str, Any], parent: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    g = cfg["gate"]
    delta, eps = float(g["delta"]), float(g["epsilon"])
    d_progress = child["score_mean"] - parent["score_mean"]
    gain = child["gate_mean"] - parent["gate_mean"]
    drop = parent["gate_worst"] - child["gate_worst"]
    d_cost = child["cost_mean"] - parent["cost_mean"]
    tie = abs(d_progress) <= eps
    if tie:
        accept = d_cost < 0 and drop <= delta
        if accept:
            reason = (f"tie on progress (|{d_progress:+.4f}| <= eps {eps}); child cheaper "
                      f"(cost {d_cost:+.4f}); drop {drop:+.4f} <= {delta}")
        elif d_cost >= 0:
            reason = f"tie on progress (|{d_progress:+.4f}| <= eps {eps}); child not cheaper (cost {d_cost:+.4f})"
        else:
            reason = f"tie on progress, child cheaper, but worst-episode drop {drop:+.4f} > delta {delta}"
    else:
        accept = gain > 0 and drop <= delta
        if accept:
            reason = f"gate-score gain {gain:+.4f} > 0 and drop {drop:+.4f} <= {delta}"
        elif gain <= 0:
            reason = f"no gate-score gain ({gain:+.4f}; progress {d_progress:+.4f}, cost {d_cost:+.4f})"
        else:
            reason = f"worst-episode drop {drop:+.4f} > delta {delta}"
    return {
        "rule": "tie-break on cost" if tie else "gate score",
        "progress_diff": round(d_progress, 4),
        "cost_diff": round(d_cost, 4),
        "gain": round(gain, 4),
        "drop": round(drop, 4),
        "delta": delta,
        "epsilon": eps,
        "lambda": float(g["lambda"]),
        "decision": "accepted" if accept else "rejected",
        "reason": reason,
    }
