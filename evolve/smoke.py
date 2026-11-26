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
            # A click needs a place to land (#15: ft09 and vc33 have only
            # ACTION6): try a coarse grid of spots until one changes the frame.
            spots = [{"x": x, "y": y} for y in range(4, 64, 8) for x in range(4, 64, 8)] if int(action) == 6 else [None]
            for data in spots:
                frame = env.step(GameAction.from_id(int(action)), data=data)
                moved = moved or [list(map(int, row)) for row in frame.frame[-1]] != first
                if moved:
                    break
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
    # #16: all of the config's seeds start at once, as in the run, and the
    # action record and the two new Validate checks are checked too.
    from evolve.action_loop import action_record_cfg

    issue16 = action_record_cfg(cfg) is not None
    small = copy.deepcopy(cfg)
    small["seeds"] = [int(s) for s in cfg["seeds"]] if issue16 else [1, 2]
    small["parallel_episodes"] = len(small["seeds"]) if issue16 else 1
    small["budget"] |= {"max_turns": 3, "max_actions": 12}
    small["meta"]["enabled"] = False
    if os.path.exists(root):
        shutil.rmtree(root)
    paths = loop.Paths(root, title="smoke test")
    seen: dict[int, list[str]] = {}
    first_seed = small["seeds"][0]
    delayed: set[int] = set()

    def factory(seed: int) -> Any:
        # #16: all seeds start together, but the others' first model call
        # waits STAGGER_S, so they are still playing when the first seed
        # finishes and the stop is requested: the cut-off path is exercised
        # (3-turn episodes started together all finish before a stop lands).
        delay = STAGGER_S if issue16 and seed != first_seed and seed not in delayed else 0.0
        delayed.add(seed)
        return _Capture(loop.make_client(small, "player", seed=seed), seen.setdefault(seed, []), delay)

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
        done_first = sorted(state.get("seeds_done") or [])
        started_seeds = [s for s in small["seeds"]
                         if os.path.exists(os.path.join(paths.trajectories, "round_0", f"seed_{s}.jsonl"))]
        expect_first = bool(done_first) and set(done_first) < set(small["seeds"]) if issue16 else done_first == [1]
        check("checkpoint written", state.get("status") == "paused" and expect_first,
              f"run_state.json: status {state.get('status')}, round {state.get('round')}, stage "
              f"{state.get('stage')}, seeds done {state.get('seeds_done')}")
        if issue16:
            check(f"{len(small['seeds'])} seeds start at once", started_seeds == small["seeds"],
                  f"trajectories started for seeds {started_seeds} in the first part (parallel "
                  f"{small['parallel_episodes']}); finished before the stop: {done_first}")

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
        cut = sorted(set(small["seeds"]) - set(done_first))
        ok = (seeds == small["seeds"] and sorted(played) == [(0, s) for s in small["seeds"]]
              and sorted(replayed) == cut and state["status"] == "finished" and len(state["segments"]) == 2
              and not os.path.exists(lock.path))
        check("--resume picks the checkpoint up", ok,
              f"archive seeds {seeds}; episodes played {played}; replayed after the cut {sorted(replayed)} "
              f"(expected {cut}); status {state['status']}; parts {len(state['segments'])}; lock gone "
              f"{not os.path.exists(lock.path)}")
        episode = archive["versions"][0]["episodes"][0]
        check("one short episode ran", episode["turns"] >= 1 and episode["tokens_in"] > 0,
              f"seed {episode['seed']}: {episode['turns']} turns, {episode['actions_used']} actions, "
              f"{episode['tokens_in'] + episode['tokens_out']} tokens, {episode['wall_time_s']}s, "
              f"model {episode.get('player_model')}")
        if issue16:
            _issue16_checks(small, root, archive, seen, check)
    except Exception as error:  # noqa: BLE001 - a failed check, reported
        lock.release()
        check("short episode + checkpoint + resume", False, redact(f"{type(error).__name__}: {error}")[:300])
    return _finish(root, checks, log)


STAGGER_S = 30.0


class _Capture:
    """Passes calls through to the player client and keeps each turn message.
    `delay_s` holds back the first call (the first part of the smoke run only)."""

    def __init__(self, client: Any, seen: list[str], delay_s: float = 0.0) -> None:
        self.client, self.seen, self.delay_s = client, seen, delay_s
        self.model = getattr(client, "model", None)

    def complete(self, messages: list[dict[str, str]], max_tokens: int | None = None) -> Any:
        if self.delay_s:
            time.sleep(self.delay_s)
            self.delay_s = 0.0
        self.seen.append(messages[-1]["content"])
        return self.client.complete(messages) if max_tokens is None else self.client.complete(messages, max_tokens)

    def preflight(self) -> dict[str, Any]:
        return self.client.preflight()


def _issue16_checks(cfg: dict[str, Any], root: str, archive: dict[str, Any], seen: dict[int, list[str]],
                    check: Callable[[str, bool | None, str], None]) -> None:
    """The action record in the player's context and in action_log; the
    state-change and repeat checks on the episodes this smoke run saved."""
    from evolve import analyze as analyze_mod
    from evolve.action_loop import EpisodeAPI, build_sandbox
    from evolve.edits import normalise
    from evolve.rejected import RejectedStore, make_entry
    from evolve.replay import make_env
    from evolve.seed_v0 import build_v0
    from evolve.state_change import StateChangeChecker
    from scorer import for_game

    messages = [m for turns in seen.values() for m in turns]
    later = [m for turns in seen.values() for m in turns[1:]]
    episodes = analyze_mod.load_episodes(archive["versions"][0])
    actions = [a for e in episodes for r in e["records"] if r.get("type") == "tool_call" for a in r["actions"]]
    with_lines = [m for m in later if "Last " in m and " actions:" in m]
    check("action record in the player's context", bool(messages) and all("ACTION RECORD" in m for m in messages)
          and (bool(with_lines) or not actions),
          f"{len(messages)} turn messages, all with an ACTION RECORD block; {len(with_lines)} list earlier actions; "
          f"{len(actions)} actions, {sum(1 for a in actions if 'record' in a)} with a logged record")

    api = EpisodeAPI(make_env(cfg["game"], seed=1), int(cfg["budget"]["actions_per_turn"]), 10, 10,
                     action_record=True)
    sandbox, _counter, failed = build_sandbox(api, build_v0(cfg.get("v0_drop_prompts") or ()), 10)
    api.begin_turn(0)
    api.restore(sandbox.namespace)
    move = sorted(api.available)[0] if api.available else 6
    cell = sandbox.run((f"action({move}, x=0, y=0)\n" if move == 6 else f"action({move})\n")
                       + "print(len(action_log), action_log[0]['step'], sorted(action_log[0]))")
    check("action_log in the sandbox", not failed and cell.stdout.startswith("1 1 "),
          (cell.stdout.strip() or cell.error or "")[:200])

    edit = normalise({"op": "add", "target": "skill", "name": "smoke_click", "test": "smoke_click()",
                      "content": 'def smoke_click():\n    """Clicks the top-left cell once."""\n'
                                 '    action(6, x=0, y=0)\n'}, "meta")
    harness = build_v0(cfg.get("v0_drop_prompts") or ())
    harness.skills["smoke_click"] = edit["content"]
    checker = StateChangeChecker(cfg, episodes, for_game(cfg["game"]).read_state)
    outcome = checker.check(edit, harness)
    check("state-change check runs on the saved episodes", bool(outcome["states"]) and outcome["env_steps"] > 0,
          f"{len(outcome['states'])} test states from seeds {sorted({s['seed'] for s in outcome['states']})}: "
          f"{outcome['verdict']} ({outcome['summary'][:120]}); {outcome['env_steps']} env steps; every-step "
          f"regions {checker.regions}, fields {checker.fields}")

    store = RejectedStore(os.path.join(root, "rejected_edits.jsonl"))
    prompt = normalise({"op": "add", "target": "prompt", "name": "smoke", "content": "SMOKE\n- A line."}, "meta")
    store.add(make_entry("smoke-1", 1, "v1", prompt, harness, "validate: smoke"))
    again = RejectedStore(store.path).match(dict(prompt, content="smoke\n-   a LINE."), harness)
    check("repeat check runs on the saved store", again is not None and again[0]["id"] == "smoke-1",
          f"store {store.path}: {len(store.entries)} entry; the same text re-cased is matched "
          f"{again and (again[0]['id'], round(again[1], 3))}")


def _finish(root: str, checks: list[dict[str, Any]], log: Callable[[str], None]) -> int:
    failed = [c for c in checks if c["result"] == "FAIL"]
    os.makedirs(root, exist_ok=True)
    write_json_atomic(os.path.join(root, "smoke_report.json"), {
        "host": socket.gethostname(), "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "python": sys.version.split()[0], "checks": checks, "passed": not failed,
    })
    log(f"smoke test: {'PASSED' if not failed else 'FAILED: ' + ', '.join(c['check'] for c in failed)}")
    return 1 if failed else 0
