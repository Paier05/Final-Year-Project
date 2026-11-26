"""The evolution loop: round 0 evaluates v0, rounds 1..N run the meta harness.

    round N:  1 Analyze(parent) -> 2 Propose -> 3 Validate (+ fact-check,
              + skill-name check) -> 4 Write vN -> evaluate vN (seeds in
              parallel) -> 5 Gate vs parent
              -> archive.json (accepted or not); accepted vN becomes the parent

Every stage persists its output under <root>/reports/round_N/ before the next
starts, so an interrupted run resumes where it stopped instead of re-spending
model calls. An episode that did not finish is re-run from scratch.

Issue #12: every version plays the same seeds (cfg["seeds"], 1..5), one
episode per seed, all at once, each with its own env, sandbox and model client.
Episodes are scored by goal progress and cost (evolve/score.py) and the gate is
cost-aware.

Issue #14: the run is checkpointed (evolve/checkpoint.py). run_state.json is
saved after every finished episode and every finished stage; a unit that will
not fit in the job's time left is not started; a stop request (time guard,
SIGUSR1) ends the run cleanly with StopRun. On resume a cut-off episode's
files go to partial/ and its seed is replayed; a cut-off stage left no output
and runs again. Propose and Validate are saved separately (attempts.json), so
a cut during Validate does not repeat the Meta LLM call.

Issue #16 (each switched on by its config): Validate's repeat check reads
<root>/rejected_edits.jsonl, which is brought up to date from the round
reports and the archive before every Validate and after every Gate (so a cut
anywhere cannot lose a rejection); Validate's state-change check; and the
"Rejected since current parent" section of the Meta LLM's input, built at
Analyze and stored in analysis.json with the rest of the report.
"""

from __future__ import annotations

import datetime as dt
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable

from harness.model import AbortExperiment, ModelClient, load_api_key
from evolve import analyze as analyze_mod
from evolve.action_loop import EpisodeOutcome, frames_path, read_records, run_episode, trajectory_path
from evolve.checkpoint import Checkpoint, StopRun, move_partial, read_json, write_json_atomic
from evolve.factcheck import FactChecker
from scorer import for_game
from evolve.harness import Harness, load_harness
from evolve.propose import meta_edits, rule_edits
from evolve.rejected import STORE_FILE, RejectedStore, rejected_since_parent, render_section
from evolve.rejected import sync as sync_rejected
from evolve.replay import make_env
from evolve.score import episode_metrics, gate, summarise
from evolve.seed_v0 import build_v0
from evolve.state_change import StateChangeChecker
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


_read_json = read_json
_write_json = write_json_atomic


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
               "meta_enabled": cfg["meta"]["enabled"]}
            | ({"action_record": cfg["action_record"], "rejected_section": cfg["meta"].get("rejected_section")}
               if "action_record" in cfg else {}),
            "versions": [],
            "rounds": [],
        }
    return archive


def save_archive(paths: Paths, archive: dict[str, Any]) -> None:
    archive["updated"] = _now()
    _write_json(paths.archive, archive)


def entry_for(archive: dict[str, Any], version: str) -> dict[str, Any] | None:
    return next((v for v in archive["versions"] if v["version"] == version), None)


def append_changelog(paths: Paths, text: str, key: str | None = None) -> None:
    """Append a section. With `key` (the section's first words), a section
    already there is not written again: a stage that is re-run after a cut
    must not duplicate its CHANGELOG entry."""
    new = not os.path.exists(paths.changelog)
    if key and not new:
        with open(paths.changelog, encoding="utf-8") as handle:
            if any(line.startswith(key) for line in handle):
                return
    with open(paths.changelog, "a", encoding="utf-8") as handle:
        if new:
            handle.write(f"# CHANGELOG: harness versions for {paths.title} (ls20, level 1)\n\n"
                         "Append-only. One section per version, written at stage 4; "
                         "the gate decision is appended when the version has been evaluated.\n"
                         "Fact-check flags: an accepted edit with claims the game could not "
                         "confirm or refute is marked **UNVERIFIABLE**, with those claims.\n"
                         "Skill-name check: an edit dropped for naming a skill that does not "
                         "exist lists each missing name with its file and line.\n\n")
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


def _missing_name_lines(item: dict[str, Any]) -> list[str]:
    return [
        f"  - missing skill name `{m['name']}`: {m['file']} line {m['line']} ({m['where']}): {m['text']}"
        for m in item.get("missing_names") or []
    ]


def _state_change_lines(item: dict[str, Any]) -> list[str]:
    outcome = item.get("state_change") or {}
    if not outcome:
        return []
    lines = [f"  - state-change check: {outcome['summary']} (called with {outcome['call']}; "
             f"{outcome['env_steps']} env steps)"]
    for state in outcome.get("states") or []:
        lines.append(f"    - seed {state['seed']} turn {state['turn']}: {state['verdict']}"
                     + (f" ({state['why']})" if state.get("why") else
                        f" ({state.get('actions')} actions, {state.get('cells_changed')} cells changed, "
                        f"game state changed: {state.get('game_state_changed')})"))
    return lines


def changelog_section(harness: Harness, passed: list[dict[str, Any]], dropped: list[dict[str, Any]]) -> str:
    lines = [f"## {harness.version} (parent {harness.parent or '-'}, round {harness.round_index}) — {_now()}"]
    if harness.parent is None:
        lines.append("- seed: issue #8's harness ported to code-acting (see evolve/seed_v0.py); same v0 as #9")
    lines.append(f"Accepted edits ({len(passed)}):")
    for p in passed:
        flag = " **UNVERIFIABLE**" if (p.get("factcheck") or {}).get("verdict") == "unverifiable" else ""
        if (p.get("state_change") or {}).get("verdict") == "unverifiable":
            flag += " **STATE-CHANGE UNVERIFIABLE**"
        lines.append(f"- `{p['id']}` [{p['source']}]{flag} {p['what']} — {p['rationale']}".rstrip(" —"))
        lines.extend(_factcheck_lines(p))
        lines.extend(_state_change_lines(p))
    if not passed:
        lines.append("- (none)")
    lines.append(f"Dropped at Validate ({len(dropped)}):")
    for d in dropped:
        lines.append(f"- `{d['id']}` [{d['source']}] {d['what']} — {d['stage']}: {d['reason']}")
        lines.extend(_factcheck_lines(d))
        lines.extend(_missing_name_lines(d))
        lines.extend(_state_change_lines(d))
    if not dropped:
        lines.append("- (none)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


EPISODE_FIELDS = (
    "episode", "seed", "score", "gate_score", "solved", "steps_to_clear", "end_reason", "actions_used",
    "turns", "resets_used", "tokens_in", "tokens_out", "llm_calls", "wall_time_s", "parse_failures",
    "cell_errors", "timeouts", "goal", "cost", "trajectory", "frames", "player_model",
)


class _EitherEvent:
    """Set when any of the events is set (an episode watches one object)."""

    def __init__(self, *events: threading.Event) -> None:
        self.events = events

    def is_set(self) -> bool:
        return any(e.is_set() for e in self.events)


def evaluate(
    harness: Harness, round_index: int, cfg: dict[str, Any], paths: Paths,
    client_factory: Callable[[int], Any], log: Callable[[str], None] = print,
    ckpt: Checkpoint | None = None,
) -> list[dict[str, Any]]:
    """Play one episode per seed, all in parallel; resume finished ones."""
    out_path = os.path.join(paths.report_dir(round_index), "episodes.json")
    done = {e["seed"]: e for e in _read_json(out_path, [])}
    seeds = [int(s) for s in cfg["seeds"]]
    todo = [s for s in seeds if s not in done]
    if not todo:
        return [done[s] for s in seeds]

    if ckpt is not None:
        ckpt.position(round_index, "evaluate", "running", harness.parent, seeds_done=list(done))
        # A seed that is not done but has files was cut off: it is not
        # counted. Keep what there is in partial/ and replay it from the start.
        for seed in todo:
            tpath = trajectory_path(round_index, seed, paths.trajectories)
            files = [tpath, frames_path(round_index, seed, paths.frames),
                     os.path.splitext(tpath)[0] + ".frame_steps.csv"]
            moved = move_partial(paths.root, round_index, seed, files)
            if moved:
                ckpt.note_replay(round_index, seed, moved)
                log(f"  [{harness.version} seed{seed}] was cut off: kept in {os.path.dirname(moved[0])}, replaying")
        ckpt.check_start("episode", f"the episodes of {harness.version} (seeds {todo})")

    failed = threading.Event()
    stop = _EitherEvent(failed, ckpt.stop_event) if ckpt is not None else failed
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
                frame_root=paths.frames, log=log, probe=for_game(cfg["game"]).read_state,
            )
            if outcome.end_reason == "aborted" or outcome.error:
                raise AbortExperiment(f"seed {seed} ended with {outcome.end_reason}: {outcome.error}")
            row = outcome.as_dict()
            row["player_model"] = getattr(client, "model", None)
            row |= episode_metrics(read_records(outcome.trajectory), row, cfg)
            with lock:
                done[seed] = row
                _write_json(out_path, [done[s] for s in seeds if s in done])
                if ckpt is not None:
                    ckpt.episode_done(round_index, seed, float(outcome.wall_time_s), list(done))
            goal = row["goal"]
            log(
                f"  [{harness.version} seed{seed}] {'CLEARED' if outcome.solved else 'not cleared'} "
                f"progress={row['score']:.3f} parts={goal['parts']} cost={row['cost']['cost']:.3f} "
                f"g={row['gate_score']:.3f} actions={outcome.actions_used} turns={outcome.turns} "
                f"calls={outcome.llm_calls} end={outcome.end_reason} "
                f"tok={outcome.tokens_in + outcome.tokens_out} {outcome.wall_time_s:.0f}s"
            )
        except BaseException as error:  # noqa: BLE001 - surfaced after the pool drains
            failed.set()
            with lock:
                errors.append(error)

    log(f"  evaluating {harness.version}: seeds {todo} in parallel")
    with ThreadPoolExecutor(max_workers=int(cfg["parallel_episodes"])) as pool:
        list(pool.map(one, todo))
    if ckpt is not None and ckpt.stop_event.is_set() and len(done) < len(seeds):
        raise StopRun(ckpt.stop_reason or "stop requested")
    if errors:
        raise AbortExperiment(f"evaluation of {harness.version} stopped: {errors[0]}")
    return [done[s] for s in seeds]


def version_entry(
    harness: Harness, round_index: int, episodes: list[dict[str, Any]], paths: Paths,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    loaded = analyze_mod.load_episodes({"episodes": episodes})
    models = sorted({e.get("player_model") for e in episodes if e.get("player_model")})
    entry = {
        "version": harness.version,
        "parent": harness.parent,
        "round": round_index,
        "harness_path": os.path.join(paths.harnesses, harness.version).replace(os.sep, "/"),
        "evaluated_at": _now(),
        "episodes": [{k: e.get(k) for k in EPISODE_FIELDS} for e in episodes],
        "tokens": sum(e["tokens_in"] + e["tokens_out"] for e in episodes),
        "skill_usage": analyze_mod.skill_usage_for_entry(harness, loaded),
        # Per version, not only per run: a resumed run may switch models
        # (the model each episode actually used is in its row).
        "player_model": models[0] if len(models) == 1 else (models or cfg["player"]["model"]),
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


def _skill_name_record(attempts: list[dict[str, Any]]) -> dict[str, Any]:
    """The skill-name check over the round: edits checked, edits rejected, and
    each missing name with where it appeared."""
    checked = rejected = 0
    missing = []
    for attempt in attempts:
        names = (attempt.get("info") or {}).get("skill_names") or {}
        checked += int(names.get("edits_checked") or 0)
        rejected += int(names.get("edits_rejected") or 0)
        for item in names.get("rejected") or []:
            for m in item["missing"]:
                missing.append({"attempt": attempt["attempt"], "edit": item["id"], "source": item["source"],
                                "what": item["what"], **m})
    last = (attempts[-1].get("info") or {}).get("skill_names") or {} if attempts else {}
    return {"edits_checked": checked, "edits_rejected": rejected, "missing": missing,
            "missing_in_child": last.get("missing_in_child") or []}


def _issue16_record(attempts: list[dict[str, Any]]) -> dict[str, Any]:
    """The round's state-change and repeat checks (#16), over its attempts."""
    state = {"skills_checked": 0, "dropped": 0, "unverifiable": 0, "env_steps": 0, "results": []}
    repeat = {"edits_dropped": 0, "repeats": []}
    for attempt in attempts:
        info = attempt.get("info") or {}
        for key in ("skills_checked", "dropped", "unverifiable", "env_steps"):
            state[key] += int((info.get("state_change") or {}).get(key) or 0)
        state["results"] += [{"attempt": attempt["attempt"], **{k: v for k, v in r.items() if k != "states"},
                              "states": [{k: s.get(k) for k in ("seed", "turn", "verdict", "why", "actions",
                                                                 "cells_changed", "game_state_changed")}
                                         for s in r.get("states") or []]}
                             for r in (info.get("state_change") or {}).get("results") or []]
        repeat["edits_dropped"] += int((info.get("repeat") or {}).get("edits_dropped") or 0)
        repeat["repeats"] += [{"attempt": attempt["attempt"], **r} for r in (info.get("repeat") or {}).get("repeats") or []]
    if attempts:
        last = (attempts[-1].get("info") or {}).get("state_change") or {}
        state["every_step_regions"] = last.get("every_step_regions")
        state["every_step_fields"] = last.get("every_step_fields")
    return {"state_change": state, "repeat": repeat}


# ---------------------------------------------------------------------------
# The loop
# ---------------------------------------------------------------------------


def _feedback(dropped: list[dict[str, Any]]) -> str:
    # The reasons are the Meta-facing ones: a fact-check drop says which claim
    # is false, not what is true.
    return "Every edit was dropped at validation:\n" + "\n".join(
        f"- {d['what']}: {d['stage']}: {d['reason']}" for d in dropped
    ) + "\nPropose edits that address these failures."


def run(
    cfg: dict[str, Any], paths: Paths, rounds: int,
    player_factory: Callable[[int], Any], meta_factory: Callable[[], Any] | None,
    log: Callable[[str], None] = print,
    fact_factory: Callable[[], Any] | None = None,
    ckpt: Checkpoint | None = None,
) -> dict[str, Any]:
    os.makedirs(paths.root, exist_ok=True)
    if ckpt is None:  # no time limit, no signals: a plain local run
        ckpt = Checkpoint(paths.root, cfg, log=log)
    archive = load_archive(paths, cfg)
    use_factcheck = bool((cfg.get("factcheck") or {}).get("enabled"))
    validate_cfg = cfg.get("validate") or {}
    use_state_change = bool(validate_cfg.get("state_change"))
    use_section = bool((cfg.get("meta") or {}).get("rejected_section"))
    store = RejectedStore(os.path.join(paths.root, STORE_FILE)) if validate_cfg.get("repeat_check") else None

    def sync_store() -> None:
        if store is not None:
            added = sync_rejected(store, paths.root, archive, lambda name: load_harness(name, paths.harnesses))
            if added:
                log(f"  rejected-edit store: {added} new, {len(store.entries)} in all")

    def stage(round_index: int, name: str, parent: str | None, work: Callable[[], Any]) -> Any:
        """Run one stage as a checkpointed unit: not started if it will not
        fit, recorded when it has finished."""
        ckpt.check_start(name.split(".")[0], f"round {round_index} {name}")
        ckpt.position(round_index, name, "running", parent)
        started = time.monotonic()
        result = work()
        ckpt.stage_done(round_index, name, time.monotonic() - started)
        return result

    def recovered(round_index: int, name: str) -> None:
        # Its output is on disk but the state file missed it (killed between
        # the two writes): the stage is done, record it once.
        if not ckpt.stage_was_completed(round_index, name):
            ckpt.stage_done(round_index, name, 0.0)

    # ---- round 0: v0 baseline ------------------------------------------------
    if entry_for(archive, "v0") is None:
        if os.path.exists(os.path.join(paths.harnesses, "v0", "manifest.json")):
            v0 = load_harness("v0", paths.harnesses)
        else:
            v0 = build_v0(cfg.get("v0_drop_prompts") or ())
            v0.save(paths.harnesses)
        append_changelog(paths, changelog_section(v0, [], []), key="## v0 ")
        log("round 0: evaluating v0")
        started = time.monotonic()
        episodes = evaluate(v0, 0, cfg, paths, player_factory, log, ckpt)
        if not ckpt.stage_was_completed(0, "evaluate"):
            ckpt.stage_done(0, "evaluate", time.monotonic() - started)

        def baseline() -> None:
            entry = version_entry(v0, 0, episodes, paths, cfg)
            entry |= {"edits_accepted": [], "edits_dropped": [], "accepted": True,
                      "gate": {"decision": "baseline", "reason": "v0 is the starting parent"}}
            archive["versions"].append(entry)
            archive["rounds"].append({"round": 0, "parent_before": None, "child": "v0",
                                      "decision": "baseline", "parent_after": "v0"})
            save_archive(paths, archive)
            append_changelog(paths, f"Gate for v0: baseline — mean progress {entry['score_mean']}, "
                                    f"mean cost {entry['cost_mean']}, mean gate score {entry['gate_mean']}, "
                                    f"clear rate {entry['clear_rate']}", key="Gate for v0:")

        stage(0, "gate", None, baseline)
    else:
        recovered(0, "evaluate")
        recovered(0, "gate")

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
            def do_analyze() -> dict[str, Any]:
                built = analyze_mod.analyze(parent, parent_entry, archive["versions"], rejected_since,
                                            game=cfg["game"])
                if use_section:
                    data = rejected_since_parent(archive, paths.root, parent, parent_entry)
                    built["rejected_since_parent"] = {"data": data, "text": render_section(data)}
                _write_json(report_path, built)
                return built

            report = stage(round_index, "analyze", parent_name, do_analyze)
        else:
            recovered(round_index, "analyze")
        evidence = report.get("frame_evidence") or {}
        log(f"  1 analyze: {len(report['inline_helpers'])} inline-helper groups, "
            f"skills called {sum(s['calls'] for s in report['skill_stats'].values())} times; frame evidence: "
            f"{len(evidence.get('rare_events') or [])} rare on-screen changes")
        if report.get("rejected_since_parent"):
            data = report["rejected_since_parent"]["data"]
            log(f"    rejected since {parent_name}: {len(data['versions'])} version(s), "
                f"{len(data['dropped'])} dropped edit(s)")

        # ---- 2 · Propose + 3 · Validate (one retry if nothing survives) ------
        # attempts.json grows one step at a time: an attempt's proposals, then
        # its validation. A cut between the two re-runs only Validate.
        validation_path = os.path.join(rdir, "validation.json")
        attempts_path = os.path.join(rdir, "attempts.json")
        validation = _read_json(validation_path)
        if validation is None:
            episodes = analyze_mod.load_episodes(parent_entry)
            attempts: list[dict[str, Any]] = _read_json(attempts_path, [])
            while True:
                last = attempts[-1] if attempts else None
                if last is not None and "passed" in last:
                    if last["passed"] or len(attempts) >= 2:
                        break
                if last is None or "passed" in last:
                    number = len(attempts) + 1
                    feedback = _feedback(last["dropped"]) if last is not None else None

                    def do_propose() -> dict[str, Any]:
                        rules = rule_edits(report, parent, cfg) if number == 1 else []
                        meta = None
                        if meta_factory is not None:
                            meta = meta_edits(report, parent, cfg, meta_factory(), feedback=feedback)
                        attempts.append({"attempt": number, "rules": rules, "meta": meta})
                        _write_json(attempts_path, attempts)
                        return attempts[-1]

                    made = stage(round_index, f"propose.{number}", parent_name, do_propose)
                    meta = made["meta"]
                    log(f"  2 propose (attempt {number}): {len(made['rules'])} rule-based, "
                        f"{len(meta['edits']) if meta else 0} from the Meta LLM"
                        + (f" (parse error: {meta['parse_error']})" if meta and meta.get("parse_error") else ""))
                    continue

                def do_validate() -> dict[str, Any]:
                    current = attempts[-1]
                    meta = current["meta"]
                    raw = current["rules"] + (meta["edits"] if meta else [])
                    checker = None
                    if use_factcheck:
                        checker = FactChecker(cfg, fact_factory() if fact_factory else None, episodes)
                    sync_store()  # everything rejected up to here, this round's earlier attempt included
                    states = None
                    if use_state_change:
                        states = StateChangeChecker(cfg, episodes, for_game(cfg["game"]).read_state)
                    _child, passed, dropped, info = validate(parent, raw, episodes, cfg, version, round_index,
                                                             log, factchecker=checker, rejected=store,
                                                             state_checker=states)
                    over_cap = (meta or {}).get("over_cap") or []
                    for i, extra in enumerate(over_cap, start=1):
                        where = extra.get("name") or extra.get("index") or extra.get("indices")
                        dropped.append({"id": f"r{round_index}-x{i}", "source": "meta",
                                        "what": f"{extra.get('op')} {extra.get('target')} {where}",
                                        "stage": "propose", "reason": "over the per-round edit cap",
                                        "edit": extra})
                    current.update(passed=passed, dropped=dropped, info=info)
                    _write_json(attempts_path, attempts)
                    return current

                checked = stage(round_index, f"validate.{len(attempts)}", parent_name, do_validate)
                names = checked["info"]["skill_names"]
                extra = ""
                if "state_change" in checked["info"]:
                    sc = checked["info"]["state_change"]
                    extra += (f"; state-change check: {sc['skills_checked']} skills checked, {sc['dropped']} "
                              f"dropped, {sc['unverifiable']} unverifiable, {sc['env_steps']} env steps")
                if "repeat" in checked["info"]:
                    extra += f"; repeat check: {checked['info']['repeat']['edits_dropped']} dropped"
                log(f"  3 validate: {len(checked['passed'])} passed, {len(checked['dropped'])} dropped "
                    f"(skill-name check: {names['edits_checked']} edits checked, "
                    f"{names['edits_rejected']} rejected{extra})")
            validation = {"attempts": attempts, "final_attempt": len(attempts)}
            _write_json(os.path.join(rdir, "proposals.json"),
                        [{"attempt": a["attempt"], "rules": a["rules"], "meta": a["meta"]} for a in attempts])
            _write_json(validation_path, validation)
        final = validation["attempts"][-1]
        passed, dropped = final["passed"], final["dropped"]
        all_dropped = [d for a in validation["attempts"] for d in a["dropped"]]
        facts = _factcheck_record(validation["attempts"])
        names = _skill_name_record(validation["attempts"])
        checks16 = _issue16_record(validation["attempts"]) if (use_state_change or store is not None) else {}
        sync_store()

        if not passed:
            log(f"  no edit survived validation; round {round_index} ends without a child")

            def no_child() -> None:
                archive["rounds"].append({"round": round_index, "parent_before": parent_name, "child": None,
                                          "decision": "no valid edits", "parent_after": parent_name,
                                          "edits_dropped": _slim(all_dropped), "factcheck": facts,
                                          "skill_names": names, **checks16})
                save_archive(paths, archive)
                append_changelog(paths, f"## round {round_index}: no child (parent {parent_name})\n"
                                 f"Every proposed edit was dropped at Validate ({len(all_dropped)}).\n"
                                 + "\n".join(f"- `{d['id']}` [{d['source']}] {d['what']} — {d['stage']}: "
                                             f"{d['reason']}" for d in all_dropped),
                                 key=f"## round {round_index}: no child")

            stage(round_index, "gate", parent_name, no_child)
            sync_store()
            continue

        # ---- 4 · Write vN+1 ----------------------------------------------------
        if os.path.exists(os.path.join(paths.harnesses, version, "manifest.json")):
            child = load_harness(version, paths.harnesses)
            append_changelog(paths, changelog_section(child, passed, all_dropped), key=f"## {version} ")
            recovered(round_index, "write")
        else:
            def do_write() -> Harness:
                built, *_ = _rebuild_child(parent, final, cfg, version, round_index)
                built.save(paths.harnesses)
                append_changelog(paths, changelog_section(built, passed, all_dropped), key=f"## {version} ")
                return built

            child = stage(round_index, "write", parent_name, do_write)
        log(f"  4 write: {version} with {len(passed)} edits")

        # ---- evaluate + 5 · Gate ------------------------------------------------
        started = time.monotonic()
        episodes = evaluate(child, round_index, cfg, paths, player_factory, log, ckpt)
        if not ckpt.stage_was_completed(round_index, "evaluate"):
            ckpt.stage_done(round_index, "evaluate", time.monotonic() - started)

        def do_gate() -> tuple[dict[str, Any], str]:
            entry = version_entry(child, round_index, episodes, paths, cfg)
            decision = gate(entry, parent_entry, cfg)
            decision["compared_to"] = parent_name
            entry |= {"edits_accepted": _slim(passed), "edits_dropped": _slim(all_dropped),
                      "gate": decision, "accepted": decision["decision"] == "accepted",
                      "factcheck": facts, "skill_names": names, **checks16,
                      "meta_analysis": [((a.get("meta") or {}).get("analysis")) for a in validation["attempts"]],
                      "meta_tokens": sum(int((a.get("meta") or {}).get("tokens_in") or 0)
                                         + int((a.get("meta") or {}).get("tokens_out") or 0)
                                         for a in validation["attempts"]) + facts["extraction_tokens"]}
            archive["versions"].append(entry)
            after = version if entry["accepted"] else parent_name
            archive["rounds"].append({"round": round_index, "parent_before": parent_name, "child": version,
                                      "decision": decision["decision"], "parent_after": after})
            save_archive(paths, archive)
            append_changelog(paths, f"Gate for {version} vs {parent_name}: **{decision['decision']}** "
                                    f"({decision['rule']}) — {decision['reason']} (progress {entry['score_mean']} vs "
                                    f"{parent_entry['score_mean']}, cost {entry['cost_mean']} vs "
                                    f"{parent_entry['cost_mean']}, gate score {entry['gate_mean']} vs "
                                    f"{parent_entry['gate_mean']}, worst gate score {entry['gate_worst']} vs "
                                    f"{parent_entry['gate_worst']})", key=f"Gate for {version} vs")
            return decision, after

        decision, parent_after = stage(round_index, "gate", parent_name, do_gate)
        log(f"  5 gate: {decision['decision']} ({decision['reason']}); parent is now {parent_after}")
        sync_store()  # a rejected version's edits

    sync_store()
    last_round = archive["rounds"][-1]
    ckpt.position(last_round["round"], "gate", "done", last_round["parent_after"], seeds_done=[])
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
    keep = ("id", "source", "what", "rationale", "stage", "reason", "checks", "repeat_of", "similarity")
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
