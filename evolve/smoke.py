"""Cluster preflight for the smoke job (issue #14): `evolve_run.py --stage smoke`.

Run inside an sbatch job on a compute node, before the real run. It checks
what the real run depends on there:

1. the game loads and steps (from environment_files/, no ARC API needed);
2. the model endpoint answers from this node (both roles, with the fallback
   model if the configured one is down);
3. one short real episode runs, a checkpoint is written, the run stops, and a
   second run with the same state file picks it up: the finished seed is not
   replayed, the cut-off one is, and each seed ends up in the archive once.

The GPU check of the issue applies "if the model runs on the node". It does
not: the model is called over an API, so the job requests no GPU and the check
is reported as not applicable.

Exit code 0 if every check passed, 1 otherwise. A report is written to
<run dir>/smoke_report.json.
"""

from __future__ import annotations

import copy
import os
import platform
import shutil
import socket
import sys
import time
from typing import Any, Callable

from harness.model import AbortExperiment
from evolve.checkpoint import STATE_FILE, Checkpoint, RunLock, StopRun, read_json, write_json_atomic


class _StopAfterFirstEpisode(Checkpoint):
    def episode_done(self, *args: Any, **kwargs: Any) -> None:
        super().episode_done(*args, **kwargs)
        self.request_stop("smoke test: stop after the first finished episode", grace_s=900)


def main(cfg: dict[str, Any], root: str, log: Callable[[str], None], redact: Callable[[str], str]) -> int:
    from evolve import loop
    from evolve.replay import make_env

    checks: list[dict[str, Any]] = []

    def check(name: str, ok: bool | None, detail: str) -> None:
        mark = "n/a " if ok is None else "PASS" if ok else "FAIL"
        checks.append({"check": name, "result": mark.strip(), "detail": detail})
        log(f"  [{mark}] {name}: {detail}")

    log(f"smoke test on {socket.gethostname()} (SLURM job {os.environ.get('SLURM_JOB_ID')}), "
        f"python {platform.python_version()}, run dir {root}")
    check("gpu visible", None, "the model is called over an API; the job requests no GPU")

    # 1. the game
    try:
        from arcengine.enums import GameAction

        env = make_env(cfg["game"], seed=1)
        frame = env.reset()
        first = [list(map(int, row)) for row in frame.frame[-1]]
        moved = False
        for action in list(frame.available_actions or [])[:4]:
            frame = env.step(GameAction.from_id(int(action)))
            moved = moved or [list(map(int, row)) for row in frame.frame[-1]] != first
        check("game loads and steps", moved,
              f"{cfg['game']} from environment_files (OPERATION_MODE={os.environ.get('OPERATION_MODE', 'normal')}); "
              f"a frame changed after an action: {moved}")
    except Exception as error:  # noqa: BLE001 - a failed check, reported
        check("game loads and steps", False, f"{type(error).__name__}: {error}")
    check("ARC-AGI-3 API reachable", None,
          "not used: the game runs from the local environment files, as in #9 and #12 (no ARC_API_KEY was given)")

    # 2. the model endpoint
    cfg = copy.deepcopy(cfg)
    try:
        from evolve_run import stage_preflight

        notes = stage_preflight(cfg)
        check("model endpoint reachable", True,
              f"player {cfg['player']['model']}, meta {cfg['meta']['model']}"
              + (f"; {'; '.join(notes)}" if notes else ""))
    except AbortExperiment as error:
        check("model endpoint reachable", False, redact(str(error))[:300])
        return _finish(root, checks, log)

    # 3. a short episode, a checkpoint, a resume
    small = copy.deepcopy(cfg)
    small["seeds"] = [1, 2]
    small["parallel_episodes"] = 1
    small["budget"] |= {"max_turns": 3, "max_actions": 12}
    small["meta"]["enabled"] = False
    if os.path.exists(root):
        shutil.rmtree(root)
    paths = loop.Paths(root, title="smoke test")
    factory = lambda seed: loop.make_client(small, "player", seed=seed)  # noqa: E731
    lock = RunLock(root)
    try:
        lock.acquire()
        first_part = _StopAfterFirstEpisode(root, small, log=log)
        started = time.monotonic()
        try:
            loop.run(small, paths, 0, factory, None, log=log, ckpt=first_part)
            check("run stops on request", False, "the run did not stop after the first episode")
        except StopRun as stop:
            first_part.finish("paused", stop.reason)
            check("run stops on request", True, f"{stop.reason}; {time.monotonic() - started:.0f}s")
        finally:
            first_part.disarm()
            lock.release()
        state = read_json(os.path.join(root, STATE_FILE)) or {}
        check("checkpoint written", state.get("status") == "paused" and state.get("seeds_done") == [1],
              f"run_state.json: status {state.get('status')}, round {state.get('round')}, stage "
              f"{state.get('stage')}, seeds done {state.get('seeds_done')}")

        lock.acquire()
        second_part = Checkpoint(root, small, log=log)
        try:
            archive = loop.run(small, paths, 0, factory, None, log=log, ckpt=second_part)
            second_part.finish("finished", "all rounds done")
        finally:
            second_part.disarm()
            lock.release()
        state = read_json(os.path.join(root, STATE_FILE)) or {}
        seeds = [e["seed"] for e in archive["versions"][0]["episodes"]]
        played = [(c["round"], c["seed"]) for c in state["completed"] if c["unit"] == "episode"]
        replayed = [r["seed"] for r in state["replayed_after_cutoff"]]
        ok = (seeds == [1, 2] and sorted(played) == [(0, 1), (0, 2)] and replayed == [2]
              and state["status"] == "finished" and len(state["segments"]) == 2
              and not os.path.exists(lock.path))
        check("--resume picks the checkpoint up", ok,
              f"archive seeds {seeds}; episodes played {played}; replayed after the cut {replayed}; "
              f"status {state['status']}; parts {len(state['segments'])}; lock gone "
              f"{not os.path.exists(lock.path)}")
        episode = archive["versions"][0]["episodes"][0]
        check("one short episode ran", episode["turns"] >= 1 and episode["tokens_in"] > 0,
              f"seed 1: {episode['turns']} turns, {episode['actions_used']} actions, "
              f"{episode['tokens_in'] + episode['tokens_out']} tokens, {episode['wall_time_s']}s, "
              f"model {episode.get('player_model')}")
    except Exception as error:  # noqa: BLE001 - a failed check, reported
        lock.release()
        check("short episode + checkpoint + resume", False, redact(f"{type(error).__name__}: {error}")[:300])
    return _finish(root, checks, log)


def _finish(root: str, checks: list[dict[str, Any]], log: Callable[[str], None]) -> int:
    failed = [c for c in checks if c["result"] == "FAIL"]
    os.makedirs(root, exist_ok=True)
    write_json_atomic(os.path.join(root, "smoke_report.json"), {
        "host": socket.gethostname(), "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "python": sys.version.split()[0], "checks": checks, "passed": not failed,
    })
    log(f"smoke test: {'PASSED' if not failed else 'FAILED: ' + ', '.join(c['check'] for c in failed)}")
    return 1 if failed else 0
