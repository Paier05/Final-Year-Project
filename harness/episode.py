"""Run one (game, seed, round) episode of ARC-AGI-3 Level 1.

Termination, per issue #8: level-1 solved, engine WIN, or budget exhausted
(actions / wall clock / tokens). GAME_OVER triggers a counted reset and play
continues, up to the reset cap.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from . import prompt as prompt_mod
from .actions import Decision, ParseFailure, fallback_decision, parse_decision
from .model import AbortExperiment, ModelCallError, ModelClient, build_user_content
from .perception import describe_diff, describe_grid, frame_diff, grid_from_frame
from .trajectory import TrajectoryWriter, frame_hash


@dataclass
class EpisodeResult:
    game_id: str
    seed: int
    round_index: int
    split: str
    solved: bool
    end_reason: str
    actions_used: int
    resets_used: int
    steps: int
    tokens_in: int
    tokens_out: int
    wall_time_s: float
    parse_failures: int
    fallback_actions: int
    module_calls: int
    skill_calls_by_name: dict[str, int] = field(default_factory=dict)
    levels_completed: int = 0
    final_state: str = ""
    human_baseline_actions: int | None = None
    error: str | None = None

    @property
    def level_score(self) -> float | None:
        """min(1, human/agent)^2, per the issue. None when no baseline exists."""
        if not self.solved or not self.human_baseline_actions:
            return None
        if self.actions_used <= 0:
            return None
        ratio = min(1.0, self.human_baseline_actions / self.actions_used)
        return round(ratio**2, 4)

    def as_row(self) -> dict[str, Any]:
        return {
            "game": self.game_id,
            "short_id": self.game_id.split("-", 1)[0],
            "seed": self.seed,
            "round": self.round_index,
            "split": self.split,
            "solved": int(self.solved),
            "end_reason": self.end_reason,
            "actions_used": self.actions_used,
            "resets_used": self.resets_used,
            "steps": self.steps,
            "human_baseline_actions": self.human_baseline_actions,
            "level_score": self.level_score,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "wall_time_s": round(self.wall_time_s, 1),
            "parse_failures": self.parse_failures,
            "fallback_actions": self.fallback_actions,
            "parse_failure_rate": (
                round(self.parse_failures / self.steps, 4) if self.steps else 0.0
            ),
            "module_calls": self.module_calls,
            "levels_completed": self.levels_completed,
            "final_state": self.final_state,
            "error": self.error or "",
        }


def _effect_text(diff: dict[str, Any], state: str, levels_completed: int) -> str:
    """One-line effect summary for the (action, effect) history."""
    parts: list[str] = []
    n_changed = diff.get("n_changed")
    if diff.get("changed") is None:
        parts.append(diff.get("note", "frame unavailable"))
    elif n_changed == 0:
        parts.append("no change")
    else:
        transitions = diff.get("transitions") or []
        top = ", ".join(
            f"{t['count']}x {t['from']}->{t['to']}" for t in transitions[:3]
        )
        r0, c0, r1, c1 = diff["bbox"]
        parts.append(
            f"{n_changed} cells changed in rows{r0}-{r1},cols{c0}-{c1} ({top})"
        )
    if state and state != "NOT_FINISHED":
        parts.append(f"state={state}")
    if levels_completed:
        parts.append(f"levels_completed={levels_completed}")
    return "; ".join(parts)


def run_episode(
    arcade: Any,
    client: ModelClient,
    game_id: str,
    seed: int,
    round_index: int,
    split: str,
    config: dict[str, Any],
    human_baseline_actions: int | None,
    skills_block: str | None = None,
    tools_block: str | None = None,
    module_runner: Callable[[str, dict[str, Any], np.ndarray], str] | None = None,
    log: Callable[[str], None] = print,
) -> EpisodeResult:
    from arcengine.enums import GameAction

    obs_cfg = config["observation"]
    budget = config["budget"]
    target_level = int(config["run"]["target_level"])

    history_n = int(obs_cfg["history_n"])
    max_actions = int(budget["max_actions"])
    max_resets = int(budget["max_resets"])
    wall_clock_s = float(budget["wall_clock_s"])
    max_tokens_episode = int(budget["max_tokens_per_episode"])

    allow_modules = module_runner is not None
    system_text = prompt_mod.system_prompt(
        history_n=history_n,
        skills_block=((skills_block or "") + (tools_block or "")) or None,
    )

    rng = random.Random(hash((game_id, seed, round_index)) & 0xFFFFFFFF)
    started = time.monotonic()

    result = EpisodeResult(
        game_id=game_id,
        seed=seed,
        round_index=round_index,
        split=split,
        solved=False,
        end_reason="",
        actions_used=0,
        resets_used=0,
        steps=0,
        tokens_in=0,
        tokens_out=0,
        wall_time_s=0.0,
        parse_failures=0,
        fallback_actions=0,
        module_calls=0,
        human_baseline_actions=human_baseline_actions,
    )

    env = arcade.make(game_id, seed=seed)
    if env is None:
        result.end_reason = "env_unavailable"
        result.error = f"arcade.make returned None for {game_id}"
        result.wall_time_s = time.monotonic() - started
        return result

    writer = TrajectoryWriter(round_index, game_id, seed)
    history: list[dict[str, Any]] = []
    scratchpad = ""
    pending_module_output: str | None = None

    try:
        frame = env.reset()
        grid = grid_from_frame(frame.frame if frame else None)
        writer.add_frame(grid)
        state = frame.state.value if frame else "UNKNOWN"
        levels_completed = int(frame.levels_completed) if frame else 0
        available = list(frame.available_actions or []) if frame else []
        last_diff: dict[str, Any] = {"changed": [], "n_changed": 0, "note": "initial"}

        while True:
            # ---- budget checks -------------------------------------------
            elapsed = time.monotonic() - started
            if result.actions_used >= max_actions:
                result.end_reason = "budget_actions"
                break
            if elapsed > wall_clock_s:
                result.end_reason = "budget_wall_clock"
                break
            if result.tokens_in + result.tokens_out > max_tokens_episode:
                result.end_reason = "budget_tokens"
                break

            observation_text, objects = describe_grid(
                grid, max_objects=int(obs_cfg["max_objects"])
            )
            diff_text = describe_diff(last_diff, int(obs_cfg["max_diff_cells"]))
            if pending_module_output:
                diff_text = f"{diff_text}\n\nMODULE OUTPUT\n{pending_module_output}"
                pending_module_output = None

            status_text = prompt_mod.format_status(
                step=result.steps,
                actions_used=result.actions_used,
                max_actions=max_actions,
                resets_used=result.resets_used,
                available_actions=available,
                state=state,
                levels_completed=levels_completed,
            )
            history_text = prompt_mod.format_history(history, history_n)

            # ---- decide (one retry on a parse failure, then fall back) ----
            decision: Decision | None = None
            retry_note: str | None = None
            tokens_in = tokens_out = latency_ms = 0

            for attempt in range(2):
                user_text = prompt_mod.user_message(
                    status_text,
                    observation_text,
                    diff_text,
                    history_text,
                    scratchpad,
                    retry_note=retry_note,
                )
                content = build_user_content(
                    user_text, grid, bool(obs_cfg["send_image"])
                )
                messages = [
                    {"role": "system", "content": system_text},
                    {"role": "user", "content": content},
                ]
                try:
                    response = client.complete(messages)
                except ModelCallError as error:
                    # A failed call is not a parse failure; treat as transient
                    # and fall back rather than killing the whole experiment.
                    log(f"    model call failed: {error}")
                    retry_note = None
                    break

                tokens_in += response.tokens_in
                tokens_out += response.tokens_out
                latency_ms += response.latency_ms
                result.tokens_in += response.tokens_in
                result.tokens_out += response.tokens_out

                try:
                    decision = parse_decision(
                        response.text, available, allow_modules=allow_modules
                    )
                    break
                except ParseFailure as error:
                    result.parse_failures += 1
                    retry_note = str(error)
                    if attempt == 1:
                        decision = None

            if decision is None:
                decision = fallback_decision(
                    available, rng, retry_note or "model call failed"
                )
                result.fallback_actions += 1

            if decision.scratchpad is not None:
                scratchpad = decision.scratchpad[: prompt_mod.MAX_SCRATCHPAD_CHARS]

            # ---- module call: costs a step, not a game action -------------
            if decision.is_module_call:
                result.steps += 1
                result.module_calls += 1
                name = decision.module or "?"
                result.skill_calls_by_name[name] = (
                    result.skill_calls_by_name.get(name, 0) + 1
                )
                try:
                    pending_module_output = module_runner(  # type: ignore[misc]
                        name, decision.module_params or {}, grid
                    )
                except Exception as error:  # modules are mined code; never fatal
                    pending_module_output = f"module {name} raised {error!r}"
                writer.write(
                    {
                        "game": game_id,
                        "seed": seed,
                        "round": round_index,
                        "step": result.steps - 1,
                        "frame_hash": frame_hash(grid),
                        "objects": objects,
                        "action": "CALL",
                        "args": decision.args,
                        "model_thought": decision.thought,
                        "scratchpad": scratchpad,
                        "next_frame_hash": frame_hash(grid),
                        "frame_diff": {"n_changed": 0, "note": "module call"},
                        "state": state,
                        "levels_completed": levels_completed,
                        "tokens_in": tokens_in,
                        "tokens_out": tokens_out,
                        "latency_ms": latency_ms,
                        "module_output": pending_module_output[:2000],
                    }
                )
                last_diff = {"changed": [], "n_changed": 0, "note": "module call"}
                continue

            # ---- execute the game action ---------------------------------
            # GameAction members are keyed by (value, kind) internally, so
            # GameAction(6) raises; from_id is the library's own accessor.
            action = GameAction.from_id(decision.action_id)
            data = decision.args or None
            if action == GameAction.RESET:
                frame = env.reset()
                result.resets_used += 1
            else:
                frame = env.step(action, data=data)
            result.actions_used += 1
            result.steps += 1

            new_grid = grid_from_frame(frame.frame if frame else None)
            writer.add_frame(new_grid)
            diff = frame_diff(grid, new_grid, int(obs_cfg["max_diff_cells"]))
            state = frame.state.value if frame else "UNKNOWN"
            levels_completed = int(frame.levels_completed) if frame else levels_completed
            available = (
                list(frame.available_actions or []) if frame else available
            )

            writer.write(
                {
                    "game": game_id,
                    "seed": seed,
                    "round": round_index,
                    "step": result.steps - 1,
                    "frame_hash": frame_hash(grid),
                    "objects": objects,
                    "action": decision.action_name,
                    "args": decision.args,
                    "model_thought": decision.thought,
                    "scratchpad": scratchpad,
                    "next_frame_hash": frame_hash(new_grid),
                    "frame_diff": diff,
                    "state": state,
                    "levels_completed": levels_completed,
                    "tokens_in": tokens_in,
                    "tokens_out": tokens_out,
                    "latency_ms": latency_ms,
                    "available_actions": available,
                }
            )

            history.append(
                {
                    "step": result.steps - 1,
                    "action": decision.action_name,
                    "args": decision.args,
                    "effect": _effect_text(diff, state, levels_completed),
                }
            )

            grid = new_grid
            last_diff = diff

            # ---- termination ---------------------------------------------
            if levels_completed >= target_level:
                result.solved = True
                result.end_reason = "level1_solved"
                break
            if state == "WIN":
                # Whole game won, which implies level 1 was cleared.
                result.solved = True
                result.end_reason = "win"
                break
            if state == "GAME_OVER":
                if result.resets_used >= max_resets:
                    result.end_reason = "game_over_reset_cap"
                    break
                frame = env.reset()
                result.resets_used += 1
                new_grid = grid_from_frame(frame.frame if frame else None)
                writer.add_frame(new_grid)
                state = frame.state.value if frame else state
                levels_completed = (
                    int(frame.levels_completed) if frame else levels_completed
                )
                available = list(frame.available_actions or []) if frame else available
                last_diff = {
                    "changed": [],
                    "n_changed": 0,
                    "note": "harness auto-reset after GAME_OVER",
                }
                history.append(
                    {
                        "step": result.steps - 1,
                        "action": "AUTO_RESET",
                        "args": {},
                        "effect": "game over; harness reset the level",
                    }
                )
                grid = new_grid

        result.levels_completed = levels_completed
        result.final_state = state

    except AbortExperiment:
        writer.close()
        raise
    except Exception as error:  # noqa: BLE001 - one game must not kill the sweep
        result.end_reason = result.end_reason or "error"
        result.error = f"{type(error).__name__}: {error}"
    finally:
        try:
            writer.close()
        except Exception:
            pass
        result.wall_time_s = time.monotonic() - started

    return result
