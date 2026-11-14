"""Progress summary of the issue #14 run, from a local copy of its run directory.

    python -m analysis.progress14 [runs/v3]

Prints the parts of the per-part progress comment that come from the run's own
files: where it stopped, scores and gate decisions so far, speed, and an
estimate of the parts still needed. The job's final state and `seff` come from
the cluster and are added by hand.
"""

from __future__ import annotations

import json
import os
import sys

import yaml


def _read(path: str, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def summary(root: str, config: str = "config_evolve.yaml") -> str:
    with open(config, encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle)
    state = _read(os.path.join(root, "run_state.json"))
    archive = _read(os.path.join(root, "archive.json"), {"versions": [], "rounds": []})
    if state is None:
        return f"{root}: no run_state.json"
    lines = [
        f"**Where the run is:** status `{state['status']}`, round {state['round']}, stage `{state['stage']}` "
        f"({state['stage_status']}), seeds done {state['seeds_done']}, parent `{state['parent_version']}`.",
        f"Commit `{state['git_commit'][:10]}`, config `{state['config_hash']}`, models {state.get('models')}.",
        "",
        "| part | SLURM job | started | ran | stopped because |",
        "|---|---|---|---|---|",
    ]
    for index, part in enumerate(state["segments"], start=1):
        lines.append(f"| {index} | {part.get('slurm_job_id') or '-'} | {part['started']} | "
                     f"{part['seconds'] / 3600:.2f} h | {part.get('stop_reason') or '(still running or killed)'} |")
    lines += ["", f"Total time used: {state['time_used_s'] / 3600:.2f} h.", ""]

    if archive["versions"]:
        lines += ["| version | parent | progress (mean ± SD) | rotation part | clears | avg steps | cost | gate score | decision |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for v in archive["versions"]:
            gate = v["gate"]
            reason = f" ({gate['reason']})" if gate.get("reason") and gate["decision"] != "baseline" else ""
            lines.append(
                f"| {v['version']} | {v['parent'] or '-'} | {v['score_mean']:.3f} ± {v['score_std']:.3f} | "
                f"{v['parts_mean']['rotation']:.2f} | {v['n_clears']}/{v['n_episodes']} | {v['avg_steps']:.0f} | "
                f"{v['cost_mean']:.3f} | {v['gate_mean']:.3f} | {gate['decision']}{reason} |")
        lines.append("")
    for item in archive["rounds"]:
        if item.get("child") is None and item["round"] > 0:
            lines.append(f"Round {item['round']}: no child ({item['decision']}).")

    # Speed and what is left.
    rounds_total = int(cfg["rounds"])
    done = len(archive["rounds"]) - 1 if archive["rounds"] else -1  # rounds 1..N finished (round 0 is the baseline)
    episodes = [c for c in state["completed"] if c.get("unit") == "episode"]
    longest = state["longest_s"].get("episode")
    if episodes and longest:
        guard = cfg.get("checkpoint") or {}
        mean = sum(c["seconds"] for c in episodes) / len(episodes)
        stages = sum(c["seconds"] for c in state["completed"]
                     if c.get("unit") == "stage" and c["stage"] not in ("evaluate",)) / max(1, done + 1)
        per_round = longest + stages  # episodes of a round run in parallel: the slowest sets the pace
        left = max(0, rounds_total - max(done, 0)) if done >= 0 else rounds_total + 1
        usable = float(guard.get("stop_by_min", 340)) * 60
        need = longest * float(guard.get("factor", 1.5))
        per_part = 0
        clock = 0.0
        while clock + need <= usable:  # the guard's own rule
            clock += per_round
            per_part += 1
        per_part = max(per_part, 1)
        lines += [
            f"**Speed:** {len(episodes)} episodes so far, mean {mean / 60:.0f} min, longest {longest / 60:.0f} min; "
            f"a round takes about {per_round / 60:.0f} min (its slowest episode plus the meta stages).",
            f"**Estimate:** {left} round(s) left; the time guard (longest x {guard.get('factor', 1.5)} must fit "
            f"before {guard.get('stop_by_min', 340)} min) allows about {per_part} round(s) per part, so about "
            f"{-(-left // per_part)} more part(s).",
        ]
    replays = state.get("replayed_after_cutoff") or []
    lines.append(f"Episodes replayed after a cut-off: {len(replays)}"
                 + (": " + ", ".join(f"round {r['round']} seed {r['seed']}" for r in replays) if replays else "") + ".")
    for note in state.get("notes") or []:
        lines.append(f"Note ({note['at']}): {note['note']}")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(summary(sys.argv[1] if len(sys.argv) > 1 else os.path.join("runs", "v3")))
