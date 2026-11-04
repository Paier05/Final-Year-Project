"""The evolution loop: round 0 evaluates v0, rounds 1..N run the meta harness.

    round N:  1 Analyze(parent) -> 2 Propose -> 3 Validate (+ fact-check)
              -> 4 Write vN -> evaluate vN (seeds in parallel) -> 5 Gate vs parent
              -> archive.json (accepted or not); accepted vN becomes the parent

Every stage persists its output under <root>/reports/round_N/ before the next
starts, so an interrupted run resumes where it stopped instead of re-spending
model calls. An episode that did not finish is re-run from scratch.

Issue #12: every version plays the same seeds (cfg["seeds"], 1..5), one
episode per seed, all at once, each with its own env, sandbox and model client.
Episodes are scored by goal progress and cost (evolve/score.py) and the gate is
cost-aware.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable

from harness.model import AbortExperiment, ModelClient, load_api_key
from evolve import analyze as analyze_mod
from evolve.action_loop import EpisodeOutcome, read_records, run_episode
from evolve.factcheck import FactChecker
from evolve.goal_score import read_state
from evolve.harness import Harness, load_harness
from evolve.propose import meta_edits, rule_edits
from evolve.replay import make_env
from evolve.score import episode_metrics, gate, summarise
from evolve.seed_v0 import build_v0
from evolve.validate import validate


@dataclass
class Paths:
    root: str
    title: str = "issue #12"

    @property
    def harnesses(self) -> str:
        return os.path.join(self.root, "harnesses")

    @property
    def trajectories(self) -> str:
        return os.path.join(self.root, "trajectories")

    @property
    def frames(self) -> str:
        return os.path.join(self.root, "frames")

    @property
    def archive(self) -> str:
        return os.path.join(self.root, "archive.json")

    @property
    def changelog(self) -> str:
        return os.path.join(self.root, "CHANGELOG.md")

    def report_dir(self, round_index: int) -> str:
        path = os.path.join(self.root, "reports", f"round_{round_index}")
        os.makedirs(path, exist_ok=True)
        return path


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def _read_json(path: str, default: Any = None) -> Any:
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: str, payload: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, default=str)
        handle.write("\n")
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Clients. Credentials come from QWEN_API_KEY / QWEN_BASE_URL (env or .env)
# and are never written to any output.
# ---------------------------------------------------------------------------


def make_client(cfg: dict[str, Any], section: str, seed: int | None = None) -> ModelClient:
    model = cfg[section]
    limits = cfg["limits"]
    return ModelClient(
        base_url=load_api_key("QWEN_BASE_URL"),
        model=model["model"],
        api_key=load_api_key("QWEN_API_KEY"),
        temperature=float(model["temperature"]),
        top_p=float(model["top_p"]),
        max_tokens=int(model["max_tokens"]),
        thinking=str(model["thinking"]),
        request_timeout_s=int(model["request_timeout_s"]),
        max_transient_retries=int(model["max_transient_retries"]),
        abort_after_consecutive_rate_limits=int(limits["abort_after_consecutive_rate_limits"]),
        global_token_cap=int(limits["global_token_cap"]),
        seed=seed,
    )


# ---------------------------------------------------------------------------
# Archive + changelog
# ---------------------------------------------------------------------------


def load_archive(paths: Paths, cfg: dict[str, Any]) -> dict[str, Any]:
    archive = _read_json(paths.archive)
    if archive is None:
        archive = {
            "experiment": cfg["experiment"],
            "created": _now(),
            "config": {k: cfg[k] for k in ("game", "episodes_per_round", "seeds", "parallel_episodes",
                                           "budget", "score", "gate", "rules", "validate", "factcheck")}
            | {"player_model": cfg["player"]["model"], "meta_model": cfg["meta"]["model"],
               "meta_enabled": cfg["meta"]["enabled"]},
            "versions": [],
            "rounds": [],
        }
    return archive


def save_archive(paths: Paths, archive: dict[str, Any]) -> None:
    archive["updated"] = _now()
    _write_json(paths.archive, archive)


def entry_for(archive: dict[str, Any], version: str) -> dict[str, Any] | None:
    return next((v for v in archive["versions"] if v["version"] == version), None)


def append_changelog(paths: Paths, text: str) -> None:
    new = not os.path.exists(paths.changelog)
    with open(paths.changelog, "a", encoding="utf-8") as handle:
        if new:
            handle.write(f"# CHANGELOG: harness versions for {paths.title} (ls20, level 1)\n\n"
                         "Append-only. One section per version, written at stage 4; "
                         "the gate decision is appended when the version has been evaluated.\n"
                         "Fact-check flags: an accepted edit with claims the game could not "
                         "confirm or refute is marked **UNVERIFIABLE**, with those claims.\n\n")
        handle.write(text.rstrip() + "\n\n")


def _factcheck_lines(item: dict[str, Any]) -> list[str]:
    facts = item.get("factcheck") or {}
    if not facts or facts.get("verdict") == "n/a":
        return []
    lines = [f"  - fact-check: {facts['summary']}"]
    for claim in facts.get("claims") or []:
        if claim["label"] in ("unverifiable", "false"):
            lines.append(f"    - {claim['label'].upper()} \"{claim['quote']}\" ({claim['kind']}): {claim['evidence']}")
    return lines


def changelog_section(harness: Harness, passed: list[dict[str, Any]], dropped: list[dict[str, Any]]) -> str:
    lines = [f"## {harness.version} (parent {harness.parent or '-'}, round {harness.round_index}) — {_now()}"]
    if harness.parent is None:
        lines.append("- seed: issue #8's harness ported to code-acting (see evolve/seed_v0.py); same v0 as #9")
    lines.append(f"Accepted edits ({len(passed)}):")
    for p in passed:
        flag = " **UNVERIFIABLE**" if (p.get("factcheck") or {}).get("verdict") == "unverifiable" else ""
        lines.append(f"- `{p['id']}` [{p['source']}]{flag} {p['what']} — {p['rationale']}".rstrip(" —"))
        lines.extend(_factcheck_lines(p))
    if not passed:
        lines.append("- (none)")
    lines.append(f"Dropped at Validate ({len(dropped)}):")
    for d in dropped:
        lines.append(f"- `{d['id']}` [{d['source']}] {d['what']} — {d['stage']}: {d['reason']}")
        lines.extend(_factcheck_lines(d))
    if not dropped:
        lines.append("- (none)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


EPISODE_FIELDS = (
    "episode", "seed", "score", "gate_score", "solved", "steps_to_clear", "end_reason", "actions_used",
    "turns", "resets_used", "tokens_in", "tokens_out", "llm_calls", "wall_time_s", "parse_failures",
    "cell_errors", "timeouts", "goal", "cost", "trajectory", "frames",
)


def evaluate(
    harness: Harness, round_index: int, cfg: dict[str, Any], paths: Paths,
    client_factory: Callable[[int], Any], log: Callable[[str], None] = print,
) -> list[dict[str, Any]]:
    """Play one episode per seed, all in parallel; resume finished ones."""
    out_path = os.path.join(paths.report_dir(round_index), "episodes.json")
    done = {e["seed"]: e for e in _read_json(out_path, [])}
    seeds = [int(s) for s in cfg["seeds"]]
    todo = [s for s in seeds if s not in done]
    if not todo:
        return [done[s] for s in seeds]

    stop = threading.Event()
    lock = threading.Lock()
    errors: list[BaseException] = []

    def one(seed: int) -> None:
        try:
            # Own env, own sandbox (built inside run_episode), own client:
            # the parallel episodes share no state.
            env = make_env(cfg["game"], seed=seed)
            client = client_factory(seed)
            outcome: EpisodeOutcome = run_episode(
                env=env, client=client, harness=harness, round_index=round_index,
                episode=seed, seed=seed, cfg=cfg, stop_event=stop, traj_root=paths.trajectories,
                frame_root=paths.frames, log=log, probe=read_state,
            )
            if outcome.end_reason == "aborted" or outcome.error:
                raise AbortExperiment(f"seed {seed} ended with {outcome.end_reason}: {outcome.error}")
            row = outcome.as_dict()
            row |= episode_metrics(read_records(outcome.trajectory), row, cfg)
            with lock:
                done[seed] = row
                _write_json(out_path, [done[s] for s in seeds if s in done])
            goal = row["goal"]
            log(
                f"  [{harness.version} seed{seed}] {'CLEARED' if outcome.solved else 'not cleared'} "
                f"progress={row['score']:.3f} parts={goal['parts']} cost={row['cost']['cost']:.3f} "
                f"g={row['gate_score']:.3f} actions={outcome.actions_used} turns={outcome.turns} "
                f"calls={outcome.llm_calls} end={outcome.end_reason} "
                f"tok={outcome.tokens_in + outcome.tokens_out} {outcome.wall_time_s:.0f}s"
            )
        except BaseException as error:  # noqa: BLE001 - surfaced after the pool drains
            stop.set()
            with lock:
                errors.append(error)

    log(f"  evaluating {harness.version}: seeds {todo} in parallel")
    with ThreadPoolExecutor(max_workers=int(cfg["parallel_episodes"])) as pool:
        list(pool.map(one, todo))
    if errors:
        raise AbortExperiment(f"evaluation of {harness.version} stopped: {errors[0]}")
    return [done[s] for s in seeds]


def version_entry(
    harness: Harness, round_index: int, episodes: list[dict[str, Any]], paths: Paths,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    loaded = analyze_mod.load_episodes({"episodes": episodes})
    entry = {
        "version": harness.version,
        "parent": harness.parent,
        "round": round_index,
        "harness_path": os.path.join(paths.harnesses, harness.version).replace(os.sep, "/"),
        "evaluated_at": _now(),
        "episodes": [{k: e.get(k) for k in EPISODE_FIELDS} for e in episodes],
        "tokens": sum(e["tokens_in"] + e["tokens_out"] for e in episodes),
        "skill_usage": analyze_mod.skill_usage_for_entry(harness, loaded),
        # Per version, not only per run: a resumed run may switch models.
        "player_model": cfg["player"]["model"],
        "meta_model": cfg["meta"]["model"],
    }
    entry |= summarise(episodes)
    return entry


def _factcheck_record(attempts: list[dict[str, Any]]) -> dict[str, Any]:
    """Every claim the fact-check tested this round, with its evidence."""
    claims, dropped_for_false = [], []
    tokens = calls = 0
    for attempt in attempts:
        extraction = (attempt.get("info") or {}).get("factcheck_extraction") or {}
        tokens += int(extraction.get("tokens_in") or 0) + int(extraction.get("tokens_out") or 0)
        calls += int(extraction.get("calls") or 0)
        for item in attempt["passed"] + attempt["dropped"]:
            facts = item.get("factcheck") or {}
            for claim in facts.get("claims") or []:
                claims.append({"attempt": attempt["attempt"], "edit": item["id"], "source": item["source"],
                               "what": item["what"], **claim})
            if item.get("stage") == "fact-check":
                dropped_for_false.append(item["id"])
    counts = {label: sum(1 for c in claims if c["label"] == label) for label in ("true", "false", "unverifiable")}
    return {"n_claims": len(claims), **counts, "edits_dropped_for_false": dropped_for_false,
            "extraction_tokens": tokens, "extraction_calls": calls, "claims": claims}


# ---------------------------------------------------------------------------
# The loop
# ---------------------------------------------------------------------------


def run(
    cfg: dict[str, Any], paths: Paths, rounds: int,
    player_factory: Callable[[int], Any], meta_factory: Callable[[], Any] | None,
    log: Callable[[str], None] = print,
    fact_factory: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    os.makedirs(paths.root, exist_ok=True)
    archive = load_archive(paths, cfg)
    use_factcheck = bool((cfg.get("factcheck") or {}).get("enabled"))

    # ---- round 0: v0 baseline ------------------------------------------------
    if entry_for(archive, "v0") is None:
        if os.path.exists(os.path.join(paths.harnesses, "v0", "manifest.json")):
            v0 = load_harness("v0", paths.harnesses)
        else:
            v0 = build_v0()
            v0.save(paths.harnesses)
            append_changelog(paths, changelog_section(v0, [], []))
        log("round 0: evaluating v0")
        episodes = evaluate(v0, 0, cfg, paths, player_factory, log)
        entry = version_entry(v0, 0, episodes, paths, cfg)
        entry |= {"edits_accepted": [], "edits_dropped": [], "accepted": True,
                  "gate": {"decision": "baseline", "reason": "v0 is the starting parent"}}
        archive["versions"].append(entry)
        archive["rounds"].append({"round": 0, "parent_before": None, "child": "v0",
                                  "decision": "baseline", "parent_after": "v0"})
        save_archive(paths, archive)
        append_changelog(paths, f"Gate for v0: baseline — mean progress {entry['score_mean']}, "
                                f"mean cost {entry['cost_mean']}, mean gate score {entry['gate_mean']}, "
                                f"clear rate {entry['clear_rate']}")

    for round_index in range(1, rounds + 1):
        if any(r["round"] == round_index for r in archive["rounds"]):
            continue
        used = sum(int(v.get("tokens") or 0) for v in archive["versions"])
        if used > int(cfg["limits"]["global_token_cap"]):
            archive["stopped_early"] = (
                f"before round {round_index}: {used} tokens used > global cap "
                f"{cfg['limits']['global_token_cap']}"
            )
            save_archive(paths, archive)
            log(f"stopping early: {archive['stopped_early']}")
            break
        parent_name = archive["rounds"][-1]["parent_after"]
        parent = load_harness(parent_name, paths.harnesses)
        parent_entry = entry_for(archive, parent_name)
        version = f"v{round_index}"
        rdir = paths.report_dir(round_index)
        log(f"\nround {round_index}: parent {parent_name} (progress {parent_entry['score_mean']}, "
            f"cost {parent_entry['cost_mean']}, gate {parent_entry['gate_mean']})")

        # ---- 1 · Analyze -----------------------------------------------------
        rejected_since = [
            entry_for(archive, r["child"]) for r in archive["rounds"]
            if r.get("parent_before") == parent_name and r.get("decision") == "rejected"
            and entry_for(archive, r["child"])
        ][-1:]
        report_path = os.path.join(rdir, "analysis.json")
        report = _read_json(report_path)
        if report is None:
            report = analyze_mod.analyze(parent, parent_entry, archive["versions"], rejected_since)
            _write_json(report_path, report)
        log(f"  1 analyze: {len(report['inline_helpers'])} inline-helper groups, "
            f"skills called {sum(s['calls'] for s in report['skill_stats'].values())} times")

        # ---- 2 · Propose + 3 · Validate (one retry if nothing survives) ------
        validation_path = os.path.join(rdir, "validation.json")
        validation = _read_json(validation_path)
        if validation is None:
            episodes = analyze_mod.load_episodes(parent_entry)
            attempts = []
            feedback = None
            for attempt in range(2):
                rules = rule_edits(report, parent, cfg) if attempt == 0 else []
                meta = None
                if meta_factory is not None:
                    meta = meta_edits(report, parent, cfg, meta_factory(), feedback=feedback)
                raw = rules + (meta["edits"] if meta else [])
                log(f"  2 propose (attempt {attempt + 1}): {len(rules)} rule-based, "
                    f"{len(meta['edits']) if meta else 0} from the Meta LLM"
                    + (f" (parse error: {meta['parse_error']})" if meta and meta.get("parse_error") else ""))
                checker = None
                if use_factcheck:
                    checker = FactChecker(cfg, fact_factory() if fact_factory else None, episodes)
                child, passed, dropped, info = validate(parent, raw, episodes, cfg, version, round_index, log,
                                                        factchecker=checker)
                over_cap = (meta or {}).get("over_cap") or []
                for i, extra in enumerate(over_cap, start=1):
                    where = extra.get("name") or extra.get("index") or extra.get("indices")
                    dropped.append({"id": f"r{round_index}-x{i}", "source": "meta",
                                    "what": f"{extra.get('op')} {extra.get('target')} {where}",
                                    "stage": "propose", "reason": "over the per-round edit cap",
                                    "edit": extra})
                attempts.append({"attempt": attempt + 1, "rules": rules, "meta": meta,
                                 "passed": passed, "dropped": dropped, "info": info})
                log(f"  3 validate: {len(passed)} passed, {len(dropped)} dropped")
                if passed:
                    break
                # The reasons are the Meta-facing ones: a fact-check drop says
                # which claim is false, not what is true.
                feedback = "Every edit was dropped at validation:\n" + "\n".join(
                    f"- {d['what']}: {d['stage']}: {d['reason']}" for d in dropped
                ) + "\nPropose edits that address these failures."
            validation = {"attempts": attempts, "final_attempt": len(attempts)}
            _write_json(validation_path, validation)
            _write_json(os.path.join(rdir, "proposals.json"),
                        [{"attempt": a["attempt"], "rules": a["rules"], "meta": a["meta"]} for a in attempts])
        final = validation["attempts"][-1]
        passed, dropped = final["passed"], final["dropped"]
        all_dropped = [d for a in validation["attempts"] for d in a["dropped"]]
        facts = _factcheck_record(validation["attempts"])

        if not passed:
            log(f"  no edit survived validation; round {round_index} ends without a child")
            archive["rounds"].append({"round": round_index, "parent_before": parent_name, "child": None,
                                      "decision": "no valid edits", "parent_after": parent_name,
                                      "edits_dropped": _slim(all_dropped), "factcheck": facts})
            save_archive(paths, archive)
            append_changelog(paths, f"## round {round_index}: no child (parent {parent_name})\n"
                             f"Every proposed edit was dropped at Validate ({len(all_dropped)}).")
            continue

        # ---- 4 · Write vN+1 ----------------------------------------------------
        if os.path.exists(os.path.join(paths.harnesses, version, "manifest.json")):
            child = load_harness(version, paths.harnesses)
        else:
            child, *_ = _rebuild_child(parent, final, cfg, version, round_index)
            child.save(paths.harnesses)
            append_changelog(paths, changelog_section(child, passed, all_dropped))
        log(f"  4 write: {version} with {len(passed)} edits")

        # ---- evaluate + 5 · Gate ------------------------------------------------
        episodes = evaluate(child, round_index, cfg, paths, player_factory, log)
        entry = version_entry(child, round_index, episodes, paths, cfg)
        decision = gate(entry, parent_entry, cfg)
        decision["compared_to"] = parent_name
        entry |= {"edits_accepted": _slim(passed), "edits_dropped": _slim(all_dropped),
                  "gate": decision, "accepted": decision["decision"] == "accepted",
                  "factcheck": facts,
                  "meta_analysis": [((a.get("meta") or {}).get("analysis")) for a in validation["attempts"]],
                  "meta_tokens": sum(int((a.get("meta") or {}).get("tokens_in") or 0)
                                     + int((a.get("meta") or {}).get("tokens_out") or 0)
                                     for a in validation["attempts"]) + facts["extraction_tokens"]}
        archive["versions"].append(entry)
        parent_after = version if entry["accepted"] else parent_name
        archive["rounds"].append({"round": round_index, "parent_before": parent_name, "child": version,
                                  "decision": decision["decision"], "parent_after": parent_after})
        save_archive(paths, archive)
        append_changelog(paths, f"Gate for {version} vs {parent_name}: **{decision['decision']}** "
                                f"({decision['rule']}) — {decision['reason']} (progress {entry['score_mean']} vs "
                                f"{parent_entry['score_mean']}, cost {entry['cost_mean']} vs "
                                f"{parent_entry['cost_mean']}, gate score {entry['gate_mean']} vs "
                                f"{parent_entry['gate_mean']}, worst gate score {entry['gate_worst']} vs "
                                f"{parent_entry['gate_worst']})")
        log(f"  5 gate: {decision['decision']} ({decision['reason']}); parent is now {parent_after}")
    return archive


def _rebuild_child(parent: Harness, final: dict[str, Any], cfg: dict[str, Any], version: str, round_index: int):
    """Re-apply the edits that passed (validation.json stores them, not the harness)."""
    from evolve.edits import Workspace, apply_edit

    ws = Workspace.from_parent(parent, version, round_index)
    for item in final["passed"]:
        apply_edit(ws, item["edit"])
    ws.harness.edits = [
        {"id": p["id"], "source": p["source"], "what": p["what"], "rationale": p["rationale"]}
        for p in final["passed"]
    ]
    return ws.harness, ws


def _slim(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """What the archive keeps per edit. Analyze shows the Meta LLM `what` and
    `reason` from here, so a fact-check `reason` must not state true values
    (see evolve/factcheck.meta_facing_reason); the evidence is kept apart."""
    keep = ("id", "source", "what", "rationale", "stage", "reason", "checks")
    out = []
    for item in items:
        slim = {k: item[k] for k in keep if k in item}
        edit = item.get("edit") or {}
        if isinstance(edit, dict):
            slim["op"] = edit.get("op")
            slim["target"] = edit.get("target")
        facts = item.get("factcheck") or {}
        if facts:
            slim["factcheck_verdict"] = facts.get("verdict")
        out.append(slim)
    return out
