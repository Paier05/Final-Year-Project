"""Goal-progress score for ft09 Level 1 (issue #15). See GAME_NOTES.md.

The win check (`cgj` in environment_files/ft09/0d8bbf25/ft09.py) looks at
every pattern sprite (tag `bsT`) and the tiles (tag `Hkx`, or `NTi`) on the 8
cells around it, 4 grid cells apart. For each neighbour that holds a tile:
where the pattern's own pixel is 0, the tile's centre colour must EQUAL the
pattern's centre colour; elsewhere it must DIFFER. The level clears when every
such check holds. Clicking a tile cycles its colour through the level's
palette (`gqb`, [9, 8] on Level 1).

One part, read from the game state after every action:

    tiles   max(0, 1 - checks failing / checks failing at the start)

1 when no check fails (that state is the clear), 0 at the start and whenever
as many checks fail as at the start or more. Level 1 starts with 4 of its 8
checks failing, so each right click is worth 0.25 and each wrong one costs
0.25. Weight 1.0: the win check has no other condition.

The episode scores its best state; a clear scores 1.0. Deterministic: it reads
the logged `game_state` records. Nothing here reaches the player or the Meta
LLM (DISCLOSE_PARTS = False).
"""

from __future__ import annotations

from typing import Any

from scorer.common import (
    ABSENT_ROLES_CLICK_GAME, display_box, score_records, span, sprite_colours, truth_roles,
)

# ft09 internals: the game's own (obfuscated) names.
PATTERN_TAG = "bsT"            # pattern sprites the win check reads
TILE_TAGS = ("Hkx", "NTi")     # clickable tiles
NEIGHBOUR_STEP = 4             # grid cells between a pattern and its neighbours
BUDGET_UI = "lpw"              # the click-budget bar; .dzy = clicks left, .oro = per level

PARTS = ("tiles",)
DEFAULT_WEIGHTS = {"tiles": 1.0}
DISCLOSE_PARTS = False


def _tile_at(level: Any, x: int, y: int) -> Any:
    for tag in TILE_TAGS:
        sprite = level.get_sprite_at(x, y, tag)
        if sprite:
            return sprite
    return None


def read_state(env: Any) -> dict[str, Any]:
    """Every check the win test makes, with the colours it compares now."""
    game = env._game
    level = game.current_level
    checks = []
    for pattern in level.get_sprites_by_tag(PATTERN_TAG):
        centre = int(pattern.pixels[1][1])
        for j in range(3):
            for i in range(3):
                if (i, j) == (1, 1):
                    continue
                x = int(pattern.x) + (i - 1) * NEIGHBOUR_STEP
                y = int(pattern.y) + (j - 1) * NEIGHBOUR_STEP
                tile = _tile_at(level, x, y)
                if tile is None:
                    continue
                # [tile x, tile y, must equal the centre, tile colour, centre colour]
                checks.append([x, y, int(pattern.pixels[j][i]) == 0, int(tile.pixels[1][1]), centre])
    ui = getattr(game, BUDGET_UI, None)
    return {
        "level": int(getattr(game, "level_index", 0)),
        "checks": checks,
        "clicks_left": int(ui.dzy) if ui is not None else None,
    }


def failing(state: dict[str, Any]) -> int:
    return sum(1 for _x, _y, same, tile, centre in state["checks"] if (tile == centre) != same)


_START: dict[str, int] = {}


def start_failing(game_id: str) -> int:
    if game_id not in _START:
        from evolve.replay import make_env

        env = make_env(game_id)
        env.reset()
        _START[game_id] = failing(read_state(env))
    return _START[game_id]


def state_parts(state: dict[str, Any], at_start: int) -> dict[str, Any] | None:
    if state.get("level", 0) != 0 or not state.get("checks"):
        return None
    wrong = failing(state)
    return {"tiles": max(0.0, 1.0 - wrong / at_start) if at_start else float(wrong == 0),
            "_checks_failing": wrong, "_checks": len(state["checks"])}


def score_episode(records: list[dict[str, Any]], game_id: str,
                  weights: dict[str, float] | None = None) -> dict[str, Any]:
    at_start = start_failing(game_id)
    result, scored = score_records(records, lambda s: state_parts(s, at_start), weights or DEFAULT_WEIGHTS, PARTS)
    fewest = min(scored, key=lambda item: item[2]["_checks_failing"])
    result["ever"] = {
        "fewest_checks_failing": fewest[2]["_checks_failing"],
        "first_action_at_fewest": fewest[1]["action_index"],
        "states_scored": len(scored),
    }
    result["start_checks_failing"] = at_start
    return result


def describe_failure(result: dict[str, Any]) -> str | None:
    return None  # parts are not disclosed for this game


def ground_truth(game_id: str) -> Any:
    """The fact-check's ground truth for ft09 Level 1."""
    from evolve.factcheck import GroundTruth
    from evolve.replay import make_env
    from harness.perception import grid_from_frame

    env = make_env(game_id)
    frame0 = grid_from_frame(env.reset().frame)
    game = env._game
    scale = frame0.shape[0] // int(game.current_level.grid_size[1])
    ui = getattr(game, BUDGET_UI)
    bar = (frame0.shape[0] - 1, 0, frame0.shape[0] - 1, frame0.shape[1] - 1)  # sve.render_interface: row 63
    objects = {"step_counter": [(bar, {int(v) for v in frame0[-1]})]}
    boxes, roles = truth_roles(frame0, objects, extra={11: {"step_counter"}})  # spent clicks turn the bar 11
    patterns = [display_box(s, scale) for s in game.current_level.get_sprites_by_tag(PATTERN_TAG)]
    tiles = [s for tag in TILE_TAGS for s in game.current_level.get_sprites_by_tag(tag)]
    truth = GroundTruth(
        moves={}, objects=boxes, roles=roles, switch_colours=set(),
        counts={"moves_per_life": int(ui.oro)},
        absent_roles=ABSENT_ROLES_CLICK_GAME,
        click_actions=frozenset({6}),
        requirements_true=frozenset({"colour"}),
        requirements_false=frozenset({"collect", "avoid", "rotation", "position"}),
        requirement_text=("the level clears when every tile next to the pattern has the colour the pattern "
                          "asks for (equal to its centre where its pixel is 0, different elsewhere)"),
        rotates=False,
        has_player=False,
    )
    truth.evidence = {
        "step_counter": f"click budget bar at {span(bar)}, {int(ui.oro)} tile clicks per attempt",
        "pattern": "pattern at " + "; ".join(span(b) for b in patterns),
        "tiles": f"{len(tiles)} clickable tiles, colours {sorted({c for t in tiles for c in sprite_colours(t)})}",
    }
    return truth
