"""Goal-progress score for vc33 Level 1 (issue #15). See GAME_NOTES.md.

The win check (`ielczunthe` in environment_files/vc33/5430563c/vc33.py)
looks at every object that must be delivered (tag `0016uciqlhjlom`) and the
target marks (tag `0010gnulkywfpz`). An object is delivered when for some
mark: (a) the object's colour (its bottom-right pixel) is one of the mark's
colours, (b) the object's coordinate across the level's gravity axis equals
the mark's (`xitrlzpbgu`: x when gravity is horizontal), and (c) the wall the
mark sits in touches the column the object stands on (`rcbyiqlbza`). The
level clears when every object is delivered. Clicking a button (tag
`0022jvmlspyigc`) moves 2 cells of height from one column to another, and the
objects standing on them move with them.

One part, read from the game state after every action:

    alignment   mean over objects of max(0, 1 - d / d at the start), where
                d = |object's cross-axis coordinate - the nearest mark's|,
                over the marks that already meet (a) and (c) (all marks if
                none does)

On Level 1, (a) and (c) hold from the start and never change, so they are
recorded in each state but carry no weight; alignment = 1 is the clear.
Level 1 starts 6 grid cells (three clicks of the right button) away.
Weight 1.0.

The episode scores its best state; a clear scores 1.0. Deterministic: it reads
the logged `game_state` records. Nothing here reaches the player or the Meta
LLM (DISCLOSE_PARTS = False).
"""

from __future__ import annotations

from typing import Any

from scorer.common import (
    ABSENT_ROLES_CLICK_GAME, display_box, score_records, span, sprite_colours, truth_roles,
)

# vc33 internals: the game's own (obfuscated) names.
OBJECT_TAG = "0016uciqlhjlom"   # objects to deliver
MARK_TAG = "0010gnulkywfpz"     # target marks
COLUMN_TAG = "0043nzrtobajqi"   # columns whose height the buttons move
WALL_TAG = "0025yfyiswdvoh"     # walls (a mark sits in one)
BUTTON_TAG = "0022jvmlspyigc"   # clickable buttons
BUDGET_UI = "heczcoeosi"        # the step bar; .current_steps left, .dmesyeowwd per level

PARTS = ("alignment",)
DEFAULT_WEIGHTS = {"alignment": 1.0}
DISCLOSE_PARTS = False


def read_state(env: Any) -> dict[str, Any]:
    """Per object: its cross-axis coordinate and, per mark, the mark's and
    whether the two fixed conditions hold."""
    game = env._game
    level = game.current_level
    marks = level.get_sprites_by_tag(MARK_TAG)
    columns = level.get_sprites_by_tag(COLUMN_TAG)
    walls = level.get_sprites_by_tag(WALL_TAG)
    objects = []
    for obj in level.get_sprites_by_tag(OBJECT_TAG):
        colour = int(obj.pixels[-1, -1])
        under = [c for c in columns if game.bcpuwqzpxw(obj, c)]
        touching = game.rcbyiqlbza(under[0]) if under else []
        targets = []
        for mark in marks:
            wall = next((w for w in walls if w.collides_with(mark)), None)
            targets.append({
                "pos": int(game.xitrlzpbgu(mark)),
                "colour_ok": bool(colour in mark.pixels),
                "contact_ok": wall is not None and wall in touching,
            })
        objects.append({"x": int(obj.x), "y": int(obj.y), "pos": int(game.xitrlzpbgu(obj)), "targets": targets})
    ui = getattr(game, BUDGET_UI, None)
    return {
        "level": int(getattr(game, "level_index", 0)),
        "objects": objects,
        "steps_left": int(ui.current_steps) if ui is not None else None,
    }


def distances(state: dict[str, Any]) -> list[int | None]:
    out = []
    for obj in state["objects"]:
        eligible = [t for t in obj["targets"] if t["colour_ok"] and t["contact_ok"]] or obj["targets"]
        out.append(min(abs(obj["pos"] - t["pos"]) for t in eligible) if eligible else None)
    return out


_START: dict[str, list[int | None]] = {}


def start_distances(game_id: str) -> list[int | None]:
    if game_id not in _START:
        from evolve.replay import make_env

        env = make_env(game_id)
        env.reset()
        _START[game_id] = distances(read_state(env))
    return _START[game_id]


def state_parts(state: dict[str, Any], at_start: list[int | None]) -> dict[str, Any] | None:
    if state.get("level", 0) != 0 or not state.get("objects"):
        return None
    now = distances(state)
    values = []
    for d, d0 in zip(now, at_start):
        if d is None:
            values.append(0.0)
        elif not d0:
            values.append(float(d == 0))
        else:
            values.append(max(0.0, 1.0 - d / d0))
    return {"alignment": sum(values) / len(values), "_distance": sum(d or 0 for d in now)}


def score_episode(records: list[dict[str, Any]], game_id: str,
                  weights: dict[str, float] | None = None) -> dict[str, Any]:
    at_start = start_distances(game_id)
    result, scored = score_records(records, lambda s: state_parts(s, at_start), weights or DEFAULT_WEIGHTS, PARTS)
    closest = min(scored, key=lambda item: item[2]["_distance"])
    farthest = max(scored, key=lambda item: item[2]["_distance"])
    result["ever"] = {
        "closest_distance": closest[2]["_distance"],
        "first_action_at_closest": closest[1]["action_index"],
        "farthest_distance": farthest[2]["_distance"],
        "states_scored": len(scored),
    }
    result["start_distance"] = sum(d or 0 for d in at_start)
    return result


def describe_failure(result: dict[str, Any]) -> str | None:
    return None  # parts are not disclosed for this game


def ground_truth(game_id: str) -> Any:
    """The fact-check's ground truth for vc33 Level 1."""
    from evolve.factcheck import GroundTruth
    from evolve.replay import make_env
    from harness.perception import grid_from_frame

    env = make_env(game_id)
    frame0 = grid_from_frame(env.reset().frame)
    game = env._game
    level = game.current_level
    scale = frame0.shape[0] // int(level.grid_size[1])
    ui = getattr(game, BUDGET_UI)
    bar = (0, 0, 0, frame0.shape[1] - 1)  # xclqwacrmx.render_interface: row 0
    objects = {
        "step_counter": [(bar, {int(v) for v in frame0[0]})],
        "goal": [(display_box(m, scale), sprite_colours(m)) for m in level.get_sprites_by_tag(MARK_TAG)],
    }
    boxes, roles = truth_roles(frame0, objects, extra={4: {"step_counter"}})  # spent steps turn the bar 4
    buttons = [display_box(b, scale) for b in level.get_sprites_by_tag(BUTTON_TAG)]
    truth = GroundTruth(
        moves={}, objects=boxes, roles=roles, switch_colours=set(),
        counts={"moves_per_life": int(ui.dmesyeowwd)},
        absent_roles=ABSENT_ROLES_CLICK_GAME,
        click_actions=frozenset({6}),
        requirements_true=frozenset({"position"}),
        requirements_false=frozenset({"collect", "avoid", "rotation"}),
        requirement_text=("the level clears when the object standing on a column is level with the target "
                          "mark (same coordinate across the gravity axis), the mark's wall touching that column"),
        rotates=False,
        has_player=False,
    )
    truth.evidence = {
        "step_counter": f"step bar at {span(bar)}, {int(ui.dmesyeowwd)} clicks per attempt",
        "goal": "target mark at " + "; ".join(span(b) for b, _c in objects["goal"]),
        "buttons": "buttons at " + "; ".join(span(b) for b in buttons),
    }
    return truth
