"""The action harness: play one ls20 Level-1 episode with a harness version.

One turn = one player-LLM call. The reply's code cell runs in the sandbox
(`evolve/sandbox.py`), which has the episode API and the harness's skills
preloaded and acts on the game through `action()`, capped per turn. Every tool
call -- every executed cell -- is one JSONL record.

The same `EpisodeAPI` + `Sandbox` pair is used by Validate to *replay* logged
cells against a live environment without any model, which is why everything a
cell can observe is deterministic.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from harness.episode import _effect_text
from harness.model import AbortExperiment, ModelCallError
from harness.perception import (
    COLOUR_NAMES,
    connected_components,
    describe_grid,
    frame_diff,
    grid_from_frame,
)
from harness.trajectory import frame_hash
from evolve.harness import EVOLVE_DIR, Harness
from evolve.sandbox import (
    Sandbox,
    SandboxViolation,
    TurnOver,
    called_names,
    defined_functions,
)

TRAJ_ROOT = os.path.join(EVOLVE_DIR, "trajectories")
FRAME_ROOT = os.path.join(EVOLVE_DIR, "frames")

CODE_RE = re.compile(r"```[ \t]*(?:python|py)?[ \t]*\n(.*?)```", re.DOTALL | re.IGNORECASE)
OPEN_CODE_RE = re.compile(r"```[ \t]*(?:python|py)[ \t]*\n(.*)$", re.DOTALL | re.IGNORECASE)
MAX_NOTES_CHARS = 2000


def trajectory_path(round_index: int, episode: int, root: str = TRAJ_ROOT) -> str:
    return os.path.join(root, f"round_{round_index}", f"episode_{episode}.jsonl")


def frames_path(round_index: int, episode: int, root: str = FRAME_ROOT) -> str:
    return os.path.join(root, f"round_{round_index}", f"episode_{episode}.npz")


# ---------------------------------------------------------------------------
# The API the player's code sees
# ---------------------------------------------------------------------------


class EpisodeAPI:
    """Game state + the functions preloaded into the sandbox.

    `action()` is the only way to touch the environment. It enforces the
    per-turn cap, the episode action budget and the reset cap, and raises
    `TurnOver` (not an error) to end the cell when one of them is hit or Level 1
    is cleared.
    """

    def __init__(
        self,
        env: Any,
        actions_per_turn: int,
        max_actions: int,
        max_resets: int,
        target_level: int = 1,
    ) -> None:
        from arcengine.enums import GameAction

        self._GameAction = GameAction
        self.env = env
        self.actions_per_turn = actions_per_turn
        self.max_actions = max_actions
        self.max_resets = max_resets
        self.target_level = target_level

        frame = env.reset()
        self.grid = grid_from_frame(frame.frame if frame else None)
        self.state = frame.state.value if frame else "UNKNOWN"
        self.levels_completed = int(frame.levels_completed) if frame else 0
        self.available = list(frame.available_actions or []) if frame else []

        self.frames: list[np.ndarray] = [self.grid.copy()]
        self.history: list[dict[str, Any]] = []
        self.actions_used = 0
        self.resets_used = 0
        self.turn = 0
        self.turn_actions: list[dict[str, Any]] = []
        self.done_reason: str | None = None
        self.solved = False
        self.steps_to_clear: int | None = None

    # -- turn bookkeeping (harness side) -------------------------------------

    def begin_turn(self, turn: int) -> None:
        self.turn = turn
        self.turn_actions = []

    # -- functions exposed to the sandbox ------------------------------------

    def action(self, a: Any, x: Any = None, y: Any = None) -> dict[str, Any]:
        if self.done_reason:
            raise TurnOver(self.done_reason)
        if len(self.turn_actions) >= self.actions_per_turn:
            raise TurnOver(f"turn action cap ({self.actions_per_turn}) reached")

        action_id = _parse_action_id(a)
        if action_id != 0 and action_id not in self.available:
            names = ", ".join(f"ACTION{i}" for i in sorted(self.available)) or "none"
            raise ValueError(f"ACTION{action_id} is not available; available: {names}")
        data = None
        if action_id == 6:
            if x is None or y is None:
                raise ValueError("ACTION6 needs x (column) and y (row)")
            x, y = int(x), int(y)
            if not (0 <= x <= 63 and 0 <= y <= 63):
                raise ValueError("ACTION6 x and y must be in 0..63")
            data = {"x": x, "y": y}

        action = self._GameAction.from_id(action_id)
        if action_id == 0:
            frame = self.env.reset()
            self.resets_used += 1
        else:
            frame = self.env.step(action, data=data)
        self.actions_used += 1

        before = self.grid
        frame_index_before = len(self.frames) - 1
        self.grid = grid_from_frame(frame.frame if frame else None)
        self.frames.append(self.grid.copy())
        self.state = frame.state.value if frame else "UNKNOWN"
        self.levels_completed = int(frame.levels_completed) if frame else self.levels_completed
        self.available = list(frame.available_actions or []) if frame else self.available
        diff = frame_diff(before, self.grid, max_cells=0)
        name = "RESET" if action_id == 0 else f"ACTION{action_id}"
        effect = _effect_text(diff, self.state, self.levels_completed)

        record = {
            "turn": self.turn,
            "action": name,
            "args": data or {},
            "effect": effect,
            "n_changed": diff.get("n_changed"),
            "frame_before": frame_index_before,
            "frame_after": len(self.frames) - 1,
            "next_frame_hash": frame_hash(self.grid),
            "state": self.state,
            "levels_completed": self.levels_completed,
            "action_index": self.actions_used,
        }
        game_over = False
        if self.state == "GAME_OVER" and self.levels_completed < self.target_level:
            game_over = True
            if self.resets_used >= self.max_resets:
                self.done_reason = "game_over_reset_cap"
            else:
                frame = self.env.reset()
                self.resets_used += 1
                self.grid = grid_from_frame(frame.frame if frame else None)
                self.frames.append(self.grid.copy())
                self.state = frame.state.value if frame else self.state
                self.available = list(frame.available_actions or []) if frame else self.available
                record["effect"] += "; game over, the harness reset the level"
                record["auto_reset_frame"] = len(self.frames) - 1
        self.turn_actions.append(record)
        self.history.append(
            {"turn": self.turn, "action": name, "args": data or {}, "effect": record["effect"]}
        )

        if self.levels_completed >= self.target_level or self.state == "WIN":
            self.solved = True
            self.steps_to_clear = self.actions_used
            self.done_reason = "level1_solved"
            raise TurnOver("level 1 cleared")
        if self.actions_used >= self.max_actions and not self.done_reason:
            self.done_reason = "budget_actions"
        if self.done_reason == "game_over_reset_cap":
            raise TurnOver(self.done_reason)

        return {
            "action": name,
            "n_changed": diff.get("n_changed"),
            "state": self.state,
            "levels_completed": self.levels_completed,
            "game_over": game_over,
            "effect": record["effect"],
        }

    def grid_fn(self) -> np.ndarray:
        return self.grid.copy()

    def objects_fn(self, g: Any = None) -> list[dict[str, Any]]:
        target = self.grid if g is None else np.asarray(g)
        objs = connected_components(target)
        for obj in objs:
            obj.pop("id", None)
        return objs

    @staticmethod
    def diff_fn(a: Any, b: Any) -> list[tuple[int, int, int, int]]:
        a, b = np.asarray(a), np.asarray(b)
        if a.shape != b.shape:
            raise ValueError(f"grids differ in shape: {a.shape} vs {b.shape}")
        rows, cols = np.nonzero(a != b)
        return [(int(r), int(c), int(a[r, c]), int(b[r, c])) for r, c in zip(rows, cols)]

    def status_fn(self) -> dict[str, Any]:
        return {
            "actions_used": self.actions_used,
            "actions_left": self.max_actions - self.actions_used,
            "turn": self.turn,
            "turn_actions_left": self.actions_per_turn - len(self.turn_actions),
            "state": self.state,
            "levels_completed": self.levels_completed,
            "available_actions": list(self.available),
            "resets": self.resets_used,
        }

    def history_fn(self, n: int = 10) -> list[dict[str, Any]]:
        return [dict(h) for h in self.history[-int(n):]] if n else []

    def preload(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "grid": self.grid_fn,
            "objects": self.objects_fn,
            "diff": self.diff_fn,
            "status": self.status_fn,
            "history": self.history_fn,
            "COLOURS": dict(COLOUR_NAMES),
        }


def _parse_action_id(a: Any) -> int:
    if isinstance(a, str):
        text = a.strip().upper()
        if text == "RESET":
            return 0
        text = text.replace("ACTION", "")
        if not text.isdigit():
            raise ValueError(f"unknown action {a!r}; use 1..7 or 0 for RESET")
        a = int(text)
    if isinstance(a, bool) or not isinstance(a, (int, np.integer)):
        raise ValueError(f"action must be an int 0..7, got {a!r}")
    a = int(a)
    if not 0 <= a <= 7:
        raise ValueError(f"action must be 0..7, got {a}")
    return a


# ---------------------------------------------------------------------------
# Skills: loaded into the sandbox and counted
# ---------------------------------------------------------------------------


@dataclass
class SkillCounter:
    calls: dict[str, int] = field(default_factory=dict)
    errors: dict[str, int] = field(default_factory=dict)
    last_error: dict[str, str] = field(default_factory=dict)

    def snapshot(self) -> tuple[dict[str, int], dict[str, int]]:
        return dict(self.calls), dict(self.errors)


def install_skills(
    sandbox: Sandbox, skills: dict[str, str], counter: SkillCounter
) -> dict[str, str]:
    """Load each skill and wrap it so calls and errors are counted.

    Returns {name: error} for skills that failed to load; those are left out of
    the namespace rather than aborting the episode.
    """
    failed: dict[str, str] = {}
    for name, source in sorted(skills.items()):
        try:
            sandbox.load_skill_source(name, source)
        except (SandboxViolation, Exception) as error:  # noqa: BLE001
            failed[name] = f"{type(error).__name__}: {error}"
            sandbox.namespace.pop(name, None)
    for name in skills:
        fn = sandbox.namespace.get(name)
        if callable(fn) and name not in failed:
            sandbox.namespace[name] = _counted(name, fn, counter)
    return failed


def _counted(name: str, fn: Callable[..., Any], counter: SkillCounter) -> Callable[..., Any]:
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        counter.calls[name] = counter.calls.get(name, 0) + 1
        try:
            return fn(*args, **kwargs)
        except Exception as error:  # TurnOver/timeout are BaseException: not counted
            counter.errors[name] = counter.errors.get(name, 0) + 1
            counter.last_error[name] = f"{type(error).__name__}: {error}"
            raise

    wrapper.skill_name = name  # type: ignore[attr-defined]
    return wrapper


def build_sandbox(
    api: EpisodeAPI, harness: Harness, time_limit_s: float
) -> tuple[Sandbox, SkillCounter, dict[str, str]]:
    sandbox = Sandbox(preload=api.preload(), time_limit_s=time_limit_s)
    counter = SkillCounter()
    failed = install_skills(sandbox, harness.skills, counter)
    return sandbox, counter, failed


# ---------------------------------------------------------------------------
# Prompt pieces
# ---------------------------------------------------------------------------


def extract_code(reply: str) -> str | None:
    """The last fenced code block in a reply, or None."""
    text = re.sub(r"<think>.*?</think>", "", reply or "", flags=re.DOTALL)
    blocks = CODE_RE.findall(text)
    if blocks:
        return blocks[-1].strip("\n")
    # A reply cut off by max_tokens can leave the fence unclosed. Keep what is
    # there; if it is not valid Python the sandbox reports the SyntaxError to
    # the model, which is more useful than discarding the turn.
    match = OPEN_CODE_RE.search(text)
    if match:
        return match.group(1).strip("\n")
    return None


def format_cell_result(record: dict[str, Any] | None) -> str:
    if record is None:
        return "LAST CELL: none yet; this is your first turn."
    lines = [f"LAST CELL (turn {record['turn']})"]
    if record.get("parse_failure"):
        lines.append("  no code was executed: your reply had no ```python code block.")
        return "\n".join(lines)
    actions = record.get("actions") or []
    if actions:
        lines.append(f"  actions taken ({len(actions)}):")
        for item in actions:
            args = f" {item['args']}" if item.get("args") else ""
            lines.append(f"    {item['action']}{args} -> {item['effect']}")
    else:
        lines.append("  actions taken: none")
    if record.get("stopped_by"):
        lines.append(f"  cell stopped early: {record['stopped_by']}")
    if record.get("error"):
        lines.append(f"  ERROR: {record['error']}")
    stdout = (record.get("stdout") or "").rstrip()
    lines.append("  printed output:" if stdout else "  printed output: (nothing)")
    if stdout:
        lines.extend(f"    {line}" for line in stdout.splitlines())
    return "\n".join(lines)


def format_status(api: EpisodeAPI, turn: int, max_turns: int) -> str:
    names = ", ".join(
        "RESET" if a == 0 else f"ACTION{a}" for a in sorted(api.available)
    )
    return (
        f"STATUS: turn {turn}/{max_turns} | actions used {api.actions_used}/"
        f"{api.max_actions} | up to {api.actions_per_turn} actions this turn | "
        f"resets {api.resets_used} | engine state {api.state} | levels completed "
        f"{api.levels_completed}\nAVAILABLE ACTIONS: {names or 'none reported'}"
    )


def format_history(api: EpisodeAPI, n: int) -> str:
    if not api.history:
        return "RECENT ACTIONS: none yet."
    recent = api.history[-n:]
    lines = [f"RECENT ACTIONS (most recent {len(recent)} of {len(api.history)}):"]
    for entry in recent:
        args = f" {entry['args']}" if entry.get("args") else ""
        lines.append(f"  turn {entry['turn']}: {entry['action']}{args} -> {entry['effect']}")
    return "\n".join(lines)


def user_message(
    api: EpisodeAPI,
    turn: int,
    max_turns: int,
    last_record: dict[str, Any] | None,
    notes: str,
    max_objects: int,
    history_n: int,
    retry_note: str | None = None,
) -> str:
    observation, _ = describe_grid(api.grid, max_objects=max_objects)
    blocks = [
        format_status(api, turn, max_turns),
        "",
        "OBSERVATION",
        observation,
        "",
        format_cell_result(last_record),
        "",
        format_history(api, history_n),
        "",
        "NOTES (the `notes` variable)",
        notes.strip() or "(empty)",
    ]
    if retry_note:
        blocks += ["", f"FORMAT ERROR ON YOUR LAST REPLY: {retry_note}"]
    blocks += ["", "Follow the turn procedure, then reply with exactly one ```python code block."]
    return "\n".join(blocks)


# ---------------------------------------------------------------------------
# One episode
# ---------------------------------------------------------------------------


@dataclass
class EpisodeOutcome:
    round_index: int
    episode: int
    version: str
    solved: bool
    steps_to_clear: int | None
    end_reason: str
    actions_used: int
    turns: int
    resets_used: int
    tokens_in: int
    tokens_out: int
    wall_time_s: float
    parse_failures: int
    fallback_turns: int
    cell_errors: int
    timeouts: int
    trajectory: str
    frames: str
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def run_episode(
    *,
    env: Any,
    client: Any,
    harness: Harness,
    round_index: int,
    episode: int,
    cfg: dict[str, Any],
    stop_event: threading.Event | None = None,
    traj_root: str = TRAJ_ROOT,
    frame_root: str = FRAME_ROOT,
    log: Callable[[str], None] = print,
) -> EpisodeOutcome:
    budget = cfg["budget"]
    obs_cfg = cfg["observation"]
    per_turn = int(budget["actions_per_turn"])
    max_turns = int(budget["max_turns"])
    wall_clock_s = float(budget["wall_clock_s"])
    max_tokens_episode = int(budget["max_tokens_per_episode"])

    started = time.monotonic()
    api = EpisodeAPI(
        env,
        actions_per_turn=per_turn,
        max_actions=int(budget["max_actions"]),
        max_resets=int(budget["max_resets"]),
    )
    sandbox, counter, failed_skills = build_sandbox(
        api, harness, float(budget["cell_time_limit_s"])
    )
    system_text = harness.render_system(per_turn)

    tpath = trajectory_path(round_index, episode, traj_root)
    fpath = frames_path(round_index, episode, frame_root)
    os.makedirs(os.path.dirname(tpath), exist_ok=True)
    os.makedirs(os.path.dirname(fpath), exist_ok=True)

    outcome = EpisodeOutcome(
        round_index=round_index, episode=episode, version=harness.version,
        solved=False, steps_to_clear=None, end_reason="", actions_used=0, turns=0,
        resets_used=0, tokens_in=0, tokens_out=0, wall_time_s=0.0,
        parse_failures=0, fallback_turns=0, cell_errors=0, timeouts=0,
        trajectory=tpath.replace(os.sep, "/"), frames=fpath.replace(os.sep, "/"),
    )
    last_record: dict[str, Any] | None = None
    inline_defined: dict[str, str] = {}  # helper name -> key, this episode

    with open(tpath, "w", encoding="utf-8") as handle:
        header = {
            "type": "episode_start",
            "round": round_index,
            "episode": episode,
            "version": harness.version,
            "system_prompt_chars": len(system_text),
            "skills": sorted(harness.skills),
            "skills_failed_to_load": failed_skills,
            "start_frame_hash": frame_hash(api.grid),
        }
        handle.write(json.dumps(header) + "\n")
        try:
            for turn in range(max_turns):
                if api.done_reason:
                    break
                if stop_event is not None and stop_event.is_set():
                    outcome.end_reason = "aborted"
                    break
                if time.monotonic() - started > wall_clock_s:
                    outcome.end_reason = "budget_wall_clock"
                    break
                if outcome.tokens_in + outcome.tokens_out > max_tokens_episode:
                    outcome.end_reason = "budget_tokens"
                    break

                notes = str(sandbox.namespace.get("notes", ""))[:MAX_NOTES_CHARS]
                code: str | None = None
                reply_text = ""
                retry_note: str | None = None
                tokens_in = tokens_out = latency_ms = 0
                parse_failed = False
                for attempt in range(2):
                    user_text = user_message(
                        api, turn, max_turns, last_record, notes,
                        int(obs_cfg["max_objects"]), int(obs_cfg["history_n"]), retry_note,
                    )
                    messages = [
                        {"role": "system", "content": system_text},
                        {"role": "user", "content": user_text},
                    ]
                    try:
                        response = client.complete(messages)
                    except ModelCallError as error:
                        log(f"    [ep{episode}] model call failed: {error}")
                        break
                    tokens_in += response.tokens_in
                    tokens_out += response.tokens_out
                    latency_ms += response.latency_ms
                    reply_text = response.text
                    code = extract_code(reply_text)
                    if code is not None and code.strip():
                        break
                    outcome.parse_failures += 1
                    parse_failed = True
                    retry_note = "no ```python code block found. End your reply with exactly one."
                outcome.tokens_in += tokens_in
                outcome.tokens_out += tokens_out

                api.begin_turn(turn)
                start_hash = frame_hash(api.grid)
                start_frame = len(api.frames) - 1
                calls_before, errors_before = counter.snapshot()
                cell = None
                if code is not None and code.strip():
                    cell = sandbox.run(code, filename=f"<turn {turn}>")
                else:
                    outcome.fallback_turns += 1
                calls_after, errors_after = counter.snapshot()

                defined = defined_functions(code or "")
                for item in defined:
                    inline_defined[item["name"]] = item["key"]
                called = called_names(code or "")
                skill_calls = {
                    k: v - calls_before.get(k, 0)
                    for k, v in calls_after.items()
                    if v - calls_before.get(k, 0)
                }
                skill_errors = {
                    k: v - errors_before.get(k, 0)
                    for k, v in errors_after.items()
                    if v - errors_before.get(k, 0)
                }
                helper_calls = {
                    name: n for name, n in called.items()
                    if name in inline_defined and name not in harness.skills
                }

                if cell is not None and cell.error:
                    outcome.cell_errors += 1
                if cell is not None and cell.timed_out:
                    outcome.timeouts += 1

                record = {
                    "type": "tool_call",
                    "round": round_index,
                    "episode": episode,
                    "version": harness.version,
                    "turn": turn,
                    "frame_hash_before": start_hash,
                    "frame_index_before": start_frame,
                    "reply": reply_text,
                    "code": code,
                    "parse_failure": code is None or not code.strip(),
                    "retried": parse_failed,
                    "actions": api.turn_actions,
                    "stdout": cell.stdout if cell else "",
                    "error": cell.error if cell else None,
                    "timed_out": bool(cell and cell.timed_out),
                    "violation": bool(cell and cell.violation),
                    "stopped_by": cell.stopped_by if cell else None,
                    "skill_calls": skill_calls,
                    "skill_errors": skill_errors,
                    "inline_helpers_defined": defined,
                    "inline_helper_calls": helper_calls,
                    "shadowed_skills": [d["name"] for d in defined if d["name"] in harness.skills],
                    "notes": str(sandbox.namespace.get("notes", ""))[:MAX_NOTES_CHARS],
                    "actions_used": api.actions_used,
                    "state": api.state,
                    "levels_completed": api.levels_completed,
                    "tokens_in": tokens_in,
                    "tokens_out": tokens_out,
                    "latency_ms": latency_ms,
                }
                handle.write(json.dumps(record, default=_json_default) + "\n")
                handle.flush()
                last_record = record
                outcome.turns = turn + 1
            else:
                outcome.end_reason = outcome.end_reason or "budget_turns"
        except AbortExperiment:
            outcome.end_reason = "aborted"
            raise
        except Exception as error:  # noqa: BLE001 - one episode must not kill the round
            outcome.end_reason = "error"
            outcome.error = f"{type(error).__name__}: {error}"
        finally:
            outcome.solved = api.solved
            outcome.steps_to_clear = api.steps_to_clear
            outcome.actions_used = api.actions_used
            outcome.resets_used = api.resets_used
            outcome.end_reason = api.done_reason or outcome.end_reason or "budget_turns"
            outcome.wall_time_s = round(time.monotonic() - started, 1)
            if len({f.shape for f in api.frames}) == 1:
                np.savez_compressed(fpath, frames=np.stack(api.frames).astype(np.int8))
            else:  # a level change resized the grid; keep frames individually
                np.savez_compressed(fpath, **{f"f{i}": f for i, f in enumerate(api.frames)})
            handle.write(json.dumps({"type": "episode_end", **outcome.as_dict()}) + "\n")
    return outcome


def _json_default(value: Any) -> Any:
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    return str(value)


def load_frames(path: str) -> list[np.ndarray] | np.ndarray:
    with np.load(path) as archive:
        if "frames" in archive.files:
            return archive["frames"]
        return [archive[f"f{i}"] for i in range(len(archive.files))]


def read_records(path: str) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]
