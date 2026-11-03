"""Goal-progress score for ls20 Level 1 (issue #12, change 1).

#9's progress term measured distance to the rotation switch, which is not the
goal (REPORT-9-architecture.md §4.1). This score is computed from the game's
own state, read after every action, and combines every condition the game
checks before it clears Level 1 (`bejndxqqzf` + `pbznecvnfr` in
environment_files/ls20/9607627b/ls20.py): the player sprite stands on the goal
sprite AND its rotation, shape and colour indices equal the goal's.

Parts of one state, each in [0, 1]:

    position  max(0, 1 - moves_to_goal / moves_to_goal_from_start)
              moves = shortest path on the maze (5-cell moves, walls only)
    rotation  1 if the player's rotation index equals the goal's, else 0
    shape     1 if the shape index matches, else 0
    colour    1 if the colour index matches, else 0

    state score = sum(weight[p] * part[p])   (weights in config_evolve.yaml)

An episode scores its best state, so it is rewarded for holding the right
rotation *and* being near the goal at the same time, which #9's players never
did. A clear scores 1.0. No non-clear state can reach 1.0: on the goal square
with every attribute matching is the clear.

The score is deterministic: it reads logged `game_state` records (written by
the action loop) or, for trajectories that have none (#9's), rebuilds the
states by replaying the logged actions (ls20 is deterministic). No model is
involved. The player never sees any of this: `game_state` is written to the
trajectory, not to the sandbox API.
"""

from __future__ import annotations

from collections import deque
from typing import Any

# ls20 internals: the game's own (obfuscated) attribute names.
PLAYER = "gudziatsk"          # player sprite
GOALS = "plrpelhym"           # goal sprites (one on Level 1)
ROTATION = "cklxociuu"        # player rotation index (0..3)
SHAPE = "fwckfzsyc"           # player shape index
COLOUR = "hiaauhahz"          # player colour index
GOAL_ROTATION = "ehwheiwsk"   # required rotation index per goal
GOAL_SHAPE = "ldxlnycps"      # required shape index per goal
GOAL_COLOUR = "yjdexjsoa"     # required colour index per goal
GOAL_DONE = "lvrnuajbl"       # per goal: already reached
LIVES = "aqygnziho"           # lives left (3 at the start)
WALL_TAG = "ihdgageizm"       # wall sprites
STEP_UI = "_step_counter_ui"  # the lime move counter; .current_steps

PARTS = ("position", "rotation", "shape", "colour")
DEFAULT_WEIGHTS = {"position": 0.4, "rotation": 0.4, "shape": 0.1, "colour": 0.1}


def read_state(env: Any) -> dict[str, Any]:
    """The goal-relevant game state, right now. Re-read on every call: a reset
    re-clones the level's sprites."""
    game = env._game
    player = getattr(game, PLAYER)
    done = list(getattr(game, GOAL_DONE, []) or [])
    goals = []
    for i, sprite in enumerate(getattr(game, GOALS) or []):
        goals.append({
            "x": int(sprite.x), "y": int(sprite.y),
            "rotation": int(getattr(game, GOAL_ROTATION)[i]),
            "shape": int(getattr(game, GOAL_SHAPE)[i]),
            "colour": int(getattr(game, GOAL_COLOUR)[i]),
            "done": bool(done[i]) if i < len(done) else False,
        })
    step_ui = getattr(game, STEP_UI, None)
    return {
        "level": int(getattr(game, "level_index", 0)),
        "x": int(player.x), "y": int(player.y),
        "rotation": int(getattr(game, ROTATION)),
        "shape": int(getattr(game, SHAPE)),
        "colour": int(getattr(game, COLOUR)),
        "goals": goals,
        "lives": int(getattr(game, LIVES, 0)),
        "moves_left": int(getattr(step_ui, "current_steps", -1)) if step_ui is not None else None,
    }


class Maze:
    """Level 1's walkable squares and the shortest-path distance to the goal."""

    def __init__(self, walls: set[tuple[int, int]], step: int, start: tuple[int, int],
                 goal: tuple[int, int], size: int = 64) -> None:
        self.walls, self.step, self.start, self.goal, self.size = walls, step, start, goal, size
        self.to_goal = self.distances(goal)
        self.start_moves = self.to_goal.get(start)
        if not self.start_moves:
            raise ValueError("the goal is not reachable from the start")

    @classmethod
    def from_env(cls, env: Any) -> "Maze":
        """Build from a fresh env at the start of Level 1."""
        game = env._game
        player = getattr(game, PLAYER)
        goal = getattr(game, GOALS)[0]
        walls = {(int(w.x), int(w.y)) for w in game.current_level.get_sprites_by_tag(WALL_TAG)}
        return cls(walls, int(player.width), (int(player.x), int(player.y)), (int(goal.x), int(goal.y)))

    def distances(self, source: tuple[int, int]) -> dict[tuple[int, int], int]:
        step, limit = self.step, self.size - self.step
        dist = {source: 0}
        queue = deque([source])
        while queue:
            x, y = queue.popleft()
            for dx, dy in ((0, -step), (0, step), (-step, 0), (step, 0)):
                nxt = (x + dx, y + dy)
                if nxt in dist or nxt in self.walls or not (0 <= nxt[0] <= limit and 0 <= nxt[1] <= limit):
                    continue
                dist[nxt] = dist[(x, y)] + 1
                queue.append(nxt)
        return dist

    def moves_to_goal(self, x: int, y: int) -> int | None:
        return self.to_goal.get((x, y))


def state_parts(state: dict[str, Any], maze: Maze) -> dict[str, float] | None:
    """Parts of one state against its nearest unfinished goal, or None if the
    state is not on Level 1 (after a clear the game shows Level 2)."""
    if state.get("level", 0) != 0:
        return None
    goals = [g for g in state["goals"] if not g.get("done")]
    if not goals:
        return None
    goal = goals[0]  # Level 1 has exactly one goal
    moves = maze.moves_to_goal(state["x"], state["y"])
    return {
        "position": 0.0 if moves is None else max(0.0, 1.0 - moves / maze.start_moves),
        "rotation": float(state["rotation"] == goal["rotation"]),
        "shape": float(state["shape"] == goal["shape"]),
        "colour": float(state["colour"] == goal["colour"]),
        "_moves": moves,
    }


def weighted(parts: dict[str, float], weights: dict[str, float]) -> float:
    return sum(weights[p] * parts[p] for p in PARTS)


# ---------------------------------------------------------------------------
# States of one episode
# ---------------------------------------------------------------------------


def states_from_records(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    """(states in order, cleared) from a trajectory that logged game_state.

    State 0 is the start; state k is the state after the k-th action. A
    harness auto-reset after a game over adds the reset state right after.
    """
    header = next((r for r in records if r.get("type") == "episode_start"), {})
    if "start_state" not in header:
        raise KeyError("trajectory has no logged game_state (use states_by_replay)")
    states = [dict(header["start_state"], action_index=0)]
    cleared = False
    for record in records:
        if record.get("type") != "tool_call":
            continue
        for item in record.get("actions") or []:
            states.append(dict(item["game_state"], action_index=item["action_index"]))
            if item.get("auto_reset_state"):
                states.append(dict(item["auto_reset_state"], action_index=item["action_index"]))
            if int(item.get("levels_completed") or 0) >= 1:
                cleared = True
    return states, cleared


def states_by_replay(records: list[dict[str, Any]], game_id: str) -> tuple[list[dict[str, Any]], bool]:
    """Same as states_from_records, rebuilt by replaying the logged actions
    through the same EpisodeAPI the run used (resets and auto-resets match)."""
    from evolve.action_loop import EpisodeAPI
    from evolve.replay import make_env
    from evolve.sandbox import TurnOver

    env = make_env(game_id)
    api = EpisodeAPI(env, actions_per_turn=10**9, max_actions=10**9, max_resets=10**9, probe=read_state)
    states = [dict(api.start_state, action_index=0)]
    actions = [a for r in records if r.get("type") == "tool_call" for a in (r.get("actions") or [])]
    for item in actions:
        api.begin_turn(0)
        action_id = 0 if item["action"] == "RESET" else int(item["action"].replace("ACTION", ""))
        args = item.get("args") or {}
        try:
            api.action(action_id, **({"x": args["x"], "y": args["y"]} if args else {}))
        except TurnOver:
            pass
        record = api.turn_actions[-1]
        states.append(dict(record["game_state"], action_index=record["action_index"]))
        if record.get("auto_reset_state"):
            states.append(dict(record["auto_reset_state"], action_index=record["action_index"]))
        if api.solved:
            break
    return states, api.solved


# ---------------------------------------------------------------------------
# Episode score
# ---------------------------------------------------------------------------


def score_states(
    states: list[dict[str, Any]], cleared: bool, maze: Maze, weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    weights = weights or DEFAULT_WEIGHTS
    scored = []
    for state in states:
        parts = state_parts(state, maze)
        if parts is not None:
            scored.append((weighted(parts, weights), state, parts))
    if not scored:
        raise ValueError("no Level-1 state to score")
    best_value, best_state, best_parts = max(scored, key=lambda item: item[0])  # first max wins
    attrs_ok = [(s, p) for _v, s, p in scored if p["rotation"] and p["shape"] and p["colour"]]
    rotated = [s for _v, s, p in scored if p["rotation"]]
    moves_any = [p["_moves"] for _v, _s, p in scored if p["_moves"] is not None]
    moves_ok = [p["_moves"] for _s, p in attrs_ok if p["_moves"] is not None]
    if cleared:
        score, parts = 1.0, {p: 1.0 for p in PARTS}
    else:
        score, parts = best_value, {p: best_parts[p] for p in PARTS}
    return {
        "score": round(score, 4),
        "cleared": cleared,
        "parts": {p: round(v, 4) for p, v in parts.items()},
        "contributions": {p: round(weights[p] * parts[p], 4) for p in PARTS},
        "failing_parts": [] if cleared else [p for p in PARTS if parts[p] < 1.0],
        "best_state": {
            "action_index": best_state["action_index"],
            "moves_to_goal": 0 if cleared else best_parts["_moves"],
        },
        "ever": {
            "rotation_matched": bool(rotated),
            "first_rotation_match_action": rotated[0]["action_index"] if rotated else None,
            "states_with_all_attributes_matched": len(attrs_ok),
            "closest_moves_to_goal": min(moves_any) if moves_any else None,
            "closest_moves_to_goal_attributes_matched": min(moves_ok) if moves_ok else None,
        },
        "start_moves_to_goal": maze.start_moves,
        "n_states": len(states),
    }


_MAZE: Maze | None = None


def level1_maze(game_id: str) -> Maze:
    global _MAZE
    if _MAZE is None:
        from evolve.replay import make_env

        _MAZE = Maze.from_env(make_env(game_id))
    return _MAZE


def score_episode(
    records: list[dict[str, Any]], game_id: str, weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Goal-progress score of one trajectory: from its logged states if it has
    them, otherwise by replay."""
    maze = level1_maze(game_id)
    try:
        states, cleared = states_from_records(records)
        source = "logged game_state"
    except KeyError:
        states, cleared = states_by_replay(records, game_id)
        source = "replay of logged actions"
    result = score_states(states, cleared, maze, weights)
    result["state_source"] = source
    return result


def describe_failure(result: dict[str, Any]) -> str:
    """One line for Analyze: which goal parts failed at the episode's best state."""
    if result["cleared"]:
        return "cleared Level 1"
    best = result["best_state"]
    parts = result["parts"]
    bits = [f"best state after action {best['action_index']}: {best['moves_to_goal']} moves from the goal square"]
    bits += [f"{p} {'matched' if parts[p] else 'WRONG'}" for p in ("rotation", "shape", "colour")]
    ever = result["ever"]
    if not ever["rotation_matched"]:
        bits.append("rotation never matched in the episode")
    elif ever["closest_moves_to_goal_attributes_matched"] is not None:
        bits.append(f"closest while rotation/shape/colour all matched: "
                    f"{ever['closest_moves_to_goal_attributes_matched']} moves")
    return "; ".join(bits)
