"""Stage 1 · Analyze: trajectories + old harness -> a report for Propose.

Inputs are the parent version's episodes (its trajectories and frames) and the
archive, which carries the lineage: what earlier rounds tried and whether it
was accepted. The report has the two things the issue names -- skill stats and
inline-helper usage -- plus what Propose needs to act on them:

- per-episode outcome, score, action mix and final notes;
- skill stats: calls, errors, last error, episodes used in, and lifetime usage
  across every evaluated version that carried the same source;
- inline helpers: functions the player wrote in its own cells, grouped by body
  (so the same helper under two names is one group), with how many episodes
  defined it and how often it was called;
- what each action actually did, measured from the saved frames with #8's
  generic rigid-translation detector (no game-specific colour roles);
- the most common cell errors;
- a short excerpt of the best and worst episodes.

The progress measure itself (the mover/target roles in analysis/approach.py)
is deliberately *not* described here: Propose sees the score per episode, not
how the evaluator computes it, so no hint about the goal leaks into the harness.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from typing import Any

import numpy as np

from evolve.action_loop import load_frames, read_records
from evolve.harness import Harness
from evolve.replay import tool_calls
from learning.mine import _translation


def source_hash(source: str) -> str:
    return hashlib.sha1(source.strip().encode("utf-8")).hexdigest()[:12]


def _translation_between(before: np.ndarray, after: np.ndarray) -> tuple[int, int] | None:
    if before.shape != after.shape:
        return None
    rows, cols = np.nonzero(before != after)
    if rows.size == 0:
        return None
    cells = [
        {"row": int(r), "col": int(c), "from": int(before[r, c]), "to": int(after[r, c])}
        for r, c in zip(rows, cols)
    ]
    return _translation({"frame_diff": {"changed": cells, "truncated": False}})


def action_effects(episodes: list[dict[str, Any]]) -> dict[str, Any]:
    """Per action: how often it changed nothing, and its most common rigid move."""
    stats: dict[str, Counter] = defaultdict(Counter)
    totals: Counter = Counter()
    for episode in episodes:
        frames = load_frames(episode["frames"])
        for record in tool_calls(episode["records"]):
            for item in record.get("actions") or []:
                name = item["action"]
                totals[name] += 1
                if not item.get("n_changed"):
                    stats[name]["no change"] += 1
                    continue
                move = _translation_between(
                    np.asarray(frames[item["frame_before"]]),
                    np.asarray(frames[item["frame_after"]]),
                )
                stats[name][f"rigid move (drow={move[0]}, dcol={move[1]})" if move else "other change"] += 1
    out = {}
    for name in sorted(totals):
        top = stats[name].most_common(3)
        out[name] = {
            "n": totals[name],
            "effects": [{"effect": label, "share": round(n / totals[name], 2)} for label, n in top],
        }
    return out


def skill_stats(
    harness: Harness, episodes: list[dict[str, Any]], archive: list[dict[str, Any]]
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, source in sorted(harness.skills.items()):
        calls = errors = shadowed = 0
        used_in: set[int] = set()
        last_error = None
        for episode in episodes:
            for record in tool_calls(episode["records"]):
                n = int((record.get("skill_calls") or {}).get(name, 0))
                calls += n
                errors += int((record.get("skill_errors") or {}).get(name, 0))
                if n:
                    used_in.add(episode["episode"])
                    if (record.get("skill_errors") or {}).get(name):
                        last_error = record.get("error")
                if name in (record.get("shadowed_skills") or []):
                    shadowed += 1
        # Lifetime: every evaluated version that carried this exact source.
        digest = source_hash(source)
        life_episodes = life_calls = 0
        for entry in archive:
            usage = (entry.get("skill_usage") or {}).get(name)
            if usage and usage.get("source_hash") == digest:
                life_episodes += int(entry.get("n_episodes") or 0)
                life_calls += int(usage.get("calls") or 0)
        out[name] = {
            "calls": calls,
            "errors": errors,
            "episodes_used": len(used_in),
            "last_error": last_error,
            "times_redefined_by_player": shadowed,
            "lifetime_episodes": life_episodes,
            "lifetime_calls": life_calls,
            "source_hash": digest,
        }
    return out


def inline_helpers(harness: Harness, episodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for episode in episodes:
        current: dict[str, str] = {}  # name -> key of its latest definition
        for record in tool_calls(episode["records"]):
            for item in record.get("inline_helpers_defined") or []:
                if item["name"] in harness.skills:
                    continue  # re-definitions of skills are counted in skill stats
                current[item["name"]] = item["key"]
                group = groups.setdefault(
                    item["key"],
                    {"key": item["key"], "names": Counter(), "episodes": set(),
                     "turns_defined": 0, "calls": 0, "sources": Counter()},
                )
                group["names"][item["name"]] += 1
                group["episodes"].add(episode["episode"])
                group["turns_defined"] += 1
                group["sources"][item["source"]] += 1
            for name, n in (record.get("inline_helper_calls") or {}).items():
                key = current.get(name)
                if key in groups:
                    groups[key]["calls"] += int(n)
    out = []
    for group in groups.values():
        name = group["names"].most_common(1)[0][0]
        source = group["sources"].most_common(1)[0][0]
        out.append(
            {
                "name": name,
                "other_names": sorted(set(group["names"]) - {name}),
                "key": group["key"],
                "episodes_defined": len(group["episodes"]),
                "turns_defined": group["turns_defined"],
                "calls": group["calls"],
                "n_lines": len(source.splitlines()),
                "source": source,
            }
        )
    out.sort(key=lambda g: (-g["episodes_defined"], -g["calls"], g["name"]))
    return out


def common_errors(episodes: list[dict[str, Any]], top: int = 8) -> list[dict[str, Any]]:
    counter: Counter = Counter()
    for episode in episodes:
        for record in tool_calls(episode["records"]):
            error = record.get("error")
            if error:
                counter[re.sub(r"\(line \d+\)", "", error).strip()[:200]] += 1
    return [{"error": e, "count": n} for e, n in counter.most_common(top)]


def _run_length(actions: list[str]) -> str:
    out: list[str] = []
    for action in actions:
        short = action.replace("ACTION", "A")
        if out and out[-1].split("x")[0] == short:
            count = int(out[-1].split("x")[1]) + 1
            out[-1] = f"{short}x{count}"
        else:
            out.append(f"{short}x1")
    return " ".join(out)


def episode_digest(episode: dict[str, Any]) -> dict[str, Any]:
    records = tool_calls(episode["records"])
    actions = [a["action"] for r in records for a in (r.get("actions") or [])]
    zero_action_turns = sum(1 for r in records if not r.get("actions"))
    counts = Counter(actions)
    return {
        "episode": episode["episode"],
        "score": episode["score"],
        "solved": episode["solved"],
        "steps_to_clear": episode.get("steps_to_clear"),
        "end_reason": episode["end_reason"],
        "actions_used": episode["actions_used"],
        "turns": len(records),
        "turns_with_no_action": zero_action_turns,
        "cell_errors": sum(1 for r in records if r.get("error")),
        "parse_failures": sum(1 for r in records if r.get("parse_failure")),
        "action_counts": dict(sorted(counts.items())),
        "action_sequence": _run_length(actions)[:600],
        "final_notes": (records[-1].get("notes") if records else "")[:800],
    }


def excerpt(episode: dict[str, Any], n_turns: int = 2, max_chars: int = 1400) -> list[dict[str, Any]]:
    out = []
    for record in tool_calls(episode["records"])[-n_turns:]:
        out.append(
            {
                "turn": record["turn"],
                "reply": (record.get("reply") or "")[:max_chars],
                "actions": [f"{a['action']} -> {a['effect']}" for a in record.get("actions") or []],
                "error": record.get("error"),
                "stdout": (record.get("stdout") or "")[:400],
            }
        )
    return out


def load_episodes(entry: dict[str, Any]) -> list[dict[str, Any]]:
    episodes = []
    for item in entry["episodes"]:
        episode = dict(item)
        episode["records"] = read_records(item["trajectory"])
        episodes.append(episode)
    return episodes


def analyze(
    parent: Harness, parent_entry: dict[str, Any], archive: list[dict[str, Any]],
    extra_entries: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the round's report. `extra_entries` = recent rejected children,
    whose episodes are summarised (not mined) so Propose sees what failed."""
    episodes = load_episodes(parent_entry)
    ranked = sorted(episodes, key=lambda e: e["score"])
    history = [
        {
            "version": e["version"],
            "parent": e.get("parent"),
            "round": e["round"],
            "score_mean": e.get("score_mean"),
            "score_worst": e.get("score_worst"),
            "clear_rate": e.get("clear_rate"),
            "decision": (e.get("gate") or {}).get("decision", "baseline"),
            "edits": [
                {"source": x.get("source"), "what": x.get("what"), "rationale": (x.get("rationale") or "")[:200]}
                for x in e.get("edits_accepted") or []
            ],
            "dropped_at_validate": [
                {"what": x.get("what"), "why": x.get("reason")}
                for x in e.get("edits_dropped") or []
            ],
        }
        for e in archive
    ]
    rejected = []
    for entry in extra_entries or []:
        rejected.append(
            {
                "version": entry["version"],
                "score_mean": entry.get("score_mean"),
                "gate": entry.get("gate"),
                "episodes": [episode_digest(e) for e in load_episodes(entry)],
            }
        )
    return {
        "version": parent.version,
        "summary": {k: parent_entry.get(k) for k in
                    ("score_mean", "score_worst", "clear_rate", "avg_steps_to_clear",
                     "mean_closest_approach")},
        "episodes": [episode_digest(e) for e in episodes],
        "skill_stats": skill_stats(parent, episodes, archive),
        "inline_helpers": inline_helpers(parent, episodes),
        "action_effects": action_effects(episodes),
        "common_errors": common_errors(episodes),
        "excerpts": {
            "best_episode": excerpt(ranked[-1]) if ranked else [],
            "worst_episode": excerpt(ranked[0]) if ranked else [],
        },
        "history": history,
        "recent_rejected_children": rejected,
    }


def skill_usage_for_entry(harness: Harness, episodes: list[dict[str, Any]]) -> dict[str, Any]:
    """Per-skill usage of one evaluated version, stored in its archive entry."""
    usage = {}
    for name, source in harness.skills.items():
        calls = errors = 0
        for episode in episodes:
            for record in tool_calls(episode["records"]):
                calls += int((record.get("skill_calls") or {}).get(name, 0))
                errors += int((record.get("skill_errors") or {}).get(name, 0))
        usage[name] = {"calls": calls, "errors": errors, "source_hash": source_hash(source)}
    return usage
