"""Build harness v0: issue #8's harness, ported to code-acting.

The issue says v0 is "the current harness". #8's harness emits one JSON action
per turn, while #9's action loop runs code, so v0 is necessarily a port. The
rule for the port is: keep everything #8's Round 1 player saw, and add only
what code-acting itself requires.

Kept from #8:
- the rules text of harness/prompt.py SYSTEM_PROMPT (grid, actions, how to
  play well), minus the JSON output format, which code-acting replaces;
- the 4 validated code modules of learning/modules.py, as Python functions
  that return data instead of text;
- the mined ls20 action-effect rules from skills/index.json, rendered exactly
  as #8 Round 1 rendered them, as the `knowledge` prompt.

Added because code-acting needs it: the sandbox API description (fixed, in
evolve/harness.py), the 6-step turn procedure, and the code-block reply format.
"""

from __future__ import annotations

import json
import os

from harness.model import PALETTE_LEGEND
from harness.prompt import SKILLS_HEADER, render_skills_block
from evolve.harness import Harness

SYSTEM_V0 = f"""\
You are playing an ARC-AGI-3 video game by writing Python code. You see a
coloured grid and act on it through a small API. Nobody tells you the rules of
the game: you must work them out by acting and watching what changes.

YOUR TASK: complete LEVEL 1 of this game in as few actions as possible.

THE GRID
- The observation is a 2D grid of colour indices. Row 0 is the top, column 0 is
  the left. Coordinates are written (row, col).
- Colour legend: {PALETTE_LEGEND}
- Perception is done for you by plain code: you get the grid size, a colour
  histogram, and a list of connected-component objects with their colour,
  bounding box, size and centroid. Object ids are recomputed every step by
  size order, so id=3 on one step is NOT necessarily the same thing as id=3 on
  the next step. Identify objects by colour and position, not by id alone.

ACTIONS
- ACTION1 .. ACTION5 are simple actions with no arguments. Their meaning is
  game-specific and unknown to you. In many games some of them are directional.
- ACTION6 is a click. It REQUIRES x (the column) and y (the row), both integers
  in 0..63. Note the order: x is horizontal (column), y is vertical (row).
- ACTION7 is another simple action with no arguments.
- RESET (action 0) restarts the level. It is allowed and sometimes necessary
  after a game-over, but every reset is counted against you, so do not use it to
  explore.
- Only the actions listed as AVAILABLE in the observation will have any effect.

HOW TO PLAY WELL
- Early on, your job is to learn the dynamics: try each available action and
  read the result carefully to see what it did.
- Once you know what an action does, stop re-testing it and start using it to
  make progress.
- If an action produces no change at all, that is information: the action may be
  blocked, irrelevant, or need different arguments.
- If the same thing keeps not working, change your approach instead of repeating
  it. Repeating a no-op action is the single most common way to waste the budget.
- Keep notes in `notes`. It is the only memory shown to you every turn, so record
  what you have established about the dynamics and the goal, not a narration of
  events."""

FORMAT_V0 = """\
REPLY FORMAT
Work through the turn procedure briefly (a few short lines, not paragraphs),
then give exactly one Python code block:

```python
# your code: act with action(...), inspect with grid()/objects()/diff(),
# print what you want to see next turn, and update `notes`
```

The code block is the only thing that is executed. Do not write a second code
block. Keep it short: it is a turn, not a program."""

STEPS_V0 = [
    "OBSERVE: read the observation and the result of your last cell. What "
    "changed, and what did each action you took actually do?",
    "CHECK: compare that with your notes and with what you expected. If anything "
    "contradicts your notes, say so and correct them.",
    "HYPOTHESISE: state your current best guess of what each action does and what "
    "the goal of the level is.",
    "PLAN: decide the next few actions (at most {cap}) that either test a "
    "hypothesis or make progress toward the goal.",
    "CODE: write one Python cell that takes those actions and prints what you need "
    "to see next turn. Use the skills where they help.",
    "NOTE: in the same cell, set `notes` to what you have established (dynamics, "
    "goal, where things are), not a narration of events.",
]

# #8's learning/modules.py, rewritten against the sandbox API so they return
# data the code can use. Behaviour matches the originals.
SKILLS_V0 = {
    "player_detector": '''\
def player_detector(g=None):
    """Rank which object is most likely the agent-controlled sprite.

    Heuristic: a small (<=16 cells) component whose colour occurs exactly once
    on the grid; falls back to the smallest components. Returns up to 3 objects
    (same fields as objects()), most likely first, each with "unique_colour".
    """
    objs = objects(g)
    if not objs:
        return []
    by_colour = {}
    for o in objs:
        by_colour.setdefault(o["colour"], []).append(o)
    cands = [os_[0] for os_ in by_colour.values() if len(os_) == 1 and os_[0]["size"] <= 16]
    if not cands:
        cands = sorted(objs, key=lambda o: o["size"])[:3]
    cands = sorted(cands, key=lambda o: o["size"])[:3]
    out = []
    for o in cands:
        item = dict(o)
        item["unique_colour"] = len(by_colour[o["colour"]]) == 1
        out.append(item)
    return out
''',
    "obstacle_map": '''\
def obstacle_map(g=None):
    """Classify each colour as wall-like or item-like from how its cells clump.

    Wall-like = at least 20 cells and on average 8+ cells per component.
    Returns {"colours": {colour: {"cells", "components", "largest", "verdict"}},
             "border": [colours touching the grid border]}.
    """
    g = grid() if g is None else np.asarray(g)
    stats = {}
    for o in objects(g):
        e = stats.setdefault(o["colour"], {"cells": 0, "components": 0, "largest": 0})
        e["cells"] += o["size"]
        e["components"] += 1
        e["largest"] = max(e["largest"], o["size"])
    for e in stats.values():
        ratio = e["cells"] / max(e["components"], 1)
        e["verdict"] = "wall-like" if e["cells"] >= 20 and ratio >= 8 else "item-like"
    border = []
    for colour in stats:
        m = g == colour
        if m[0, :].any() or m[-1, :].any() or m[:, 0].any() or m[:, -1].any():
            border.append(colour)
    return {"colours": stats, "border": sorted(border)}
''',
    "bfs_to_target": '''\
def bfs_to_target(from_row, from_col, to_row, to_col, blocked_colours=(), g=None):
    """Shortest 4-connected path length between two cells.

    Cells whose colour is in blocked_colours are impassable. Returns the number
    of single-cell steps, or None if the target is unreachable or blocked.
    """
    g = grid() if g is None else np.asarray(g)
    h, w = g.shape
    blocked = {int(c) for c in blocked_colours}
    start, goal = (int(from_row), int(from_col)), (int(to_row), int(to_col))
    for r, c in (start, goal):
        if not (0 <= r < h and 0 <= c < w):
            return None
    if int(g[goal]) in blocked:
        return None
    queue = collections.deque([start])
    dist = {start: 0}
    while queue:
        cell = queue.popleft()
        if cell == goal:
            return dist[cell]
        r, c = cell
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < h and 0 <= nc < w and (nr, nc) not in dist and int(g[nr, nc]) not in blocked:
                dist[(nr, nc)] = dist[cell] + 1
                queue.append((nr, nc))
    return None
''',
    "grid_region": '''\
def grid_region(row0, col0, row1, col1, g=None):
    """Raw colour indices of a rectangle, as text (one hex digit per cell).

    Use it to zoom in when objects() is too coarse. At most 1024 cells.
    """
    g = grid() if g is None else np.asarray(g)
    h, w = g.shape
    r0, c0 = max(0, int(row0)), max(0, int(col0))
    r1, c1 = min(h - 1, int(row1)), min(w - 1, int(col1))
    if r1 < r0 or c1 < c0:
        return "empty range (need row0<=row1 and col0<=col1)"
    if (r1 - r0 + 1) * (c1 - c0 + 1) > 1024:
        return "region too large; ask for at most 1024 cells"
    lines = ["     " + "".join(str(c % 10) for c in range(c0, c1 + 1))]
    for r in range(r0, r1 + 1):
        lines.append(f"r{r:>3} " + "".join(format(int(v), "x") for v in g[r, c0:c1 + 1]))
    return "\\n".join(lines)
''',
}


def knowledge_from_issue8(index_path: str = os.path.join("skills", "index.json")) -> str:
    """#8's mined action-effect rules, rendered as #8 Round 1 rendered them."""
    if not os.path.exists(index_path):
        return ""
    with open(index_path, encoding="utf-8") as handle:
        index = json.load(handle)
    rules = [s for s in index.get("skills", []) if s.get("kind") == "action_effect"]
    if not rules:
        return ""
    # #8's header says the skills came from "a different set of games". For
    # ls20 that was never true (they were mined from ls20 itself), so the
    # header is restated accurately rather than copied.
    header = SKILLS_HEADER.replace(
        "from previous play on a *different* set of games",
        "from previous play on this game",
    )
    return f"{header}\n{render_skills_block(rules)}".strip()


def build_v0() -> Harness:
    prompts = {"system": SYSTEM_V0}
    knowledge = knowledge_from_issue8()
    if knowledge:
        prompts["knowledge"] = knowledge
    prompts["format"] = FORMAT_V0
    return Harness(
        version="v0",
        parent=None,
        round_index=0,
        prompts=prompts,
        steps=list(STEPS_V0),
        skills=dict(SKILLS_V0),
        edits=[{"op": "seed", "source": "issue #8 harness", "note": __doc__.strip().splitlines()[0]}],
    )
