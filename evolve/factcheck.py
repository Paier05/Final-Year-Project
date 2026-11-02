"""Stage 3 · Validate, knowledge fact-check (issue #12, change 2).

#9's Validate checked mechanics only, so false game facts written by the Meta
LLM ("the player is the lime bar", "moves 1 cell per action") went straight
into the harness and were inherited by every later version
(REPORT-9-architecture.md §4.3-4.4). This module checks what an edit *says*
about the game against the game itself.

Two steps, kept apart on purpose:

1. **Extract** (one model call per Validate attempt): the meta model turns each
   edit's text -- a prompt, a step, or a skill's code and docstring -- into
   claims from a fixed vocabulary (CLAIM_KINDS). It is told not to judge them.
2. **Check** (code, no model): each claim is tested against ground truth from
   the env, probed by replaying actions from the start of Level 1 (what each
   action does to the player sprite, where the goal, switch, counter and lives
   are, what each colour is), plus the logged game states of the parent's
   episodes, plus -- for claims about what a skill returns -- running the
   skill on replayed recorded states and comparing with the real positions.

Each claim is labelled true / false / unverifiable. An edit with a false claim
is dropped; an edit with unverifiable claims is kept and flagged in the
CHANGELOG. The Meta LLM's retry feedback says only that a claim is false (the
user's choice, 2026-11-02): the evidence, which states the true value, goes to
validation.json, archive.json and the CHANGELOG, not back to the Meta LLM.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from harness.perception import COLOUR_NAMES, connected_components

CLAIM_KINDS = ("move", "colour_role", "location", "rotation_cause", "goal_requirement",
               "count", "skill_output", "other")
ROLES = ("player", "goal", "wall", "floor", "rotation_switch", "step_counter", "lives",
         "collectible", "hazard", "trail", "enemy", "other")
# Roles nothing on ls20 Level 1 plays: a claim that some colour is one is false.
ABSENT_ROLES = ("collectible", "hazard", "trail", "enemy")
GOAL_CONDITIONS = ("position", "rotation", "shape", "colour")
DIRECTIONS = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}
TOLERANCE = 2  # cells of slack on a stated location


# ---------------------------------------------------------------------------
# Ground truth, probed from the env
# ---------------------------------------------------------------------------


@dataclass
class GroundTruth:
    moves: dict[int, tuple[int, int] | None]          # action -> (drow, dcol) in grid cells
    objects: dict[str, list[tuple[int, int, int, int]]]  # name -> bboxes (r0, c0, r1, c1)
    roles: dict[str, set[str]]                        # colour name -> roles it plays
    switch_colours: set[str]
    counts: dict[str, int]
    evidence: dict[str, str] = field(default_factory=dict)

    def role_text(self, colour: str) -> str:
        roles = sorted(self.roles.get(colour, set()))
        return f"{colour} is {', '.join(roles) if roles else 'not on screen'}"


def _bbox(x: int, y: int, w: int, h: int) -> tuple[int, int, int, int]:
    return (y, x, y + h - 1, x + w - 1)


def _colours_in(grid: np.ndarray, box: tuple[int, int, int, int]) -> set[str]:
    r0, c0, r1, c1 = box
    return {COLOUR_NAMES[int(v)] for v in np.unique(grid[r0:r1 + 1, c0:c1 + 1])}


def _probe_moves(game_id: str) -> dict[int, tuple[int, int] | None]:
    """What each action does to the player sprite: try it from the start and,
    if it is blocked there, from the states one or two other moves away."""
    from evolve.action_loop import EpisodeAPI
    from evolve.goal_score import read_state
    from evolve.replay import make_env

    def run(prefix: list[int], action: int) -> tuple[int, int] | None:
        env = make_env(game_id)
        api = EpisodeAPI(env, 10**9, 10**9, 10**9, probe=read_state)
        for a in prefix:
            api.begin_turn(0)
            api.action(a)
        before = read_state(env)
        api.begin_turn(0)
        api.action(action)
        after = read_state(env)
        d = (after["y"] - before["y"], after["x"] - before["x"])
        return None if d == (0, 0) else d

    env = make_env(game_id)
    available = [a for a in (env.reset().available_actions or []) if a != 0]
    out: dict[int, tuple[int, int] | None] = {}
    for action in available:
        found = None
        for prefix in [[]] + [[a] for a in available] + [[a, b] for a in available for b in available]:
            found = run(prefix, action)
            if found:
                break
        out[int(action)] = found
    return out


_TRUTH: dict[str, GroundTruth] = {}


def ground_truth(game_id: str) -> GroundTruth:
    """Probe ls20 Level 1 once per process."""
    if game_id in _TRUTH:
        return _TRUTH[game_id]
    from evolve.action_loop import EpisodeAPI
    from evolve.goal_score import GOALS, LIVES, PLAYER, WALL_TAG, read_state, level1_maze
    from evolve.replay import make_env

    env = make_env(game_id)
    api = EpisodeAPI(env, 10**9, 10**9, 10**9, probe=read_state)
    game = env._game
    frame0 = api.grid.copy()
    tags = lambda tag: game.current_level.get_sprites_by_tag(tag)  # noqa: E731

    player = getattr(game, PLAYER)
    objects: dict[str, list[tuple[int, int, int, int]]] = defaultdict(list)
    objects["player"].append(_bbox(player.x, player.y, player.width, player.height))
    for sprite in getattr(game, GOALS):
        objects["goal"].append(_bbox(sprite.x, sprite.y, sprite.width, sprite.height))
    for tag in ("vjotnebuqo", "hoswmpiqkw"):  # the goal's 7x7 frame
        for sprite in tags(tag):
            objects["goal_frame"].append(_bbox(sprite.x, sprite.y, sprite.width, sprite.height))
    for sprite in tags("rhsxkxzdjz"):
        objects["rotation_switch"].append(_bbox(sprite.x, sprite.y, sprite.width, sprite.height))
    for sprite in tags(WALL_TAG):
        objects["wall"].append(_bbox(sprite.x, sprite.y, sprite.width, sprite.height))
    for sprite in tags("eqatonpohu"):  # HUD box showing the player's shape
        objects["hud"].append(_bbox(sprite.x, sprite.y, sprite.width, sprite.height))

    # Floor: the colour of reachable maze squares that hold nothing else.
    maze = level1_maze(game_id)
    occupied = {(b[1], b[0]) for name in ("player", "goal", "rotation_switch") for b in objects[name]}
    floor = Counter(int(frame0[y + 2, x + 2]) for (x, y) in maze.distances(maze.start) if (x, y) not in occupied)
    floor_colour = COLOUR_NAMES[floor.most_common(1)[0][0]]

    # Step counter: the cells one move changes outside the player sprite.
    # Lives: keep moving until a life is lost and see which cells change,
    # other than the player and the counter refilling.
    moves = _probe_moves(game_id)
    probe_env = make_env(game_id)
    probe_api = EpisodeAPI(probe_env, 10**9, 10**9, 10**9, probe=read_state)
    lives0 = int(getattr(probe_env._game, LIVES))
    budget = int(probe_api.start_state["moves_left"])
    mover = next(a for a in sorted(moves) if moves[a])
    back = next((a for a in sorted(moves) if moves[a] and moves[mover]
                 and moves[a] == (-moves[mover][0], -moves[mover][1])), mover)

    def player_box(state: dict[str, Any]) -> tuple[int, int, int, int]:
        return _bbox(state["x"], state["y"], player.width, player.height)

    def changed_outside(before: np.ndarray, after: np.ndarray, boxes: list) -> set[tuple[int, int]]:
        return {(int(r), int(c)) for r, c in np.argwhere(before != after)
                if not any(b[0] <= r <= b[2] and b[1] <= c <= b[3] for b in boxes)}

    counter_cells: set[tuple[int, int]] = set()
    lives_cells: set[tuple[int, int]] = set()
    state = probe_api.start_state
    for i in range(budget + 2):
        before, state_before = probe_api.grid.copy(), state
        probe_api.begin_turn(0)
        probe_api.action(mover if i % 2 == 0 else back)
        state = probe_api.turn_actions[-1]["game_state"]
        boxes = [player_box(state_before), player_box(state)]
        if i == 0:
            counter_cells = changed_outside(before, probe_api.grid, boxes)
        if state["lives"] < lives0:
            counter_idx = int(frame0[next(iter(counter_cells))]) if counter_cells else None
            boxes.append(player_box(probe_api.start_state))
            lives_cells = {rc for rc in changed_outside(before, probe_api.grid, boxes)
                           if int(before[rc]) != counter_idx and COLOUR_NAMES[int(before[rc])] != floor_colour}
            break
    components = connected_components(frame0)
    for name, cells in (("step_counter", counter_cells), ("lives", lives_cells)):
        if not cells:
            continue
        colour = int(frame0[next(iter(cells))])
        for comp in components:
            r0, c0, r1, c1 = comp["bbox"]
            if comp["colour"] == colour and any(r0 <= r <= r1 and c0 <= c <= c1 for r, c in cells):
                objects[name].append((r0, c0, r1, c1))
        if name == "lives":  # every block of the lives colour on the counter's row band
            band = {r for b in objects["lives"] for r in (b[0], b[2])}
            for comp in components:
                r0, c0, r1, c1 = comp["bbox"]
                if comp["colour"] == colour and r0 in band and (r0, c0, r1, c1) not in objects["lives"]:
                    objects["lives"].append((r0, c0, r1, c1))

    roles: dict[str, set[str]] = defaultdict(set)
    explained = np.zeros(frame0.shape, dtype=bool)
    # Walls are drawn under the HUD in places, so a wall's colour is the most
    # common colour over all wall squares, not every colour inside them.
    wall_pixels = Counter(int(v) for box in objects["wall"]
                          for v in frame0[box[0]:box[2] + 1, box[1]:box[3] + 1].ravel())
    roles[COLOUR_NAMES[wall_pixels.most_common(1)[0][0]]].add("wall")
    for name, role in (("player", "player"), ("goal", "goal"), ("goal_frame", "goal"),
                       ("rotation_switch", "rotation_switch"), ("step_counter", "step_counter"),
                       ("lives", "lives"), ("hud", "ui"), ("wall", None)):
        for box in objects[name]:
            colours = _colours_in(frame0, box)
            if name == "rotation_switch":
                colours -= {floor_colour}
            if name in ("step_counter", "lives"):
                colours = {COLOUR_NAMES[int(frame0[box[0], box[1]])]}
            for colour in colours if role else ():
                roles[colour].add(role)
            r0, c0, r1, c1 = box
            explained[r0:r1 + 1, c0:c1 + 1] = True
    roles[floor_colour].add("floor")
    for (x, y) in maze.distances(maze.start):
        explained[y:y + maze.step, x:x + maze.step] = True
    # A colour that also appears where no known object is (the border, the
    # HUD) gets "ui": a claim giving it a role it lacks is then unverifiable,
    # not false. The background colour is the walls' colour and is left out.
    background = COLOUR_NAMES[int(np.bincount(frame0.ravel()).argmax())]
    for colour in {COLOUR_NAMES[int(v)] for v in np.unique(frame0[~explained])} - {background}:
        roles[colour].add("ui")
    switch_colours = {c for c, r in roles.items() if "rotation_switch" in r}

    counts = {"lives": lives0, "moves_per_life": int(budget)}
    truth = GroundTruth(moves=moves, objects=dict(objects), roles=dict(roles),
                        switch_colours=switch_colours, counts=counts)
    truth.evidence = {
        "player": f"player sprite at rows {_span(objects['player'][0])} ({', '.join(sorted(_colours_in(frame0, objects['player'][0])))})",
        "goal": f"goal at rows {_span(objects['goal'][0])}",
        "rotation_switch": "rotation switch at " + "; ".join(f"rows {_span(b)}" for b in objects["rotation_switch"]),
        "step_counter": "step counter at " + "; ".join(f"rows {_span(b)}" for b in objects["step_counter"]),
        "lives": f"{lives0} lives, shown at " + "; ".join(f"rows {_span(b)}" for b in objects["lives"]),
    }
    _TRUTH[game_id] = truth
    return truth


def _span(box: tuple[int, int, int, int]) -> str:
    r0, c0, r1, c1 = box
    return f"{r0}-{r1}, cols {c0}-{c1}"


def observed_moves(episodes: list[dict[str, Any]]) -> dict[str, Counter]:
    """Per action, the player displacements in the parent's logged states."""
    out: dict[str, Counter] = defaultdict(Counter)
    for episode in episodes:
        records = episode["records"]
        header = next((r for r in records if r.get("type") == "episode_start"), {})
        prev = header.get("start_state")
        if prev is None:
            continue
        for record in records:
            for item in record.get("actions") or [] if record.get("type") == "tool_call" else []:
                state = item.get("game_state")
                if state is None:
                    break
                if prev.get("level") == state.get("level") == 0 and prev.get("lives") == state.get("lives"):
                    out[item["action"]][(state["y"] - prev["y"], state["x"] - prev["x"])] += 1
                prev = item.get("auto_reset_state") or state
    return out


# ---------------------------------------------------------------------------
# Extraction (the only model call)
# ---------------------------------------------------------------------------

EXTRACT_SYSTEM = """\
You extract checkable factual claims about a video game from text that will be
given to a game-playing model. You do NOT judge whether the claims are true: a
program checks each one against the game afterwards.

A factual claim states a fact about the game: what an action does, which
colour or object is what, where something is, what completing the level
requires, how many of something there are, what a function returns. NOT
claims (skip them): advice, plans, strategies, instructions to the player
("explore first", "plan your route"), and statements explicitly marked as
guesses ("may", "might", "possibly", "hypothesis", "unverified").
For code (skills): extract what the code assumes about the game (for example,
it searches for lime cells to find the player -> the player is lime) and what
its docstring says it returns.

Coordinates are (row, col) on the 64x64 observation grid, row 0 at the top.
"cells" means grid cells. Colour names: {colours}.

Reply with one JSON object and nothing else. The fields of a kind sit directly
in the claim object, next to "kind" -- not nested. For example:
{{"claims": [{{"edit": "r1-e2", "quote": "ACTION1 moves the player up 5 cells",
              "kind": "move", "action": 1, "direction": "up", "cells": 5, "unit": "cells"}},
             {{"edit": "r1-e3", "quote": "if o['colour'] == 11: return o",
              "kind": "colour_role", "colour": "lime", "role": "player"}}]}}
Colours are always names, never indices (colour 11 is "lime").

Kinds and their fields (null for anything the text does not say):
- "move": an action moves the player.
  {{"action": 1..7 or null (null = every movement action), "direction": "up"|"down"|"left"|"right"|"none"|null,
   "cells": integer or null, "unit": "cells"|"unclear"}}   ("none" = the action does nothing)
- "colour_role": a colour is a kind of thing.
  {{"colour": <colour name>, "role": "player"|"goal"|"wall"|"floor"|"rotation_switch"|"step_counter"|"lives"|"collectible"|"hazard"|"trail"|"enemy"|"other"}}
- "location": where something is. Use the object the text names; "collectible" for items the
  text says are to be collected, "other" for anything else.
  {{"object": "player"|"goal"|"rotation_switch"|"step_counter"|"lives"|"collectible"|"other",
   "rows": [lo, hi] or null, "cols": [lo, hi] or null, "region": e.g. "top", "bottom-left", "centre", or null}}
- "rotation_cause": what changes the player's rotation / orientation.
  {{"cause": "action"|"touch", "action": integer or null, "rows": [lo, hi] or null, "cols": [lo, hi] or null,
   "colour": <colour name> or null}}
- "goal_requirement": what completing the level requires.
  {{"requires": [any of "position" (reach / stand on the goal), "rotation", "shape", "colour",
   "collect" (collect items), "avoid", "other"]}}
- "count": {{"what": "lives"|"moves_per_life", "value": integer}}
- "skill_output": a skill returns a location. {{"skill": <name>, "returns": "player_position"|"goal_position"|"rotation_switch_position"}}
- "other": any other factual claim. {{}}

One claim per fact: a sentence with two facts gives two claims. An edit with
no factual claims gives none."""


def extract_messages(items: list[dict[str, Any]]) -> list[dict[str, str]]:
    colours = ", ".join(sorted(COLOUR_NAMES.values()))
    blocks = []
    for item in items:
        blocks.append(
            f"=== edit {item['id']}: {item['op']} {item['target']} {item.get('name') or item.get('index') or ''} ===\n"
            f"{item['content']}"
        )
    return [
        {"role": "system", "content": EXTRACT_SYSTEM.format(colours=colours)},
        {"role": "user", "content": "\n\n".join(blocks) + "\n\nExtract the claims now. JSON only."},
    ]


def parse_claims(text: str) -> list[dict[str, Any]]:
    cleaned = re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL).strip()
    for candidate in re.findall(r"```(?:json)?\s*\n(.*?)```", cleaned, flags=re.DOTALL) + [cleaned]:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start < 0 or end <= start:
            continue
        try:
            payload = json.loads(candidate[start:end + 1])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and isinstance(payload.get("claims"), list):
            return [c for c in payload["claims"] if isinstance(c, dict)]
    raise ValueError("no JSON object with a 'claims' list in the extractor reply")


def extract_claims(items: list[dict[str, Any]], client: Any, max_tokens: int) -> dict[str, Any]:
    """{edit id: [claims]} plus the call's cost, from one model call."""
    out: dict[str, Any] = {"by_edit": {i["id"]: [] for i in items}, "tokens_in": 0, "tokens_out": 0,
                           "calls": 0, "error": None}
    if not items:
        return out
    messages = extract_messages(items)
    for _attempt in range(2):
        response = client.complete(messages, max_tokens=max_tokens)
        out["calls"] += 1
        out["tokens_in"] += response.tokens_in
        out["tokens_out"] += response.tokens_out
        try:
            claims = parse_claims(response.text)
        except ValueError as error:
            out["error"] = str(error)
            continue
        out["error"] = None
        for claim in claims:
            edit_id = str(claim.get("edit", ""))
            if edit_id in out["by_edit"]:
                out["by_edit"][edit_id].append(claim)
        break
    return out


# ---------------------------------------------------------------------------
# Checking (no model)
# ---------------------------------------------------------------------------


def _range(value: Any) -> tuple[int, int] | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value), int(value)
    if isinstance(value, (list, tuple)) and value and all(isinstance(v, (int, float)) for v in value):
        return int(min(value)), int(max(value))
    return None


def _overlaps(rows: tuple[int, int] | None, cols: tuple[int, int] | None,
              box: tuple[int, int, int, int], tol: int = TOLERANCE) -> bool:
    r0, c0, r1, c1 = box
    ok_r = rows is None or (rows[0] <= r1 + tol and rows[1] >= r0 - tol)
    ok_c = cols is None or (cols[0] <= c1 + tol and cols[1] >= c0 - tol)
    return ok_r and ok_c


def _region_of(box: tuple[int, int, int, int]) -> tuple[str, str, float, float]:
    r = (box[0] + box[2]) / 2
    c = (box[1] + box[3]) / 2
    vert = "top" if r < 21.33 else "bottom" if r >= 42.67 else "middle"
    horiz = "left" if c < 21.33 else "right" if c >= 42.67 else "centre"
    # distance to the nearest band boundary, per axis
    return vert, horiz, min(abs(r - 21.33), abs(r - 42.67)), min(abs(c - 21.33), abs(c - 42.67))


def _check_region(region: str, box: tuple[int, int, int, int]) -> str:
    words = set(re.findall(r"[a-z]+", region.lower()))
    vert, horiz, dv, dh = _region_of(box)
    want_v = next((w for w in ("top", "bottom", "middle") if w in words or (w == "top" and "upper" in words)
                   or (w == "bottom" and "lower" in words)), None)
    want_h = next((w for w in ("left", "right", "centre") if w in words or (w == "centre" and "center" in words)),
                  None)
    if "centre" in words or "center" in words or "middle" in words:
        if want_v is None:
            want_v = "middle" if not (words & {"top", "bottom", "upper", "lower"}) else want_v
        if want_h is None and not (words & {"left", "right"}):
            want_h = "centre"
    if want_v is None and want_h is None:
        return "unverifiable"
    for want, have, margin in ((want_v, vert, dv), (want_h, horiz, dh)):
        if want is not None and want != have:
            return "unverifiable" if margin < 4 else "false"
    return "true"


def _colour_name(value: Any) -> str:
    """'lime', 11, '11' and 'lime(11)' all mean lime."""
    if isinstance(value, (int, np.integer)) and not isinstance(value, bool):
        return COLOUR_NAMES.get(int(value), str(value))
    text = str(value or "").strip().lower()
    match = re.fullmatch(r"([a-z]*)\s*\(?\s*(\d+)?\s*\)?", text)
    if match and match.group(2) and not match.group(1):
        return COLOUR_NAMES.get(int(match.group(2)), text)
    return match.group(1) if match and match.group(1) else text


def normalise_claim(claim: dict[str, Any]) -> dict[str, Any]:
    """Undo the extractor's formatting slips: fields nested under "fields"
    (seen from qwen38-flash-next-autoround on 2026-11-02), colour indices."""
    out = dict(claim)
    nested = out.pop("fields", None)
    if isinstance(nested, dict):
        for key, value in nested.items():
            out.setdefault(key, value)
    if out.get("colour") is not None:
        out["colour"] = _colour_name(out["colour"])
    return out


def check_claim(
    claim: dict[str, Any], truth: GroundTruth, observed: dict[str, Counter],
    skill_runner: Any = None,
) -> tuple[str, str]:
    """(label, evidence) for one claim."""
    claim = normalise_claim(claim)
    kind = str(claim.get("kind", "other"))
    if kind == "move":
        actions = [int(claim["action"])] if claim.get("action") is not None else sorted(truth.moves)
        direction = claim.get("direction")
        cells = claim.get("cells") if claim.get("unit", "cells") == "cells" else None
        if direction is None and cells is None:
            return "unverifiable", "no direction or size stated"
        notes = []
        for action in actions:
            if action not in truth.moves:
                return "unverifiable", f"ACTION{action} is not available in this game"
            real = truth.moves[action]
            seen = observed.get(f"ACTION{action}")
            logged = (f"; logged: {dict(seen.most_common(3))}" if seen else "")
            if real is None:
                notes.append(f"ACTION{action} never moved the player in the probe{logged}")
                if direction not in (None, "none"):
                    return "false", notes[-1]
                continue
            real_dir = next(name for name, (dr, dc) in DIRECTIONS.items()
                            if (np.sign(real[0]), np.sign(real[1])) == (dr, dc))
            size = max(abs(real[0]), abs(real[1]))
            notes.append(f"ACTION{action} moves the player {real_dir} {size} cells{logged}")
            if direction == "none" or (direction is not None and direction != real_dir):
                return "false", notes[-1]
            if cells is not None and int(cells) != size:
                return "false", notes[-1]
        return "true", "; ".join(notes)
    if kind == "colour_role":
        colour = str(claim.get("colour", "")).lower()
        role = str(claim.get("role", "other")).lower()
        if colour not in COLOUR_NAMES.values():
            return "unverifiable", f"unknown colour {colour!r}"
        if role in ABSENT_ROLES:
            return "false", f"Level 1 has no {role}; {truth.role_text(colour)}"
        if role not in ROLES or role == "other":
            return "unverifiable", f"role {role!r} is not checkable"
        roles = truth.roles.get(colour, set())
        if role in roles:
            return "true", truth.role_text(colour)
        if not roles:
            return "false", f"{colour} does not appear on the start screen"
        if "ui" in roles:
            return "unverifiable", f"{truth.role_text(colour)} (also in screen areas with no known role)"
        return "false", truth.role_text(colour)
    if kind == "location":
        name = str(claim.get("object", ""))
        if name in ABSENT_ROLES:
            return "false", f"Level 1 has no {name}"
        boxes = truth.objects.get(name)
        if not boxes:
            return "unverifiable", f"unknown object {name!r}"
        rows, cols = _range(claim.get("rows")), _range(claim.get("cols"))
        region = claim.get("region")
        evidence = truth.evidence.get(name, "")
        if rows is None and cols is None:
            if not region:
                return "unverifiable", "no location stated"
            labels = {_check_region(str(region), box) for box in boxes}
            label = "true" if "true" in labels else "false" if labels == {"false"} else "unverifiable"
            return label, evidence
        return ("true" if any(_overlaps(rows, cols, box) for box in boxes) else "false"), evidence
    if kind == "rotation_cause":
        cause = str(claim.get("cause", ""))
        switches = truth.objects.get("rotation_switch", [])
        if cause == "action":
            return "false", "no action rotates the player directly; " + truth.evidence["rotation_switch"]
        if cause == "touch":
            rows, cols = _range(claim.get("rows")), _range(claim.get("cols"))
            colour = claim.get("colour")
            if rows is not None or cols is not None:
                ok = any(_overlaps(rows, cols, box) for box in switches)
                return ("true" if ok else "false"), truth.evidence["rotation_switch"]
            if colour:
                return ("true" if str(colour).lower() in truth.switch_colours else "false"), (
                    f"switch colours {sorted(truth.switch_colours)}")
            return ("true" if switches else "false"), truth.evidence["rotation_switch"]
        return "unverifiable", f"cause {cause!r} is not checkable"
    if kind == "goal_requirement":
        requires = [str(r).lower() for r in claim.get("requires") or []]
        real = "the level clears when the player stands on the goal with matching rotation, shape and colour"
        if not requires:
            return "unverifiable", "no requirement stated"
        if any(r in ("collect", "avoid") for r in requires):
            return "false", real
        if any(r not in GOAL_CONDITIONS for r in requires):
            return "unverifiable", real
        return "true", real
    if kind == "count":
        what = str(claim.get("what", ""))
        if what not in truth.counts or claim.get("value") is None:
            return "unverifiable", f"count {what!r} is not checkable"
        real = truth.counts[what]
        return ("true" if int(claim["value"]) == real else "false"), f"{what} = {real}"
    if kind == "skill_output":
        if skill_runner is None:
            return "unverifiable", "no recorded states to run the skill on"
        return skill_runner(str(claim.get("skill", "")), str(claim.get("returns", "")))
    return "unverifiable", "outside the checkable vocabulary"


# ---------------------------------------------------------------------------
# Skill outputs on real recorded states
# ---------------------------------------------------------------------------


def _as_point(value: Any) -> tuple[float, float] | None:
    if isinstance(value, np.ndarray):
        value = value.tolist()
    if value is None:
        return None
    if isinstance(value, dict):
        for key in ("centroid", "center", "centre", "position", "pos"):
            if key in value:
                return _as_point(value[key])
        if "bbox" in value:
            return _as_point(value["bbox"])
        if "row" in value and "col" in value:
            return _as_point([value["row"], value["col"]])
        if "r" in value and "c" in value:
            return _as_point([value["r"], value["c"]])
        return None
    if isinstance(value, (list, tuple)):
        if len(value) in (2, 4) and all(isinstance(v, (int, float, np.integer, np.floating)) and
                                        not isinstance(v, bool) for v in value):
            if len(value) == 2:
                return float(value[0]), float(value[1])
            return (value[0] + value[2]) / 2, (value[1] + value[3]) / 2
        if value:
            return _as_point(value[0])
    return None


def make_skill_runner(harness: Any, test_states: list[tuple[str, list]], cfg: dict[str, Any]):
    """Run a skill on replayed recorded states; compare with the real position."""
    from evolve.action_loop import build_sandbox
    from evolve.goal_score import read_state
    from evolve.replay import api_at_state

    targets = {"player_position": "player", "goal_position": "goal",
               "rotation_switch_position": "rotation_switch"}

    def run(skill: str, returns: str) -> tuple[str, str]:
        if skill not in harness.skills:
            return "unverifiable", f"no skill named {skill!r}"
        if returns not in targets:
            return "unverifiable", f"return kind {returns!r} is not checkable"
        results = []
        for label, prefix in test_states:
            api = api_at_state(prefix, cfg)
            sandbox, _counter, failed = build_sandbox(api, harness, float(cfg["budget"]["cell_time_limit_s"]))
            if failed:
                return "unverifiable", f"skills fail to load: {failed}"
            cell = sandbox.run(f"fc_result = {skill}()", filename="<fact-check>")
            state = read_state(api.env)
            if returns == "player_position":
                box = (state["y"], state["x"], state["y"] + 4, state["x"] + 4)
            else:
                box = ground_truth(cfg["game"]).objects[targets[returns]][0]
            point = None if cell.error else _as_point(sandbox.namespace.get("fc_result"))
            if point is None:
                results.append((label, None, box))
                continue
            inside = any(box[0] - 1 <= r <= box[2] + 1 and box[1] - 1 <= c <= box[3] + 1
                         for r, c in (point, point[::-1]))
            results.append((label, inside, box))
        text = "; ".join(
            f"{label}: real rows {b[0]}-{b[2]}, cols {b[1]}-{b[3]} -> "
            + ("returned nothing usable" if ok is None else "match" if ok else "returned elsewhere")
            for label, ok, b in results
        )
        if any(ok is False for _l, ok, _b in results):
            return "false", text
        if results and all(ok for _l, ok, _b in results):
            return "true", text
        return "unverifiable", text

    return run


# ---------------------------------------------------------------------------
# One edit
# ---------------------------------------------------------------------------


def edit_text(edit: dict[str, Any]) -> str | None:
    """What an edit asserts: its new content (prompt, step or skill source)."""
    if edit["op"] == "delete":
        return None
    content = edit.get("content")
    return str(content) if content and str(content).strip() else None


class FactChecker:
    """Built once per Validate attempt; checks every edit of that attempt."""

    def __init__(self, cfg: dict[str, Any], client: Any, episodes: list[dict[str, Any]]) -> None:
        self.cfg = cfg
        self.client = client
        self.truth = ground_truth(cfg["game"])
        self.observed = observed_moves(episodes)
        self.extraction: dict[str, Any] = {"by_edit": {}, "tokens_in": 0, "tokens_out": 0, "calls": 0}

    def prepare(self, edits: list[dict[str, Any]]) -> None:
        items = [dict(e, content=edit_text(e)) for e in edits if edit_text(e)]
        if self.client is None:
            self.extraction = {"by_edit": {}, "tokens_in": 0, "tokens_out": 0, "calls": 0,
                               "error": "no extractor model configured"}
            return
        self.extraction = extract_claims(items, self.client, int(self.cfg["factcheck"]["max_tokens"]))

    def check(self, edit: dict[str, Any], harness: Any, test_states: list[tuple[str, list]]) -> dict[str, Any]:
        if edit_text(edit) is None:
            return {"verdict": "n/a", "claims": [], "summary": "n/a (nothing asserted)"}
        if self.extraction.get("error"):
            return {"verdict": "unverifiable", "claims": [],
                    "summary": f"claims could not be extracted ({self.extraction['error']})"}
        runner = make_skill_runner(harness, test_states, self.cfg)
        claims = []
        for claim in self.extraction["by_edit"].get(edit["id"], []):
            claim = normalise_claim(claim)
            try:
                label, evidence = check_claim(claim, self.truth, self.observed, runner)
            except (TypeError, ValueError, KeyError) as error:  # a malformed claim is not a false one
                label, evidence = "unverifiable", f"malformed claim: {type(error).__name__}: {error}"
            claims.append({"quote": str(claim.get("quote", ""))[:200], "kind": claim.get("kind"),
                           "claim": {k: v for k, v in claim.items() if k not in ("edit", "quote")},
                           "label": label, "evidence": evidence})
        counts = Counter(c["label"] for c in claims)
        verdict = "false" if counts["false"] else "unverifiable" if counts["unverifiable"] else "true"
        return {
            "verdict": verdict,
            "claims": claims,
            "summary": (f"{len(claims)} claims: {counts['true']} true, {counts['false']} false, "
                        f"{counts['unverifiable']} unverifiable"),
        }


def meta_facing_reason(result: dict[str, Any]) -> str:
    """The drop reason the Meta LLM sees: which claims are false, not why."""
    false = [c["quote"] for c in result["claims"] if c["label"] == "false"]
    return "contradicted by the game: " + "; ".join(f"'{q}'" for q in false[:4])
