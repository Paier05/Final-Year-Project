"""Tables for issue #12's report, generated from the run's files.

    python -m analysis.report12 [root]   ->  <root>/report_tables.md

Every number in the report's tables comes from here (archive.json,
rescored_9.json, the trajectories), not from hand-copying.
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from typing import Any

from evolve.action_loop import read_records


def _load(path: str) -> Any:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _decision(entry: dict[str, Any]) -> str:
    return (entry.get("gate") or {}).get("decision", "baseline")


def best_version(versions: list[dict[str, Any]]) -> dict[str, Any]:
    return max(versions, key=lambda v: (v["score_mean"], v["gate_mean"]))


def table_rounds(archive: dict[str, Any]) -> str:
    rows = ["| round | version | parent | mean progress (± SD) | clear rate | avg steps | avg cost | "
            "avg tokens | gate score | decision | reason |",
            "|---|---|---|---|---|---|---|---|---|---|---|"]
    for v in archive["versions"]:
        gate = v.get("gate") or {}
        rows.append(
            f"| {v['round']} | {v['version']} | {v['parent'] or '–'} | {v['score_mean']:.3f} ± {v['score_std']:.3f} | "
            f"{v['n_clears']}/{v['n_episodes']} | {v['avg_steps']:.0f} | {v['cost_mean']:.3f} | "
            f"{v['tokens_mean'] / 1e3:.0f}k | {v['gate_mean']:.3f} | **{_decision(v)}** | "
            f"{gate.get('reason', '').replace('|', chr(92) + '|')} |"  # |x| would end the cell
        )
    for info in archive["rounds"]:
        if info.get("child") is None:
            rows.append(f"| {info['round']} | – | {info['parent_before']} | – | – | – | – | – | – | "
                        f"no valid edits | every edit dropped at Validate |")
    return "\n".join(rows)


def table_seeds(archive: dict[str, Any]) -> str:
    seeds = archive["config"]["seeds"]
    rows = ["| version | " + " | ".join(f"seed {s}" for s in seeds) + " | mean |",
            "|---|" + "---|" * (len(seeds) + 1)]
    for v in archive["versions"]:
        by_seed = {e["seed"]: e for e in v["episodes"]}
        cells = []
        for s in seeds:
            e = by_seed.get(s)
            if e is None:
                cells.append("–")
                continue
            failing = ",".join(p[:3] for p in e["goal"]["failing_parts"]) or "clear"
            cells.append(f"{e['score']:.3f} ({failing})")
        rows.append(f"| {v['version']} ({_decision(v)}) | " + " | ".join(cells) + f" | {v['score_mean']:.3f} |")
    return "\n".join(rows) + "\n\n(in brackets: goal parts failing at the episode's best state; pos = position, rot = rotation)"


def table_edits(archive: dict[str, Any]) -> str:
    rows = ["| round | child | promote | merge | delete | edit | add (other) | from Meta LLM | rule-based | "
            "dropped at Validate (stage) |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    by_round = {v["round"]: v for v in archive["versions"] if v["round"] > 0}
    for info in archive["rounds"]:
        if info["round"] == 0:
            continue
        v = by_round.get(info["round"])
        accepted = (v or {}).get("edits_accepted") or []
        dropped = (v or {}).get("edits_dropped") or info.get("edits_dropped") or []
        kinds = Counter()
        for e in accepted:
            if e.get("op") == "add" and e.get("source") == "rule":
                kinds["promote"] += 1
            elif e.get("op") == "add":
                kinds["add"] += 1
            else:
                kinds[e.get("op")] += 1
        sources = Counter(e.get("source") for e in accepted)
        stages = Counter(d.get("stage") for d in dropped)
        rows.append(
            f"| {info['round']} | {info.get('child') or '–'} ({info['decision']}) | {kinds['promote']} | "
            f"{kinds['merge']} | {kinds['delete']} | {kinds['edit']} | {kinds['add']} | {sources['meta']} | "
            f"{sources['rule']} | {len(dropped)}"
            + (f" ({', '.join(f'{k} {n}' for k, n in stages.items())})" if dropped else "") + " |"
        )
    detail = ["", "Accepted edits, by round:", ""]
    for v in archive["versions"]:
        for e in v.get("edits_accepted") or []:
            flag = " ⚑ unverifiable claims" if e.get("factcheck_verdict") == "unverifiable" else ""
            detail.append(f"- {v['version']} `{e['id']}` [{e['source']}] {e['what']}{flag}")
    return "\n".join(rows + detail)


def table_helpers(archive: dict[str, Any]) -> str:
    """Inline helpers the player wrote, per version; promotions; later use."""
    promoted: dict[str, list[str]] = {}  # skill -> versions it was promoted into
    for v in archive["versions"]:
        for e in v.get("edits_accepted") or []:
            if e.get("source") == "rule" and e.get("op") == "add":
                promoted.setdefault(e["what"].split()[-1], []).append(v["version"])
    rows = ["| version | helper groups written (distinct bodies) | episodes that wrote one | helper calls | "
            "promoted into this version | promoted skills called by its players |",
            "|---|---|---|---|---|---|"]
    for v in archive["versions"]:
        keys, episodes_with, calls = set(), 0, 0
        for e in v["episodes"]:
            wrote = False
            for record in read_records(e["trajectory"]):
                if record.get("type") != "tool_call":
                    continue
                for helper in record.get("inline_helpers_defined") or []:
                    keys.add(helper["key"])
                    wrote = True
                calls += sum((record.get("inline_helper_calls") or {}).values())
            episodes_with += wrote
        here = [n for n, into in promoted.items() if v["version"] in into]
        usage = v.get("skill_usage") or {}
        used = [f"{n} ({usage[n]['calls']} calls)" for n in promoted if n in usage]
        rows.append(f"| {v['version']} | {len(keys)} | {episodes_with}/{len(v['episodes'])} | {calls} | "
                    f"{', '.join(here) or '–'} | {', '.join(used) or '–'} |")
    return "\n".join(rows)


def table_factcheck(archive: dict[str, Any]) -> str:
    rows = ["| round | claims tested | true | false | unverifiable | edits dropped for a false claim | "
            "extraction calls / tokens |",
            "|---|---|---|---|---|---|---|"]
    totals = Counter()
    records = [(v["round"], v.get("factcheck")) for v in archive["versions"] if v["round"] > 0]
    records += [(r["round"], r.get("factcheck")) for r in archive["rounds"] if r.get("child") is None and r["round"] > 0]
    for round_index, facts in sorted(records, key=lambda x: x[0]):
        if not facts:
            continue
        for k in ("n_claims", "true", "false", "unverifiable", "extraction_calls", "extraction_tokens"):
            totals[k] += facts[k]
        totals["dropped"] += len(facts["edits_dropped_for_false"])
        rows.append(f"| {round_index} | {facts['n_claims']} | {facts['true']} | {facts['false']} | "
                    f"{facts['unverifiable']} | {len(facts['edits_dropped_for_false'])} "
                    f"({', '.join(facts['edits_dropped_for_false']) or '–'}) | {facts['extraction_calls']} / "
                    f"{facts['extraction_tokens'] / 1e3:.1f}k |")
    rows.append(f"| **all** | **{totals['n_claims']}** | **{totals['true']}** | **{totals['false']}** | "
                f"**{totals['unverifiable']}** | **{totals['dropped']}** | {totals['extraction_calls']} / "
                f"{totals['extraction_tokens'] / 1e3:.1f}k |")
    false_claims = ["", "Claims labelled false:", ""]
    for round_index, facts in sorted(records, key=lambda x: x[0]):
        for c in (facts or {}).get("claims") or []:
            if c["label"] == "false":
                false_claims.append(f"- round {round_index} `{c['edit']}` ({c['what']}): \"{c['quote']}\" → "
                                    f"{c['evidence']}")
    return "\n".join(rows + false_claims)


def table_comparisons(archive: dict[str, Any], rescored: dict[str, Any]) -> str:
    v0_12 = archive["versions"][0]
    v0_9 = rescored["versions"][0]
    best_12 = best_version(archive["versions"])
    best_9 = best_version(rescored["versions"])
    final_12 = archive["rounds"][-1]["parent_after"]

    def cell(v: dict[str, Any]) -> str:
        return f"{v['score_mean']:.3f} ± {v['score_std']:.3f} (cost {v['cost_mean']:.3f}, g {v['gate_mean']:.3f})"

    rows = ["| comparison | from | to | Δ progress | Δ cost | what it measures |", "|---|---|---|---|---|---|",
            f"| #9 v0 (rescored) → #12 v0 | {cell(v0_9)} | {cell(v0_12)} | "
            f"{v0_12['score_mean'] - v0_9['score_mean']:+.3f} | {v0_12['cost_mean'] - v0_9['cost_mean']:+.3f} | "
            f"the model change alone (same v0 harness; 3 vs 5 episodes) |",
            f"| #12 v0 → #12 best ({best_12['version']}) | {cell(v0_12)} | {cell(best_12)} | "
            f"{best_12['score_mean'] - v0_12['score_mean']:+.3f} | {best_12['cost_mean'] - v0_12['cost_mean']:+.3f} | "
            f"the evolve loop on the new model |",
            f"| #9 best (rescored, {best_9['version']}) → #12 best ({best_12['version']}) | {cell(best_9)} | "
            f"{cell(best_12)} | {best_12['score_mean'] - best_9['score_mean']:+.3f} | "
            f"{best_12['cost_mean'] - best_9['cost_mean']:+.3f} | model + harness changes together |"]
    note = (f"\n\n\"Best\" = highest mean goal progress (ties → higher gate score). #12's final parent (what the "
            f"gate kept) is {final_12}; #9's was {rescored['final_parent_9']}.")
    return "\n".join(rows) + note


def build(root: str) -> str:
    archive = _load(os.path.join(root, "archive.json"))
    rescored = _load(os.path.join(root, "rescored_9.json"))
    sections = [
        ("Per round", table_rounds(archive)),
        ("Per seed (goal progress)", table_seeds(archive)),
        ("Edits per round", table_edits(archive)),
        ("Helpers", table_helpers(archive)),
        ("Fact-check", table_factcheck(archive)),
        ("The three comparisons", table_comparisons(archive, rescored)),
    ]
    text = "\n\n".join(f"### {title}\n\n{body}" for title, body in sections) + "\n"
    path = os.path.join(root, "report_tables.md")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


if __name__ == "__main__":
    print("wrote", build(sys.argv[1] if len(sys.argv) > 1 else os.path.join("results", "evolve_12")))
