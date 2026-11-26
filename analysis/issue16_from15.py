"""Issue #16, steps 2 and 3, from #15's saved data (no new play).

    python -m analysis.issue16_from15            # writes results/issue16/from15.json

1. The repeat check over #15's runs: walking each game's rounds in order,
   how many proposed edits (rule-based and Meta) repeat an edit rejected
   earlier in that run. The store grows with #15's own outcomes: each
   attempt's Validate drops after the attempt, each Gate-rejected version's
   edits after its Gate. (In #16 a repeat is dropped before it can be tested,
   so later outcomes would differ; this counts what #15 proposed.)
2. The action-record frame diff over #15's trajectories: per episode, clicks
   with no effect, and no-effect clicks at a location already clicked with no
   effect earlier in the episode. Two passes per episode: the first finds the
   regions that change every step (vc33's step bar), the second counts with
   them known from the first action on.
3. The state-change audit of v0: which of v0's skills take actions, and the
   check on each one that does, with #15's round-0 episodes as the parent's.
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys
import tempfile
from collections import Counter
from typing import Any

import numpy as np
import yaml

os.environ.setdefault("OPERATION_MODE", "offline")

from evolve.action_loop import load_frames, read_records  # noqa: E402
from evolve.edits import EditError, normalise  # noqa: E402
from evolve.frame_diff import ActionRecorder  # noqa: E402
from evolve.harness import load_harness  # noqa: E402
from evolve.rejected import RejectedStore, edit_type, make_entry  # noqa: E402
from evolve.replay import tool_calls  # noqa: E402
from evolve.state_change import StateChangeChecker, applies_to, takes_actions  # noqa: E402
from scorer import for_game  # noqa: E402

GAMES = ("ft09", "vc33")
OUT = os.path.join("results", "issue16", "from15.json")


def repeat_rate(root: str, threshold: float = 0.9) -> dict[str, Any]:
    archive = json.load(open(os.path.join(root, "archive.json"), encoding="utf-8"))
    store = RejectedStore(os.path.join(tempfile.mkdtemp(prefix="rep15_"), "rejected_edits.jsonl"))
    decisions = {r["round"]: r for r in archive["rounds"]}
    proposed = repeats = 0
    by_type: Counter = Counter()
    repeats_by_type: Counter = Counter()
    found = []
    for round_index in sorted(r for r in decisions if r > 0):
        decision = decisions[round_index]
        parent = load_harness(decision["parent_before"], os.path.join(root, "harnesses"))
        path = os.path.join(root, "reports", f"round_{round_index}", "attempts.json")
        if not os.path.exists(path):
            path = os.path.join(root, "reports", f"round_{round_index}", "validation.json")
        attempts = json.load(open(path, encoding="utf-8"))
        attempts = attempts["attempts"] if isinstance(attempts, dict) else attempts
        for attempt in attempts:
            raw = attempt["rules"] + ((attempt.get("meta") or {}).get("edits") or [])
            for index, item in enumerate(raw, start=1):
                try:
                    edit = normalise(item, item.get("source", "meta"))
                except EditError:
                    continue
                proposed += 1
                by_type[edit_type(edit)] += 1
                match = store.match(edit, parent, threshold)
                if match is not None:
                    earlier, score = match
                    repeats += 1
                    repeats_by_type[edit_type(edit)] += 1
                    found.append({"round": round_index, "attempt": attempt["attempt"], "edit": f"r{round_index}-e{index}",
                                  "source": edit["source"], "type": edit_type(edit), "op": edit["op"],
                                  "target": edit["target"], "name": edit.get("name") or edit.get("index"),
                                  "repeats": earlier["id"], "earlier_rejected_by": earlier["rejected_by"],
                                  "similarity": round(score, 4)})
            for item in attempt.get("dropped") or []:
                edit = item.get("edit")
                if item.get("stage") == "propose" or not isinstance(edit, dict) or "op" not in edit:
                    continue
                store.add(make_entry(f"r{round_index}-a{attempt['attempt']}-e{item['id'].split('-e')[-1]}",
                                     round_index, f"v{round_index}", edit, parent, f"validate: {item['stage']}"))
        if decision["decision"] == "rejected":
            entry = next(v for v in archive["versions"] if v["version"] == decision["child"])
            for item in attempts[-1]["passed"]:
                store.add(make_entry(f"r{round_index}-gate-e{item['id'].split('-e')[-1]}", round_index,
                                     decision["child"], item["edit"], parent, f"gate: {entry['gate']['reason']}"))
    return {"proposed": proposed, "would_be_repeats": repeats,
            "repeat_rate": round(repeats / proposed, 4) if proposed else None,
            "proposed_by_type": dict(by_type), "repeats_by_type": dict(repeats_by_type),
            "rejected_in_store_at_end": len(store.entries), "repeats": found}


def _actions(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [a for r in tool_calls(records) for a in r.get("actions") or []]


def no_effect_clicks(trajectory: str, frames_path: str) -> dict[str, Any]:
    """Clicks with no effect and repeated no-effect clicks in one episode."""
    frames = load_frames(frames_path)
    actions = _actions(read_records(trajectory))

    def run(known: list) -> ActionRecorder:
        recorder = ActionRecorder(known)
        for item in actions:
            recorder.add(item["action_index"], item["action"], item.get("args"),
                         np.asarray(frames[item["frame_before"]]), np.asarray(frames[item["frame_after"]]),
                         game_over="auto_reset_frame" in item, level_restarted="auto_reset_frame" in item)
        return recorder

    first = run([])
    second = run(first.every_step())
    clicks = [r for r in second.records if "x" in r]
    seen: Counter = Counter()
    repeated = 0
    for record in clicks:
        if not record["changed"]:
            where = (record["x"], record["y"])
            if seen[where]:
                repeated += 1
            seen[where] += 1
    no_effect = sum(1 for r in clicks if not r["changed"])
    return {"clicks": len(clicks), "no_effect": no_effect, "repeated_no_effect": repeated,
            "no_effect_share": round(no_effect / len(clicks), 4) if clicks else None,
            "every_step_regions": [list(b) for b in first.every_step()]}


def click_counts(root: str) -> list[dict[str, Any]]:
    out = []
    for trajectory in sorted(glob.glob(os.path.join(root, "trajectories", "round_*", "seed_*.jsonl"))):
        round_index = int(re.search(r"round_(\d+)", trajectory).group(1))
        seed = int(re.search(r"seed_(\d+)", trajectory).group(1))
        frames = trajectory.replace("trajectories", "frames").replace(".jsonl", ".npz")
        out.append({"round": round_index, "seed": seed, **no_effect_clicks(trajectory, frames)})
    return out


def audit_v0(game: str, root: str) -> dict[str, Any]:
    from evolve_run import apply_game

    cfg = yaml.safe_load(open("config_evolve_16.yaml", encoding="utf-8"))
    apply_game(cfg, game)
    archive = json.load(open(os.path.join(root, "archive.json"), encoding="utf-8"))
    entry = next(v for v in archive["versions"] if v["version"] == "v0")
    episodes = []
    for item in entry["episodes"]:
        name = os.path.basename(item["trajectory"])
        episodes.append({**item, "records": read_records(os.path.join(root, "trajectories", "round_0", name)),
                         "frames": os.path.join(root, "frames", "round_0", name.replace(".jsonl", ".npz"))})
    v0 = load_harness("v0", os.path.join(root, "harnesses"))
    checker = StateChangeChecker(cfg, episodes, for_game(cfg["game"]).read_state)
    skills = {}
    for name in sorted(v0.skills):
        edit = {"op": "edit", "target": "skill", "name": name, "content": v0.skills[name], "source": "audit"}
        if applies_to(edit, v0):
            skills[name] = {"takes_actions": True, **checker.check(edit, v0)}
        else:
            skills[name] = {"takes_actions": takes_actions(v0, name), "verdict": "not checked (read-only helper)"}
    return {"harness": os.path.join(root, "harnesses", "v0").replace(os.sep, "/"), "skills": skills,
            "action_taking": [n for n, s in skills.items() if s["takes_actions"]],
            "every_step_regions": [list(b) for b in checker.regions], "every_step_fields": checker.fields}


def main() -> None:
    result: dict[str, Any] = {}
    for game in GAMES:
        root = os.path.join("runs", game)
        counts = click_counts(root)
        rounds = {}
        for row in counts:
            rounds.setdefault(row["round"], []).append(row)
        result[game] = {
            "repeat_check": repeat_rate(root),
            "clicks": counts,
            "clicks_by_round": {r: {"clicks": sum(x["clicks"] for x in rows), "no_effect": sum(x["no_effect"] for x in rows),
                                    "repeated_no_effect": sum(x["repeated_no_effect"] for x in rows)}
                                for r, rows in sorted(rounds.items())},
            "v0_audit": audit_v0(game, root),
        }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=1)
    for game, data in result.items():
        rep = data["repeat_check"]
        print(f"{game}: {rep['would_be_repeats']} of {rep['proposed']} proposed edits would be dropped as repeats "
              f"({rep['repeat_rate']:.0%}); by type {rep['repeats_by_type']} of {rep['proposed_by_type']}")
        for item in rep["repeats"]:
            print(f"    round {item['round']} {item['edit']} [{item['source']}] {item['op']} {item['target']} "
                  f"{item['name']} repeats {item['repeats']} ({item['earlier_rejected_by'][:40]}), sim {item['similarity']}")
        total = {k: sum(r[k] for r in data["clicks"]) for k in ("clicks", "no_effect", "repeated_no_effect")}
        print(f"  clicks: {total['clicks']} in {len(data['clicks'])} episodes, {total['no_effect']} with no effect, "
              f"{total['repeated_no_effect']} of those repeated at a location already clicked with no effect")
        for r, row in data["clicks_by_round"].items():
            print(f"    round {r}: {row}")
        audit = data["v0_audit"]
        print(f"  v0 audit: action-taking skills {audit['action_taking'] or 'none'}; "
              + "; ".join(f"{n}: {s['verdict']}" for n, s in audit["skills"].items()))
    print("wrote", OUT)


if __name__ == "__main__":
    sys.exit(main())
