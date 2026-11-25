"""Driver for the evo-harness runs on ls20, Level 1 (issues #9, #12, #14).

    python evolve_run.py --stage preflight             # credentials + inference
    python evolve_run.py --stage pilot                 # one real v0 episode, for cost
    python evolve_run.py --run-dir runs/v3 --resume    # the run, in as many jobs as it takes
    python evolve_run.py --stage status --run-dir runs/v3   # where a run is; consistency check
    python evolve_run.py --stage smoke --run-dir DIR   # cluster preflight: game, model, checkpoint
    python evolve_run.py --stage figures               # figures from archive.json
    python evolve_run.py --stage rescore9              # #9's episodes on #12's score
    python evolve_run.py --stub --rounds 2 --run-dir DIR   # offline self-test, no model

The run directory is `--run-dir` (or `root` in the config). Credentials:
QWEN_API_KEY and QWEN_BASE_URL, from the environment or .env.

Checkpoint and resume (#14, evolve/checkpoint.py): the run saves
run_state.json after every episode and stage. `--resume` continues a run from
its state; without it, a run directory that already holds a run is refused.
A finished run resumes to nothing, unless `--rounds` asks for more rounds than
it has recorded: then it goes on from its last parent (the config, and so the
config hash, stay as they were). `--time-limit-min` (default: the config's
`checkpoint.job_time_limit_min` under SLURM, none otherwise) is the job's
limit; the run stops by `checkpoint.stop_by_min` and on SIGUSR1.
Exit codes: 0 = finished or cleanly paused, 2 = stopped on an error,
3 = the run directory is locked or `--resume` is missing.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from urllib.parse import urlsplit

import yaml

from harness.model import AbortExperiment, load_api_key
from evolve import loop
from evolve.checkpoint import STATE_FILE, Checkpoint, LockError, RunLock, StopRun, config_hash, read_json


def redact(text: str) -> str:
    """Strip the endpoint URL and key from anything printed (the issue treats
    both as credentials; harness.model's errors include the URL)."""
    for name, placeholder in (("QWEN_BASE_URL", "<QWEN_BASE_URL>"), ("QWEN_API_KEY", "<QWEN_API_KEY>")):
        try:
            secret = load_api_key(name)
        except AbortExperiment:
            continue
        if secret:
            text = str(text).replace(secret.rstrip("/"), placeholder)
            # Connection errors name the host and path, not the configured URL.
            host = urlsplit(secret).hostname
            if host:
                text = text.replace(host, placeholder)
    # A gateway error can quote the address of the backend behind it (seen
    # 2026-11-15: 'Post "http://12...'). No URL in an error is worth printing.
    return _URL_RE.sub("<url>", str(text))


_URL_RE = re.compile(r"https?://[^\s\"'\\<>]+")


# Progress lines also go to this file, opened and closed on every write. On
# 2026-11-02 the detached #12 run's redirected stdout stopped receiving them
# at 16:37 while the run itself went on (py-spy showed no thread blocked), so
# monitoring must not depend on stdout alone.
EVENT_LOG: str | None = None


def log(message: str) -> None:
    text = redact(message)
    print(text, flush=True)
    if EVENT_LOG:
        with open(EVENT_LOG, "a", encoding="utf-8") as handle:
            handle.write(text + "\n")


def load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def stage_preflight(cfg: dict) -> list[str]:
    """Check both roles' models answer. If a role's model fails and the config
    names a `fallback_model`, the role switches to it for this process (the
    user's instruction for #14: use the normal model if the flash one is
    down). Returns notes on any switch; `cfg` is updated in place."""
    notes = []
    for section in ("player", "meta"):
        client = loop.make_client(cfg, section)
        # Print the model id only; the endpoint URL is a credential here.
        try:
            info = client.preflight()
        except AbortExperiment as error:
            fallback = cfg[section].get("fallback_model")
            if not fallback or fallback == cfg[section]["model"]:
                raise AbortExperiment(redact(str(error))) from None
            failed = cfg[section]["model"]
            cfg[section]["model"] = fallback
            client = loop.make_client(cfg, section)
            try:
                info = client.preflight()
            except AbortExperiment as second:
                raise AbortExperiment(
                    redact(f"{failed} failed ({error}); fallback {fallback} failed too ({second})")) from None
            notes.append(f"{section}: {failed} did not answer ({redact(str(error))[:160]}); "
                         f"using the fallback model {fallback}")
            print(f"*** {notes[-1]}")
        print(f"{section}: {client.model} OK (probe reply {info.get('probe')!r})")
    return notes


def stage_pilot(cfg: dict, root: str) -> None:
    """One real v0 episode on the first seed, written outside the experiment's
    tree, scored like a run episode. Also checks that the logged game states
    equal the states rebuilt by replay (what rescoring #9 relies on)."""
    from evolve.action_loop import read_records, run_episode
    from evolve.goal_score import read_state, states_by_replay, states_from_records
    from evolve.replay import make_env
    from evolve.score import episode_metrics
    from evolve.seed_v0 import build_v0

    paths = loop.Paths(root)
    seed = int(cfg["seeds"][0])
    client = loop.make_client(cfg, "player", seed=seed)
    outcome = run_episode(
        env=make_env(cfg["game"], seed=seed), client=client, harness=build_v0(), round_index=0,
        episode=seed, seed=seed, cfg=cfg, traj_root=paths.trajectories, frame_root=paths.frames,
        probe=read_state,
    )
    row = outcome.as_dict()
    records = read_records(outcome.trajectory)
    row |= episode_metrics(records, row, cfg)
    logged, _ = states_from_records(records)
    replayed, _ = states_by_replay(records, cfg["game"])
    row["logged_states_equal_replay"] = logged == replayed
    print(json.dumps(row, indent=1, default=str))


def apply_game(cfg: dict, name: str) -> None:
    """--game (#15): the game the config runs, and that game's score weights
    (`score.by_game`). Applied before the config hash, so each game's run has
    its own identity."""
    from scorer import game_id, short_name

    cfg["game"] = game_id(name)
    short = short_name(cfg["game"])
    by_game = (cfg.get("score") or {}).get("by_game") or {}
    if short in by_game:
        cfg["score"] = {"weights": dict(by_game[short]["weights"])}
    cfg["experiment"] = str(cfg.get("experiment", "")).replace("{game}", short)


def stage_baseline(cfg: dict, root: str, harness_dir: str, stub: bool = False) -> int:
    """A fixed harness played once on the config's seeds, in parallel, no
    evolution (#15 baseline B: #14's best ls20 harness on a new game). Writes
    the episodes and <root>/summary.json; a rerun keeps finished seeds."""
    from evolve.checkpoint import write_json_atomic
    from evolve.harness import load_harness

    global EVENT_LOG
    harness = load_harness(os.path.basename(os.path.normpath(harness_dir)), os.path.dirname(os.path.normpath(harness_dir)))
    os.makedirs(root, exist_ok=True)
    lock = RunLock(root)
    try:
        note = lock.acquire()
    except LockError as error:
        print(f"*** {error}", file=sys.stderr)
        return 3
    EVENT_LOG = os.path.join(root, "events.log")
    try:
        if note:
            log(f"*** {note}")
        notes: list[str] = []
        if stub:
            from evolve.stub import StubPlayer

            factory = lambda seed: StubPlayer(seed=seed)  # noqa: E731
            print("*** STUB MODE: stub player, no model calls. Not a result. ***")
        else:
            try:
                notes = stage_preflight(cfg)
            except AbortExperiment as error:
                print(f"*** PREFLIGHT FAILED: {error}", file=sys.stderr)
                return 2
            factory = lambda seed: loop.make_client(cfg, "player", seed=seed)  # noqa: E731
        paths = loop.Paths(root, title="baseline B")
        harness.save(paths.harnesses)  # the exact harness played, next to its results
        log(f"--- baseline: {harness.version} from {harness_dir} on {cfg['game']}, seeds {cfg['seeds']}, "
            f"player {cfg['player']['model']}, job {os.environ.get('SLURM_JOB_ID')}")
        try:
            episodes = loop.evaluate(harness, 0, cfg, paths, factory, log)
        except AbortExperiment as error:
            print(f"\n*** BASELINE STOPPED: {redact(str(error))}", file=sys.stderr)
            return 2
        entry = loop.version_entry(harness, 0, episodes, paths, cfg)
        entry |= {"baseline": "B", "harness_source": harness_dir.replace(os.sep, "/"), "game": cfg["game"],
                  "notes": notes, "config_hash": config_hash(cfg)}
        write_json_atomic(os.path.join(root, "summary.json"), entry)
        log(f"--- baseline done: progress {entry['score_mean']} (worst {entry['score_worst']}), cost "
            f"{entry['cost_mean']}, gate {entry['gate_mean']}, clears {entry['n_clears']}/{entry['n_episodes']}")
        return 0
    finally:
        lock.release()


def run_status(root: str, cfg: dict) -> dict:
    """Where a run is, read from its files, and whether run_state.json agrees
    with them. Reads only."""
    state = read_json(os.path.join(root, STATE_FILE))
    archive = read_json(os.path.join(root, "archive.json")) or {"versions": [], "rounds": []}
    problems = []
    versions = [v["version"] for v in archive["versions"]]
    rounds = [r["round"] for r in archive["rounds"]]
    if len(versions) != len(set(versions)):
        problems.append(f"archive.json lists a version twice: {versions}")
    if len(rounds) != len(set(rounds)):
        problems.append(f"archive.json lists a round twice: {rounds}")
    seeds = [int(s) for s in cfg["seeds"]]
    for entry in archive["versions"]:
        got = [e["seed"] for e in entry["episodes"]]
        if sorted(got) != sorted(seeds):
            problems.append(f"{entry['version']} has seeds {got}, expected {seeds}")
    next_round = (max(rounds) + 1) if rounds else 0
    episodes = read_json(os.path.join(root, "reports", f"round_{next_round}", "episodes.json"), [])
    done = sorted(e["seed"] for e in episodes)
    if len(done) != len(set(done)):
        problems.append(f"round {next_round} episodes.json lists a seed twice: {done}")
    if state is None:
        problems.append("no run_state.json")
    else:
        if state["status"] != "finished" and state.get("stage") == "evaluate" and state["round"] == next_round \
                and sorted(state.get("seeds_done") or []) != done:
            problems.append(f"run_state.json says seeds {state.get('seeds_done')} are done in round "
                            f"{next_round}; episodes.json has {done}")
        if state["status"] != "finished" and state["round"] not in (next_round, next_round - 1):
            problems.append(f"run_state.json is at round {state['round']}; the archive's next round is {next_round}")
        if state["config_hash"] != config_hash(cfg):
            problems.append(f"config hash differs: state {state['config_hash']}, this config {config_hash(cfg)}")
        counted = {}
        for unit in state["completed"]:
            key = (unit["round"], unit.get("stage") or f"seed {unit.get('seed')}")
            counted[key] = counted.get(key, 0) + 1
        twice = [f"round {r} {what}" for (r, what), n in counted.items() if n > 1]
        if twice:
            problems.append(f"units recorded more than once: {twice}")
    return {
        "run_dir": root,
        "state": {k: state.get(k) for k in ("status", "round", "stage", "stage_status", "seeds_done",
                                             "parent_version", "git_commit", "config_hash", "slurm_job_ids",
                                             "time_used_s", "longest_s", "updated")} if state else None,
        "segments": (state or {}).get("segments"),
        "replayed_after_cutoff": (state or {}).get("replayed_after_cutoff"),
        "archive": [{"version": v["version"], "parent": v["parent"], "progress": v["score_mean"],
                     "rotation": (v.get("parts_mean") or {}).get("rotation"), "cost": v["cost_mean"],
                     "gate": v["gate_mean"], "clears": v["n_clears"],
                     "decision": v["gate"]["decision"]} for v in archive["versions"]],
        "rounds_done": rounds,
        "next_round": next_round,
        "next_round_seeds_done": done,
        "lock_present": os.path.exists(os.path.join(root, "run.lock")),
        "consistent": not problems,
        "problems": problems,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="evo-harness run (#9, #12, #14)")
    parser.add_argument("--stage", choices=["preflight", "pilot", "figures", "rescore9", "status", "smoke",
                                            "baseline"])
    parser.add_argument("--rounds", type=int, default=None)
    parser.add_argument("--config", default="config_evolve.yaml")
    parser.add_argument("--game", default=None,
                        help="the game to run, e.g. ft09 (default: `game` in the config) (#15)")
    parser.add_argument("--harness", default=None,
                        help="--stage baseline: the harness version directory to play (#15)")
    parser.add_argument("--elapsed-min", type=float, default=0.0,
                        help="minutes of this job used before this process started (#15); "
                             "taken off the time limit and the stop time")
    parser.add_argument("--run-dir", "--root", dest="root", default=None,
                        help="run directory (default: `root` in the config)")
    parser.add_argument("--resume", action="store_true",
                        help="continue the run in --run-dir from its run_state.json (starts it if new)")
    parser.add_argument("--time-limit-min", type=float, default=None,
                        help="this job's time limit in minutes (default: the config's under SLURM, else none)")
    parser.add_argument("--break-lock", action="store_true",
                        help="take over a lock file left by a job that is gone")
    parser.add_argument("--stub", action="store_true",
                        help="offline self-test: stub player and stub Meta LLM, no model calls")
    args = parser.parse_args()
    cfg = load_config(args.config)
    if args.game:
        apply_game(cfg, args.game)
    if not cfg.get("game"):
        parser.error("the config names no game; pass --game")
    root_default = cfg.get("root") or os.path.join("results", "evolve")
    if args.stub:
        cfg["budget"]["max_actions"] = 40
        cfg["budget"]["max_turns"] = 30
        # StubMeta returns 6 edits; let all of them reach Validate so every
        # drop path, the fact-check included, runs end to end.
        cfg["meta"]["max_edits"] = 8

    if args.stage == "preflight":
        try:
            stage_preflight(cfg)
        except AbortExperiment as error:
            print(f"*** PREFLIGHT FAILED: {error}", file=sys.stderr)
            raise SystemExit(2)
        return
    if args.stage == "pilot":
        try:
            stage_pilot(cfg, args.root or os.path.join("data", "evolve12_pilot"))
        except AbortExperiment as error:
            print(f"*** PILOT STOPPED: {redact(str(error))}", file=sys.stderr)
            raise SystemExit(2)
        return
    if args.stage == "figures":
        from analysis.evolution12 import build_all

        for path in build_all(args.root or root_default):
            print("wrote", path)
        return
    if args.stage == "rescore9":
        from analysis.rescore_9 import main as rescore

        rescore(cfg, os.path.join("results", "evolve"), args.root or root_default)
        return
    if args.stage == "status":
        status = run_status(args.root or root_default, cfg)
        print(json.dumps(status, indent=1, default=str))
        raise SystemExit(0 if status["consistent"] else 1)
    if args.stage == "smoke":
        from evolve.smoke import main as smoke

        raise SystemExit(smoke(cfg, args.root or os.path.join("runs", "smoke"), log, redact))
    if args.stage == "baseline":
        if not args.harness or not args.root:
            parser.error("--stage baseline needs --harness and --run-dir")
        raise SystemExit(stage_baseline(cfg, args.root, args.harness, stub=args.stub))

    rounds = args.rounds if args.rounds is not None else int(cfg["rounds"])
    if args.stub:
        from evolve.stub import StubExtractor, StubMeta, StubPlayer

        root = args.root or os.path.join("data", "evolve12_stub")
        print("*** STUB MODE: stub player, Meta LLM and claim extractor, no model calls. Not a result. ***")
    else:
        root = args.root or root_default

    # ---- the run directory: resume rules, one writer ---------------------------
    state = read_json(os.path.join(root, STATE_FILE))
    holds_run = state is not None or os.path.exists(os.path.join(root, "archive.json"))
    if holds_run and not args.resume:
        print(f"*** {root} already holds a run. Pass --resume to continue it, or choose another --run-dir.",
              file=sys.stderr)
        raise SystemExit(3)
    extended_from = None
    if state is not None and state.get("status") == "finished":
        # A finished run goes on only when more rounds are asked for on the
        # command line than it has recorded (`--rounds`; the config, and so
        # the run's identity, stays as it was).
        archive = read_json(os.path.join(root, "archive.json")) or {"rounds": []}
        last_round = max((r["round"] for r in archive["rounds"]), default=0)
        if args.rounds is None or rounds <= last_round or archive.get("stopped_early"):
            print(f"{root}: the run is finished (round {state['round']}, parent {state['parent_version']}). "
                  "Nothing to do.")
            return
        extended_from = last_round
    if state is not None and state["config_hash"] != config_hash(cfg):
        print(f"*** {root} was started with a different config (hash {state['config_hash']}, now "
              f"{config_hash(cfg)}). Refusing to resume: results would mix settings.", file=sys.stderr)
        raise SystemExit(3)
    digest = config_hash(cfg)  # before preflight: a model fallback must not change the run's identity
    # The run keeps the models its first part used, so versions are compared
    # on one model. If that model is down when a later part starts, the part
    # falls back to the other configured one and the switch is recorded.
    for section, pinned in ((state or {}).get("models") or {}).items():
        if pinned and pinned != cfg[section]["model"]:
            cfg[section]["fallback_model"], cfg[section]["model"] = cfg[section]["model"], pinned

    lock = RunLock(root)
    try:
        note = lock.acquire(force=args.break_lock)
    except LockError as error:
        print(f"*** {error}", file=sys.stderr)
        raise SystemExit(3)

    global EVENT_LOG
    EVENT_LOG = os.path.join(root, "events.log")
    exit_code = 0
    ckpt = None
    try:
        if note:
            log(f"*** {note}")
        notes: list[str] = []
        if args.stub:
            player_factory = lambda k: StubPlayer(seed=k)  # noqa: E731
            meta_factory = StubMeta
            fact_factory = StubExtractor
        else:
            print("preflight ...")
            try:
                notes = stage_preflight(cfg)
            except AbortExperiment as error:
                print(f"*** PREFLIGHT FAILED: {error}", file=sys.stderr)
                raise SystemExit(2)
            player_factory = lambda seed: loop.make_client(cfg, "player", seed=seed)  # noqa: E731
            meta_factory = (lambda: loop.make_client(cfg, "meta")) if cfg["meta"]["enabled"] else None
            fact_factory = lambda: loop.make_client(cfg, "meta")  # noqa: E731

        guard = cfg.get("checkpoint") or {}
        limit_min = args.time_limit_min
        if limit_min is None and os.environ.get("SLURM_JOB_ID"):
            limit_min = guard.get("job_time_limit_min")
        stop_by_min = None
        if limit_min is not None:
            stop_by_min = min(float(guard.get("stop_by_min", limit_min)), float(limit_min))
            # Another step of the same job ran first (#15: baseline B before
            # part 1): both limits move back by the time it used.
            limit_min = float(limit_min) - args.elapsed_min
            stop_by_min -= args.elapsed_min
        ckpt = Checkpoint(
            root, cfg,
            time_limit_s=None if limit_min is None else float(limit_min) * 60,
            stop_by_s=None if stop_by_min is None else stop_by_min * 60,
            factor=float(guard.get("factor", 1.5)),
            log=log,
        )
        ckpt.state["config_hash"] = digest
        ckpt.state["status"] = "running"
        if not args.stub:
            used = {section: cfg[section]["model"] for section in ("player", "meta")}
            ckpt.state.setdefault("models", used)
            ckpt.segment["models"] = used
        if extended_from is not None:
            notes.append(f"run extended: it had finished at round {extended_from} "
                         f"(config rounds={cfg['rounds']}); --rounds {rounds} asked for more")
            log(f"*** {notes[-1]}")
        for text in notes:
            ckpt.state.setdefault("notes", []).append({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "note": text})
        ckpt.on_forced_exit = lock.release
        ckpt.arm(usr1_grace_s=float(guard.get("signal_grace_s", 10)),
                 guard_grace_s=float(guard.get("stop_grace_s", 120)))
        ckpt.save()

        log(f"--- run {'resumed' if ckpt.resumed else 'started'}, rounds={rounds}, run dir={root}, "
            f"commit={ckpt.state['git_commit']}, config={digest}, job={os.environ.get('SLURM_JOB_ID')}, "
            f"time limit={limit_min} min, stop by={stop_by_min} min, used so far "
            f"{ckpt.state['time_used_s'] / 3600:.2f} h")
        started = time.monotonic()
        title = cfg.get("experiment", "").split(":")[0] or "issue #12"
        try:
            archive = loop.run(cfg, loop.Paths(root, title=title), rounds, player_factory, meta_factory,
                               log=log, fact_factory=fact_factory, ckpt=ckpt)
        except StopRun as stop:
            ckpt.finish("paused", stop.reason)
            log(f"*** RUN PAUSED: {stop.reason}. State saved at round {ckpt.state['round']}, stage "
                f"{ckpt.state['stage']}, seeds done {ckpt.state['seeds_done']}. Resume with --resume.")
            return
        except AbortExperiment as error:
            ckpt.finish("failed", redact(str(error))[:500])
            print(f"\n*** RUN STOPPED: {redact(str(error))}", file=sys.stderr)
            exit_code = 2
            return
        except BaseException as error:
            ckpt.finish("failed", f"{type(error).__name__}: {redact(str(error))[:500]}")
            raise
        ckpt.finish("finished", archive.get("stopped_early") or "all rounds done")
        log(f"--- run finished in this job after {(time.monotonic() - started) / 60:.1f} min; total "
            f"{ckpt.state['time_used_s'] / 3600:.2f} h over {len(ckpt.state['segments'])} part(s)")
        for entry in archive["versions"]:
            print(f"  {entry['version']:>3} parent={entry['parent'] or '-':>3} progress={entry['score_mean']} "
                  f"cost={entry['cost_mean']} gate={entry['gate_mean']} clears={entry['n_clears']}/"
                  f"{entry['n_episodes']} decision={entry['gate']['decision']}")
    finally:
        if ckpt is not None:
            ckpt.disarm()
        lock.release()
        if exit_code:
            raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
