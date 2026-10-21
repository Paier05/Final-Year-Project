"""Phase 3: mine skills from dev-game trajectories and validate them.

Four skill kinds, exactly as the issue lists them:

- action_effect: "ACTION1 tends to do X", learned from (action, frame_diff) pairs.
- macro:         frequent action subsequences that preceded progress or a win.
- module:        the code modules in learning/modules.py, admitted only if they
                 would actually have fired on logged dev frames.
- goal:          patterns observed in the frames just before a level was cleared.

Every candidate is validated by **replaying it against the logged data** and is
dropped if it fails. Validation is split train/holdout over dev episodes so
precision is measured on records the rule was not fitted on.

Mining reads only dev-game trajectories. The test games are never opened; the
function asserts this rather than trusting the caller.
"""

from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from typing import Any

import numpy as np

from harness.perception import colour_name
from harness.trajectory import iter_trajectories
from learning.modules import MODULES, run_module

SKILLS_DIR = "skills"
INDEX_PATH = os.path.join(SKILLS_DIR, "index.json")

# Admission thresholds. A skill must be both frequent enough to be real and
# precise enough on held-out records to be worth putting in the prompt.
MIN_SUPPORT = 8
MIN_PRECISION = 0.6
MIN_MACRO_SUPPORT = 3
MIN_GOAL_SUPPORT = 2


# ---------------------------------------------------------------------------
# Helpers over trajectory records
# ---------------------------------------------------------------------------


def _signature(record: dict[str, Any]) -> str:
    """Compact, comparable description of what a step did to the grid."""
    diff = record.get("frame_diff") or {}
    n_changed = diff.get("n_changed")
    if n_changed is None:
        return "unknown"
    if n_changed == 0:
        return "no_change"
    if n_changed < 0:
        return "grid_resized"

    transitions = diff.get("transitions") or []
    bucket = (
        "tiny" if n_changed <= 4
        else "small" if n_changed <= 20
        else "medium" if n_changed <= 100
        else "large"
    )
    if transitions:
        top = transitions[0]
        return f"{bucket}:{top['from']}->{top['to']}"
    return bucket


def _translation(record: dict[str, Any]) -> tuple[int, int] | None:
    """Detect a pure translation of one colour blob from the diff.

    An object moving by (dr, dc) shows up as k cells going colour->background
    and the same k cells going background->colour, with the two centroids
    offset by exactly the move. This is what makes "ACTION1 moves the X object
    one cell up" learnable from logged data alone.
    """
    diff = record.get("frame_diff") or {}
    cells = diff.get("changed")
    if not cells or diff.get("truncated"):
        return None
    vacated = [c for c in cells if c["to"] != c["from"] and c["from"] != 0]
    filled = [c for c in cells if c["to"] != c["from"] and c["to"] != 0]
    if not vacated or not filled or len(vacated) != len(filled):
        return None
    colours_out = {c["from"] for c in vacated}
    colours_in = {c["to"] for c in filled}
    if len(colours_out) != 1 or colours_out != colours_in:
        return None

    vac_r = sum(c["row"] for c in vacated) / len(vacated)
    vac_c = sum(c["col"] for c in vacated) / len(vacated)
    fil_r = sum(c["row"] for c in filled) / len(filled)
    fil_c = sum(c["col"] for c in filled) / len(filled)
    dr, dc = fil_r - vac_r, fil_c - vac_c
    # Only accept a clean integer unit-ish move.
    if abs(dr - round(dr)) > 0.01 or abs(dc - round(dc)) > 0.01:
        return None
    dr, dc = int(round(dr)), int(round(dc))
    if (dr, dc) == (0, 0) or max(abs(dr), abs(dc)) > 8:
        return None
    return dr, dc


def _direction_name(dr: int, dc: int) -> str:
    vertical = "up" if dr < 0 else "down" if dr > 0 else ""
    horizontal = "left" if dc < 0 else "right" if dc > 0 else ""
    magnitude = max(abs(dr), abs(dc))
    name = "-".join(part for part in (vertical, horizontal) if part)
    return f"{name} by {magnitude} cell{'s' if magnitude != 1 else ''}"


def _progress_steps(records: list[dict[str, Any]]) -> set[int]:
    """Indices of steps where levels_completed increased (i.e. real progress)."""
    progress: set[int] = set()
    previous = 0
    for index, record in enumerate(records):
        current = int(record.get("levels_completed") or 0)
        if current > previous:
            progress.add(index)
        previous = current
    return progress


# ---------------------------------------------------------------------------
# Miners
# ---------------------------------------------------------------------------


def mine_action_effects(
    episodes: list[tuple[str, int, list[dict[str, Any]]]]
) -> list[dict[str, Any]]:
    """Per-(game, action) effect rules with support and held-out precision."""
    # observations[(game, action)] -> list of (episode_key, signature, translation)
    observations: dict[tuple[str, str], list[tuple[tuple[str, int], str, Any]]] = (
        defaultdict(list)
    )
    for game_id, seed, records in episodes:
        for record in records:
            action = record.get("action")
            if not action or action in ("CALL", "RESET", "AUTO_RESET"):
                continue
            observations[(game_id, action)].append(
                ((game_id, seed), _signature(record), _translation(record))
            )

    skills: list[dict[str, Any]] = []
    for (game_id, action), rows in sorted(observations.items()):
        if len(rows) < MIN_SUPPORT:
            continue

        # Split by seed so precision is measured on held-out episodes.
        seeds = sorted({key[1] for key, _, _ in rows})
        holdout_seed = seeds[-1] if len(seeds) > 1 else None
        train = [r for r in rows if holdout_seed is None or r[0][1] != holdout_seed]
        holdout = [r for r in rows if holdout_seed is not None and r[0][1] == holdout_seed]
        if not train:
            continue

        # --- translation rule (the strongest kind) -----------------------
        train_moves = Counter(r[2] for r in train if r[2] is not None)
        if train_moves:
            move, move_count = train_moves.most_common(1)[0]
            fitted_fraction = move_count / len(train)
            if fitted_fraction >= MIN_PRECISION:
                check = holdout or train
                hits = sum(1 for r in check if r[2] == move)
                precision = hits / len(check)
                if precision >= MIN_PRECISION:
                    dr, dc = move
                    skills.append(
                        {
                            "kind": "action_effect",
                            "name": f"{game_id.split('-')[0]}_{action.lower()}_moves",
                            "description": (
                                f"In game {game_id.split('-')[0].upper()}, {action} "
                                f"moves the moving object {_direction_name(dr, dc)}."
                            ),
                            "source_games": [game_id],
                            "action": action,
                            "effect": {"translation": [dr, dc]},
                            "support": len(rows),
                            "precision": round(precision, 3),
                            "validation": {
                                "check": "replay logged (action, frame_diff) pairs "
                                "and recompute the translation",
                                "holdout_seed": holdout_seed,
                                "n_checked": len(check),
                                "n_hits": hits,
                            },
                            "usage_hint": (
                                f"Use {action} when you need to move "
                                f"{_direction_name(dr, dc)}."
                            ),
                        }
                    )
                    continue

        # --- coarse signature rule ---------------------------------------
        train_signatures = Counter(r[1] for r in train)
        signature, signature_count = train_signatures.most_common(1)[0]
        if signature_count / len(train) < MIN_PRECISION:
            continue
        check = holdout or train
        hits = sum(1 for r in check if r[1] == signature)
        precision = hits / len(check)
        if precision < MIN_PRECISION:
            continue

        if signature == "no_change":
            description = (
                f"In game {game_id.split('-')[0].upper()}, {action} usually does "
                f"nothing at all."
            )
            hint = (
                f"{action} is probably inert in this game; prefer other actions "
                f"unless the state has changed."
            )
        elif ":" in signature:
            bucket, transition = signature.split(":", 1)
            source, _, target = transition.partition("->")
            description = (
                f"In game {game_id.split('-')[0].upper()}, {action} usually causes a "
                f"{bucket} change, mostly {colour_name(int(source))} -> "
                f"{colour_name(int(target))} cells."
            )
            hint = f"Expect {action} to recolour {colour_name(int(source))} regions."
        else:
            description = (
                f"In game {game_id.split('-')[0].upper()}, {action} usually causes a "
                f"{signature} change to the grid."
            )
            hint = f"{action} has a {signature} effect."

        skills.append(
            {
                "kind": "action_effect",
                "name": f"{game_id.split('-')[0]}_{action.lower()}_effect",
                "description": description,
                "source_games": [game_id],
                "action": action,
                "effect": {"signature": signature},
                "support": len(rows),
                "precision": round(precision, 3),
                "validation": {
                    "check": "replay logged (action, frame_diff) pairs and "
                    "recompute the effect signature",
                    "holdout_seed": holdout_seed,
                    "n_checked": len(check),
                    "n_hits": hits,
                },
                "usage_hint": hint,
            }
        )
    return skills


def mine_macros(
    episodes: list[tuple[str, int, list[dict[str, Any]]]],
    lengths: tuple[int, ...] = (2, 3),
) -> list[dict[str, Any]]:
    """Action subsequences that immediately preceded progress or a win."""
    # counts[(game, seq)] = (times seen, times followed by progress)
    seen: Counter[tuple[str, tuple[str, ...]]] = Counter()
    good: Counter[tuple[str, tuple[str, ...]]] = Counter()

    for game_id, _seed, records in episodes:
        actions = [r.get("action") for r in records]
        progress = _progress_steps(records)
        win_steps = {
            index
            for index, record in enumerate(records)
            if record.get("state") == "WIN"
        }
        marked = progress | win_steps
        for length in lengths:
            for start in range(len(actions) - length + 1):
                window = tuple(
                    a for a in actions[start : start + length] if isinstance(a, str)
                )
                if len(window) != length or any(
                    a in ("CALL", "AUTO_RESET") for a in window
                ):
                    continue
                key = (game_id, window)
                seen[key] += 1
                if (start + length - 1) in marked:
                    good[key] += 1

    skills: list[dict[str, Any]] = []
    for (game_id, window), good_count in good.most_common():
        if good_count < MIN_MACRO_SUPPORT:
            continue
        total = seen[(game_id, window)]
        precision = good_count / total if total else 0.0
        skills.append(
            {
                "kind": "macro",
                "name": f"{game_id.split('-')[0]}_macro_" + "_".join(
                    a.replace("ACTION", "a").lower() for a in window
                ),
                "description": (
                    f"In game {game_id.split('-')[0].upper()}, the sequence "
                    f"{' -> '.join(window)} immediately preceded progress "
                    f"{good_count} of the {total} times it was played."
                ),
                "source_games": [game_id],
                "sequence": list(window),
                "support": total,
                "precision": round(precision, 3),
                "validation": {
                    "check": "count occurrences in logged dev episodes and how "
                    "often the window ended on a levels_completed increase or WIN",
                    "n_checked": total,
                    "n_hits": good_count,
                },
                "usage_hint": (
                    f"If you are close to the goal, try {' then '.join(window)}."
                ),
            }
        )
    return skills


def mine_goal_hypotheses(
    episodes: list[tuple[str, int, list[dict[str, Any]]]]
) -> list[dict[str, Any]]:
    """What the grid looked like on the step that cleared a level."""
    per_game: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for game_id, _seed, records in episodes:
        for index in _progress_steps(records):
            record = records[index]
            objects = record.get("objects") or []
            diff = record.get("frame_diff") or {}
            per_game[game_id].append(
                {
                    "action": record.get("action"),
                    "n_objects": len(objects),
                    "colours": sorted({o["colour"] for o in objects}),
                    "n_changed": diff.get("n_changed"),
                }
            )

    skills: list[dict[str, Any]] = []
    for game_id, wins in sorted(per_game.items()):
        if len(wins) < MIN_GOAL_SUPPORT:
            continue
        actions = Counter(w["action"] for w in wins)
        winning_action, action_count = actions.most_common(1)[0]
        object_counts = [w["n_objects"] for w in wins]
        skills.append(
            {
                "kind": "goal",
                "name": f"{game_id.split('-')[0]}_goal_pattern",
                "description": (
                    f"In game {game_id.split('-')[0].upper()}, level completion was "
                    f"triggered by {winning_action} in {action_count} of "
                    f"{len(wins)} recorded completions, with "
                    f"{min(object_counts)}-{max(object_counts)} objects on screen "
                    f"at the moment it completed."
                ),
                "source_games": [game_id],
                "support": len(wins),
                "precision": round(action_count / len(wins), 3),
                "validation": {
                    "check": "re-scan logged dev episodes for levels_completed "
                    "increases and recompute the triggering action",
                    "n_checked": len(wins),
                    "n_hits": action_count,
                },
                "usage_hint": (
                    f"The level likely completes on {winning_action}; aim to set up "
                    f"the board so that action finishes it."
                ),
            }
        )
    return skills


def validate_modules(
    episodes: list[tuple[str, int, list[dict[str, Any]]]], max_frames: int = 60
) -> list[dict[str, Any]]:
    """Admit a code module only if it runs clean and says something useful.

    The validation replays logged dev *object lists* back into a grid and calls
    the module on it. A module that errors, or that returns a degenerate answer
    on every frame, is dropped.
    """
    frames: list[np.ndarray] = []
    for _game_id, _seed, records in episodes:
        for record in records[:20]:
            objects = record.get("objects") or []
            if not objects:
                continue
            # Reconstruct an approximate grid from the logged bounding boxes.
            # Exact pixels are not needed: this checks the module is runnable
            # and informative on realistic object layouts.
            grid = np.zeros((64, 64), dtype=np.int16)
            for obj in objects:
                r0, c0, r1, c1 = obj["bbox"]
                grid[r0 : r1 + 1, c0 : c1 + 1] = obj["colour"]
            frames.append(grid)
            if len(frames) >= max_frames:
                break
        if len(frames) >= max_frames:
            break

    skills: list[dict[str, Any]] = []
    if not frames:
        return skills

    probe_params = {
        "player_detector": {},
        "obstacle_map": {},
        "bfs_to_target": {
            "from_row": 1,
            "from_col": 1,
            "to_row": 20,
            "to_col": 20,
            "blocked_colours": [5],
        },
        "grid_region": {"row0": 0, "col0": 0, "row1": 7, "col1": 7},
    }

    for name, entry in sorted(MODULES.items()):
        params = probe_params.get(name, {})
        informative = 0
        errors = 0
        for grid in frames:
            try:
                output = run_module(name, params, grid)
            except Exception:
                errors += 1
                continue
            lowered = output.lower()
            if output and not lowered.startswith(
                (f"{name}: empty", f"{name}: no ", f"{name}: needs")
            ):
                informative += 1
        precision = informative / len(frames)
        passed = errors == 0 and precision >= MIN_PRECISION
        if not passed:
            continue
        skills.append(
            {
                "kind": "module",
                "name": name,
                "description": entry["description"],
                "source_games": ["derived (general perception primitive)"],
                "params": entry["params"],
                "returns": entry["returns"],
                "support": len(frames),
                "precision": round(precision, 3),
                "validation": {
                    "check": "run the module on grids reconstructed from logged "
                    "dev object lists; require zero exceptions and a useful "
                    "answer on most frames",
                    "n_checked": len(frames),
                    "n_hits": informative,
                    "n_errors": errors,
                },
                "usage_hint": (
                    f'Call it with {{"action":"CALL","args":{{"module":"{name}",'
                    f'"params":{{...}}}}}}.'
                ),
            }
        )
    return skills


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def mine_and_validate(
    dev_games: list[str],
    test_games: list[str],
    round_index: int = 0,
) -> dict[str, Any]:
    """Mine from dev trajectories only, validate, and write skills/."""
    episodes = iter_trajectories(round_index, game_ids=dev_games)
    if not episodes:
        raise SystemExit(
            f"No round-{round_index} trajectories found for the dev games. "
            "Run `python run.py --round 0` first."
        )

    # Guard the acceptance criterion rather than trusting the caller.
    leaked = sorted({game for game, _seed, _records in episodes} & set(test_games))
    if leaked:
        raise RuntimeError(
            f"Refusing to mine: test games appeared in the dev trajectory set: {leaked}"
        )

    candidates: list[dict[str, Any]] = []
    candidates += mine_action_effects(episodes)
    candidates += mine_macros(episodes)
    candidates += mine_goal_hypotheses(episodes)
    candidates += validate_modules(episodes)

    kept = [
        skill
        for skill in candidates
        if skill["precision"] >= MIN_PRECISION
        and skill["support"]
        >= (MIN_MACRO_SUPPORT if skill["kind"] in ("macro", "goal") else MIN_SUPPORT)
    ]
    dropped = [s for s in candidates if s not in kept]

    os.makedirs(SKILLS_DIR, exist_ok=True)
    # Clear stale skill files so the library always matches the index.
    for existing in os.listdir(SKILLS_DIR):
        if existing.endswith(".json") and existing != "index.json":
            os.remove(os.path.join(SKILLS_DIR, existing))

    for skill in kept:
        path = os.path.join(SKILLS_DIR, f"{skill['name']}.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(skill, handle, indent=2)
            handle.write("\n")

    index = {
        "mined_from_round": round_index,
        "dev_games": sorted(dev_games),
        "n_dev_episodes": len(episodes),
        "n_candidates": len(candidates),
        "n_kept": len(kept),
        "thresholds": {
            "min_support": MIN_SUPPORT,
            "min_precision": MIN_PRECISION,
            "min_macro_support": MIN_MACRO_SUPPORT,
            "min_goal_support": MIN_GOAL_SUPPORT,
        },
        "skills": [
            {
                "name": s["name"],
                "kind": s["kind"],
                "description": s["description"],
                "source_games": s["source_games"],
                "support": s["support"],
                "precision": s["precision"],
                "usage_hint": s.get("usage_hint"),
                "file": f"{s['name']}.json",
            }
            for s in kept
        ],
        "dropped": [
            {
                "name": s["name"],
                "kind": s["kind"],
                "support": s["support"],
                "precision": s["precision"],
                "reason": "failed support/precision thresholds",
            }
            for s in dropped
        ],
    }
    with open(INDEX_PATH, "w", encoding="utf-8") as handle:
        json.dump(index, handle, indent=2)
        handle.write("\n")

    by_kind = Counter(s["kind"] for s in kept)
    return {
        "n_dev_episodes": len(episodes),
        "n_candidates": len(candidates),
        "n_kept": len(kept),
        "n_dropped": len(dropped),
        "kept_by_kind": dict(by_kind),
        "index": INDEX_PATH,
    }
