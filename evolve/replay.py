"""Deterministic replay of logged code cells, with no model in the loop.

ls20 is deterministic and seed-independent (verified 2026-11-01: #8's 200
logged actions reproduce every frame hash under a different seed), and the
sandbox forbids randomness and clocks. So re-running an episode's logged cells,
in order, against a fresh environment reproduces the episode -- *if the harness
is the same*. Validate uses that two ways:

- fidelity:    replay under the parent harness; turns that reproduce exactly are
               the trustworthy evidence base.
- candidate:   replay under the edited harness (optionally with the cells
               rewritten, e.g. an inline helper stripped so the promoted skill
               is the one that runs). Any turn that reproduced under the parent
               but not under the candidate is a behaviour change the edit caused.

A turn "reproduces" when it issues the same actions with the same arguments and
errors (or not) the same way. Printed output is not compared: dict and set
ordering of strings varies with the per-process hash seed, and stdout is not
behaviour.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable

from evolve.action_loop import EpisodeAPI, build_sandbox
from evolve.harness import Harness
from evolve.sandbox import TurnOver

_ARCADE = None
_ARCADE_LOCK = threading.Lock()


def make_env(game_id: str, seed: int = 0) -> Any:
    """One shared Arcade, a fresh environment per call."""
    global _ARCADE
    import arc_agi

    with _ARCADE_LOCK:
        if _ARCADE is None:
            _ARCADE = arc_agi.Arcade()
        return _ARCADE.make(game_id, seed=seed)


@dataclass
class ReplayResult:
    turns: int = 0
    reproduced: list[bool] = field(default_factory=list)
    errors: list[bool] = field(default_factory=list)
    skill_calls: dict[str, int] = field(default_factory=dict)
    skill_errors: dict[str, int] = field(default_factory=dict)
    skills_failed_to_load: dict[str, str] = field(default_factory=dict)
    first_divergence: int | None = None

    @property
    def n_reproduced(self) -> int:
        return sum(self.reproduced)


def tool_calls(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in records if r.get("type") == "tool_call"]


def replay(
    records: list[dict[str, Any]],
    harness: Harness,
    cfg: dict[str, Any],
    transform: Callable[[str], str] | None = None,
    stop_at_divergence: bool = False,
) -> ReplayResult:
    budget = cfg["budget"]
    env = make_env(cfg["game"])
    api = EpisodeAPI(
        env,
        actions_per_turn=int(budget["actions_per_turn"]),
        max_actions=int(budget["max_actions"]),
        max_resets=int(budget["max_resets"]),
    )
    sandbox, counter, failed = build_sandbox(api, harness, float(budget["cell_time_limit_s"]))
    result = ReplayResult(skills_failed_to_load=failed)
    for record in tool_calls(records):
        api.begin_turn(int(record["turn"]))
        code = record.get("code")
        if not code or record.get("parse_failure"):
            result.reproduced.append(True)  # nothing ran then, nothing runs now
            result.errors.append(False)
            result.turns += 1
            continue
        if transform is not None:
            code = transform(code)
        cell = sandbox.run(code, filename=f"<turn {record['turn']}>")
        now = [(a["action"], a.get("args") or {}) for a in api.turn_actions]
        then = [(a["action"], a.get("args") or {}) for a in record.get("actions") or []]
        same = now == then and bool(cell.error) == bool(record.get("error"))
        result.reproduced.append(same)
        result.errors.append(bool(cell.error))
        result.turns += 1
        if not same and result.first_divergence is None:
            result.first_divergence = int(record["turn"])
            if stop_at_divergence:
                break
        if api.done_reason:
            break
    result.skill_calls = dict(counter.calls)
    result.skill_errors = dict(counter.errors)
    return result


def states_along(
    records: list[dict[str, Any]], cfg: dict[str, Any], fractions: tuple[float, ...]
) -> list[tuple[str, list[tuple[str, dict]]]]:
    """Action prefixes that rebuild real recorded states (for skill tests).

    Returns [(label, [(action, args), ...])] -- replaying the prefix on a fresh
    environment lands exactly on the recorded state at that fraction of the
    episode.
    """
    actions: list[tuple[str, dict]] = []
    for record in tool_calls(records):
        for item in record.get("actions") or []:
            actions.append((item["action"], item.get("args") or {}))
    out = []
    for fraction in fractions:
        cut = int(len(actions) * fraction)
        out.append((f"after {cut} actions", actions[:cut]))
    return out


def api_at_state(
    prefix: list[tuple[str, dict]], cfg: dict[str, Any]
) -> EpisodeAPI:
    """A fresh EpisodeAPI advanced through `prefix`, with a fresh turn budget."""
    budget = cfg["budget"]
    env = make_env(cfg["game"])
    api = EpisodeAPI(
        env,
        actions_per_turn=10**9,
        max_actions=10**9,
        max_resets=10**9,
    )
    for action, args in prefix:
        api.begin_turn(0)
        action_id = 0 if action == "RESET" else int(action.replace("ACTION", ""))
        try:
            api.action(action_id, **({"x": args["x"], "y": args["y"]} if args else {}))
        except (TurnOver, ValueError):  # a clear or an exhausted cap ends the prefix
            break
    api.actions_per_turn = int(budget["actions_per_turn"])
    api.max_actions = int(budget["max_actions"])
    api.max_resets = int(budget["max_resets"])
    api.done_reason = None
    api.begin_turn(0)
    return api
