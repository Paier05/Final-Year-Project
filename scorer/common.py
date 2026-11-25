"""What the ft09 and vc33 scorers share (issue #15).

The contract is #12/#14's (evolve/goal_score.py): a state scores
sum(weight * part) with every part in [0, 1]; an episode scores its best
Level-1 state; a clear scores 1.0; deterministic, no model. States come from
the `game_state` records the action loop logs after every action.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable

import numpy as np

from evolve.goal_score import states_from_records

# Roles the fact-check's vocabulary has that nothing on Level 1 of ft09 or
# vc33 plays: a claim that some colour is one is false.
ABSENT_ROLES_CLICK_GAME = ("collectible", "hazard", "trail", "enemy", "lives", "rotation_switch")


def score_states(
    states: list[dict[str, Any]], cleared: bool, parts_of: Callable[[dict[str, Any]], dict[str, float] | None],
    weights: dict[str, float], parts: tuple[str, ...],
) -> dict[str, Any]:
    scored = []
    for state in states:
        found = parts_of(state)
        if found is not None:
            scored.append((sum(weights[p] * found[p] for p in parts), state, found))
    if not scored:
        raise ValueError("no Level-1 state to score")
    best_value, best_state, best_parts = max(scored, key=lambda item: item[0])  # first max wins
    if cleared:
        score, values = 1.0, {p: 1.0 for p in parts}
    else:
        score, values = best_value, {p: best_parts[p] for p in parts}
    return {
        "score": round(score, 4),
        "cleared": cleared,
        "parts": {p: round(v, 4) for p, v in values.items()},
        "contributions": {p: round(weights[p] * values[p], 4) for p in parts},
        "failing_parts": [] if cleared else [p for p in parts if values[p] < 1.0],
        "best_state": {"action_index": best_state["action_index"],
                       **{k: v for k, v in best_parts.items() if k.startswith("_")}},
        "n_states": len(states),
        "_scored": scored,
    }


def score_records(
    records: list[dict[str, Any]], parts_of: Callable[[dict[str, Any]], dict[str, float] | None],
    weights: dict[str, float], parts: tuple[str, ...],
) -> tuple[dict[str, Any], list[tuple[float, dict[str, Any], dict[str, float]]]]:
    """(result, scored states). Only logged states: these games' runs log
    `game_state` from the first episode on, so there is no replay fallback."""
    states, cleared = states_from_records(records)
    result = score_states(states, cleared, parts_of, weights, parts)
    result["state_source"] = "logged game_state"
    return result, result.pop("_scored")


def display_box(sprite: Any, scale: int) -> tuple[int, int, int, int]:
    """(r0, c0, r1, c1) on the 64x64 observation of a sprite on a grid shown
    at `scale` display cells per grid cell."""
    return (int(sprite.y) * scale, int(sprite.x) * scale,
            (int(sprite.y) + int(sprite.height)) * scale - 1, (int(sprite.x) + int(sprite.width)) * scale - 1)


def sprite_colours(sprite: Any) -> set[int]:
    pixels = np.asarray(sprite.pixels)
    return {int(v) for v in np.unique(pixels) if v >= 0}


def truth_roles(
    frame0: np.ndarray, objects: dict[str, list[tuple[tuple[int, int, int, int], set[int]]]],
    extra: dict[int, set[str]] | None = None,
) -> tuple[dict[str, list[tuple[int, int, int, int]]], dict[str, set[str]]]:
    """Boxes per object and roles per colour name, for the fact-check.

    An object's colours are the sprite's own (opaque) pixel values, not what
    shows through it. Every colour that is also on screen outside the known
    objects -- the background included -- gets "ui", so a claim giving it a
    role the code cannot check is unverifiable rather than false.
    """
    from harness.perception import COLOUR_NAMES

    boxes: dict[str, list[tuple[int, int, int, int]]] = defaultdict(list)
    roles: dict[str, set[str]] = defaultdict(set)
    explained = np.zeros(frame0.shape, dtype=bool)
    for name, items in objects.items():
        for box, colours in items:
            boxes[name].append(box)
            for colour in colours:
                roles[COLOUR_NAMES[colour]].add(name)
            r0, c0, r1, c1 = box
            explained[r0:r1 + 1, c0:c1 + 1] |= np.isin(frame0[r0:r1 + 1, c0:c1 + 1], list(colours))
    for colour in np.unique(frame0[~explained]):
        roles[COLOUR_NAMES[int(colour)]].add("ui")
    for colour, extra_roles in (extra or {}).items():
        roles[COLOUR_NAMES[colour]] |= extra_roles
    return dict(boxes), dict(roles)


def span(box: tuple[int, int, int, int]) -> str:
    r0, c0, r1, c1 = box
    return f"rows {r0}-{r1}, cols {c0}-{c1}"
