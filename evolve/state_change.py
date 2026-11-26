"""Stage 3 · Validate, state-change check (issue #16, change 2).

A skill whose actions have no effect is not a useful skill. #15's ft09 run
added one in every child: a skill that clicked every block of two colours,
starting with pictures that never change, so its clicks used the whole turn
and changed nothing (WORK_LOG-15). This check runs such a skill on real states
of the parent's episodes and drops it if nothing changes.

- Which skills: every new, promoted or code-edited skill that takes actions:
  it calls action() itself or through another skill of the edited harness.
  Read-only helpers are not checked.
- Test states: up to 5 states from the parent's trajectories, from different
  seeds where possible: first the turns where the skill (or the helper it was
  promoted from, or a skill merged into it) was called, then evenly spaced
  turns.
- Each state is restored by replaying that seed's logged actions in a fresh
  env. If the replayed frame is not the logged one, the state is
  unverifiable.
- The skill runs once from each state: called with no arguments if it needs
  none, else through the edit's own test snippet, else with the literal
  arguments of a recorded call. Then the frame and the game state before and
  after are compared, leaving out what changes after every action whatever
  the action is: the every-step regions of the action record
  (evolve/frame_diff.py), found in the parent's episodes and along the
  restored prefix, and the game-state fields that change on (almost) every
  action of the parent's episodes.
- Verdict: no change from every verifiable state -> drop; a change from at
  least one -> pass; every state unverifiable -> keep, flagged.

Deterministic, no model. The env steps it uses are counted on their own, not
as episode cost.
"""

from __future__ import annotations

import ast
from collections import Counter
from typing import Any, Callable

import numpy as np

from evolve.action_loop import build_sandbox, load_frames
from evolve.frame_diff import (EVERY_STEP_MIN_ACTIONS, EVERY_STEP_SHARE, ActionRecorder, changed_cells,
                               grow, in_box)
from evolve.harness import Harness
from evolve.replay import api_at_state, tool_calls
from harness.trajectory import frame_hash

MAX_STATES = 5


# ---------------------------------------------------------------------------
# Which skills
# ---------------------------------------------------------------------------


def _called(source: str) -> set[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    return {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}


def takes_actions(harness: Harness, name: str) -> bool:
    """Does the skill call action(), itself or through other skills?"""
    seen: set[str] = set()
    todo = [name]
    while todo:
        current = todo.pop()
        if current in seen or current not in harness.skills:
            continue
        seen.add(current)
        calls = _called(harness.skills[current])
        if "action" in calls:
            return True
        todo.extend(c for c in calls if c in harness.skills)
    return False


def applies_to(edit: dict[str, Any], harness: Harness) -> bool:
    return (edit["target"] == "skill" and edit["op"] in ("add", "edit", "merge")
            and takes_actions(harness, edit.get("name") or ""))


# ---------------------------------------------------------------------------
# What changes every step, from the parent's episodes
# ---------------------------------------------------------------------------


def every_step_regions(episodes: list[dict[str, Any]]) -> list[tuple[int, int, int, int]]:
    """The action record's every-step regions, over each parent episode."""
    boxes: list[tuple[int, int, int, int]] = []
    for episode in episodes:
        frames = load_frames(episode["frames"])
        recorder = ActionRecorder()
        for record in tool_calls(episode["records"]):
            for item in record.get("actions") or []:
                recorder.add(item["action_index"], item["action"], item.get("args"),
                             np.asarray(frames[item["frame_before"]]), np.asarray(frames[item["frame_after"]]))
        for box in recorder.every_step():
            if box not in boxes:
                boxes.append(box)
    return boxes


def every_step_fields(episodes: list[dict[str, Any]]) -> list[str]:
    """Game-state fields that changed on (almost) every action of a parent
    episode, whatever the action (a step counter)."""
    fields: set[str] = set()
    for episode in episodes:
        records = episode["records"]
        previous = next((r.get("start_state") for r in records if r.get("type") == "episode_start"), None)
        changes: Counter = Counter()
        keys: dict[str, set] = {}
        n = 0
        for record in tool_calls(records):
            for item in record.get("actions") or []:
                state = item.get("game_state")
                if state is None:
                    continue
                n += 1
                args = item.get("args") or {}
                key = (item["action"], args.get("x"), args.get("y"))
                if isinstance(previous, dict):
                    for field, value in state.items():
                        if previous.get(field) != value:
                            changes[field] += 1
                            keys.setdefault(field, set()).add(key)
                previous = item.get("auto_reset_state") or state
        if n >= EVERY_STEP_MIN_ACTIONS:
            fields |= {f for f, k in changes.items() if k >= EVERY_STEP_SHARE * n and len(keys[f]) >= 2}
    return sorted(fields)


# ---------------------------------------------------------------------------
# Test states
# ---------------------------------------------------------------------------


def _spread(items: list[int]) -> list[int]:
    """`items` in an evenly spread order: first, middle, quarters, ..."""
    if not items:
        return []
    order, seen = [], set()
    fractions = [0.0, 0.5, 0.25, 0.75, 0.125, 0.375, 0.625, 0.875]
    for fraction in fractions + [i / len(items) for i in range(len(items))]:
        index = min(int(fraction * len(items)), len(items) - 1)
        if index not in seen:
            seen.add(index)
            order.append(items[index])
    return order


def test_states(episodes: list[dict[str, Any]], names: set[str], limit: int = MAX_STATES) -> list[dict[str, Any]]:
    """Up to `limit` (seed, turn) states, from different seeds where
    possible: turns where one of `names` was called first."""
    called: dict[int, list[int]] = {}
    spread: dict[int, list[int]] = {}
    calls_by_seed: dict[int, dict[str, Any]] = {}
    for episode in episodes:
        seed = int(episode.get("seed", episode["episode"]))
        records = tool_calls(episode["records"])
        calls_by_seed[seed] = {"records": records, "episode": episode}
        hits = [i for i, r in enumerate(records)
                if any((r.get("skill_calls") or {}).get(n) or (r.get("inline_helper_calls") or {}).get(n)
                       for n in names)]
        called[seed] = _spread(hits)
        spread[seed] = _spread(list(range(len(records))))
    picked: list[tuple[int, int, bool]] = []
    for source, was_called in ((called, True), (spread, False)):
        queues = {s: [t for t in v] for s, v in source.items() if v}
        while len(picked) < limit and any(queues.values()):
            for seed in sorted(queues):
                while queues[seed] and len(picked) < limit:
                    turn = queues[seed].pop(0)
                    if all((seed, turn) != (s, t) for s, t, _c in picked):
                        picked.append((seed, turn, was_called))
                        break
    states = []
    for seed, turn, was_called in picked:
        records = calls_by_seed[seed]["records"]
        prefix = [(item["action"], item.get("args") or {}) for r in records[:turn] for item in r.get("actions") or []]
        states.append({"seed": seed, "turn": int(records[turn]["turn"]), "prefix": prefix,
                       "frame_hash": records[turn].get("frame_hash_before"), "skill_called_here": was_called})
    return states


# ---------------------------------------------------------------------------
# Running the skill once
# ---------------------------------------------------------------------------


def _literal_call(name: str, names: set[str], episodes: list[dict[str, Any]]) -> str | None:
    """A call of one of `names` with literal arguments from the parent's cells."""
    for episode in episodes:
        for record in tool_calls(episode["records"]):
            try:
                tree = ast.parse(record.get("code") or "")
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in names):
                    continue
                try:
                    for value in list(node.args) + [k.value for k in node.keywords]:
                        ast.literal_eval(value)
                except (ValueError, SyntaxError, TypeError):
                    continue
                if any(k.arg is None for k in node.keywords):
                    continue
                node.func.id = name
                return ast.unparse(node)
    return None


def call_code(edit: dict[str, Any], harness: Harness, episodes: list[dict[str, Any]]) -> tuple[str | None, str]:
    """(code that calls the skill once, how it was chosen)."""
    name = edit["name"]
    try:
        node = next(n for n in ast.parse(harness.skills[name]).body if isinstance(n, ast.FunctionDef))
    except (SyntaxError, StopIteration, KeyError):
        return None, "the skill does not parse"
    args = node.args
    positional = args.posonlyargs + args.args
    required = len(positional) - len(args.defaults) + sum(1 for d in args.kw_defaults if d is None)
    if required <= 0:
        return f"{name}()", "no arguments"
    if edit.get("test") and str(edit["test"]).strip():
        return str(edit["test"]), "the edit's test snippet"
    names = {name} | set(edit.get("names") or []) | {n for n, _k in edit.get("replay_strip") or []} \
        | set((edit.get("replay_rename") or {}).keys())
    copied = _literal_call(name, names, episodes)
    if copied:
        return copied, "the arguments of a recorded call"
    return None, "it needs arguments and there is no test or recorded call to take them from"


class StateChangeChecker:
    """One per Validate call: the every-step regions and fields are found
    once, from the parent's episodes."""

    def __init__(self, cfg: dict[str, Any], episodes: list[dict[str, Any]],
                 probe: Callable[[Any], dict[str, Any]] | None) -> None:
        self.cfg = cfg
        self.episodes = episodes
        self.probe = probe
        self.regions = every_step_regions(episodes)
        self.fields = every_step_fields(episodes)
        self.env_steps = 0
        self.results: list[dict[str, Any]] = []

    def _state(self, env: Any) -> dict[str, Any] | None:
        if self.probe is None:
            return None
        return {k: v for k, v in self.probe(env).items() if k not in self.fields}

    def run_once(self, harness: Harness, code: str, state: dict[str, Any]) -> dict[str, Any]:
        budget = self.cfg["budget"]
        api = api_at_state(state["prefix"], self.cfg, seed=state["seed"], probe=self.probe, action_record=True,
                           known_every_step=self.regions)
        self.env_steps += api.actions_used
        out = {"seed": state["seed"], "turn": state["turn"], "skill_called_here": state["skill_called_here"],
               "prefix_actions": len(state["prefix"])}
        if state["frame_hash"] and frame_hash(api.grid) != state["frame_hash"]:
            return out | {"verdict": "unverifiable", "why": "the replay did not reproduce the logged frame"}
        api.max_actions = api.max_resets = 10**9  # the per-turn cap still applies
        sandbox, _counter, failed = build_sandbox(api, harness, float(budget["cell_time_limit_s"]))
        if failed:
            return out | {"verdict": "unverifiable", "why": f"skills fail to load: {sorted(failed)}"}
        before, before_state = api.grid.copy(), self._state(api.env)
        first, used_before = len(api.recorder.records), api.actions_used
        api.begin_turn(0)
        api.restore(sandbox.namespace)
        result = sandbox.run(code, filename="<state-change>")
        taken = api.actions_used - used_before
        self.env_steps += taken
        after, after_state = api.grid.copy(), self._state(api.env)
        if before.shape != after.shape:
            net = {(-1, -1)}
        else:
            excluded = set().union(*api.recorder.excluded[first:]) if taken else set()
            grown = [grow(box) for box in self.regions]
            net = {cell for cell in changed_cells(before, after) - excluded
                   if not any(in_box(cell, box) for box in grown)}
        state_changed = before_state != after_state
        out |= {"actions": taken, "cells_changed": 0 if (-1, -1) in net else len(net),
                "game_state_changed": state_changed, "error": result.error}
        if (-1, -1) in net:
            out["frame_size_changed"] = True
        return out | {"verdict": "changed" if net or state_changed else "no change"}

    def check(self, edit: dict[str, Any], harness: Harness) -> dict[str, Any]:
        steps_before = self.env_steps
        names = {edit["name"]} | set(edit.get("names") or []) | {n for n, _k in edit.get("replay_strip") or []}
        code, how = call_code(edit, harness, self.episodes)
        states = test_states(self.episodes, names)
        if code is None:
            results = [{"seed": s["seed"], "turn": s["turn"], "verdict": "unverifiable", "why": how} for s in states]
        else:
            results = [self.run_once(harness, code, s) for s in states]
        changed = [r for r in results if r["verdict"] == "changed"]
        still = [r for r in results if r["verdict"] == "no change"]
        where = ", ".join(f"seed {r['seed']} turn {r['turn']}" for r in results)
        if changed:
            verdict = "changed"
            summary = f"its actions changed the game from {len(changed)} of {len(results)} test states"
        elif still:
            verdict = "no change"
            summary = (f"its actions changed nothing on screen or in the game state (outside what changes after "
                       f"every action) from any of the {len(still)} test states it could run from ({where})")
        else:
            verdict = "unverifiable"
            reasons = sorted({r.get("why", "") for r in results}) or ["no test state"]
            summary = f"could not be checked from any test state: {'; '.join(reasons)}"
        outcome = {"verdict": verdict, "summary": summary, "call": how, "states": results,
                   "env_steps": self.env_steps - steps_before}
        self.results.append({"id": edit.get("id"), "name": edit["name"], **outcome})
        return outcome

    def info(self) -> dict[str, Any]:
        return {
            "skills_checked": len(self.results),
            "dropped": sum(1 for r in self.results if r["verdict"] == "no change"),
            "unverifiable": sum(1 for r in self.results if r["verdict"] == "unverifiable"),
            "env_steps": self.env_steps,
            "every_step_regions": [list(b) for b in self.regions],
            "every_step_fields": self.fields,
            "results": self.results,
        }
