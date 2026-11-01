"""Prompt construction for the Round 0 / Round 1 harness.

The Round 0 prompt is exactly what issue #8 specifies: harness rules, available
actions, output format, the current observation, the diff from the previous
frame, the last N (action, effect) pairs, and a scratchpad the model rewrites
every step.

Round 1 adds one extra block: the validated skill library. Nothing else changes,
so the comparison isolates the skills.
"""

from __future__ import annotations

from typing import Any

from .model import PALETTE_LEGEND

MAX_SCRATCHPAD_CHARS = 2000

SYSTEM_PROMPT = """\
You are playing an ARC-AGI-3 video game through a text harness. You see a
coloured grid and choose one action per turn. Nobody tells you the rules of the
game: you must work them out by acting and watching what changes.

YOUR TASK: complete LEVEL 1 of this game in as few actions as possible.

THE GRID
- The observation is a 2D grid of colour indices. Row 0 is the top, column 0 is
  the left. Coordinates are written (row, col).
- Colour legend: {palette}
- Perception is done for you by plain code: you get the grid size, a colour
  histogram, and a list of connected-component objects with their colour,
  bounding box, size and centroid. Object ids are recomputed every step by
  size order, so id=3 on one step is NOT necessarily the same thing as id=3 on
  the next step. Identify objects by colour and position, not by id alone.

ACTIONS
- ACTION1 .. ACTION5 are simple actions with no arguments. Their meaning is
  game-specific and unknown to you. In many games some of them are directional.
- ACTION6 is a click. It REQUIRES arguments: {{"x": <col>, "y": <row>}} where x
  is the column and y is the row, both integers in 0..{max_coord}. Note the
  order: x is horizontal (column), y is vertical (row).
- ACTION7 is another simple action with no arguments.
- RESET restarts the level. It is allowed and sometimes necessary after a
  game-over, but every reset is counted against you, so do not use it to
  explore.
- Only the actions listed as AVAILABLE in the observation will have any effect.
  Choosing an unavailable action wastes a turn.

HOW TO PLAY WELL
- Early on, your job is to learn the dynamics: try each available action and
  read the diff carefully to see what it did.
- Once you know what an action does, stop re-testing it and start using it to
  make progress.
- If an action produces no change at all, that is information: the action may be
  blocked, irrelevant, or need different arguments.
- If the same thing keeps not working, change your approach instead of repeating
  it. Repeating a no-op action is the single most common way to waste the budget.
- Keep notes in the scratchpad. It is the only memory that survives beyond the
  last {history_n} steps, so record what you have established about the
  dynamics and the goal, not a narration of events.

OUTPUT FORMAT
Reply with a single JSON object and nothing else. No prose before or after, no
markdown code fence. The schema is:

{{"thought": "<brief reasoning, one or two sentences>",
 "action": "<one of RESET, ACTION1, ACTION2, ACTION3, ACTION4, ACTION5, ACTION6, ACTION7>",
 "args": {{}},
 "scratchpad": "<your updated notes, under {scratchpad_chars} characters>"}}

"args" must be {{}} for every action except ACTION6, where it must be
{{"x": <int>, "y": <int>}}. If "scratchpad" is omitted your previous notes are
kept unchanged.\
"""

SKILLS_HEADER = """\
LEARNED SKILL LIBRARY
These were mined automatically from previous play on a *different* set of games
and then validated against the recorded data. They are hypotheses, not
guarantees: a skill can be wrong for this particular game. Use them as a
starting point and trust the diff you actually observe over any skill text.\
"""


def system_prompt(
    history_n: int,
    max_coord: int = 63,
    skills_block: str | None = None,
) -> str:
    """Build the system prompt. `skills_block` is None in Round 0."""
    prompt = SYSTEM_PROMPT.format(
        palette=PALETTE_LEGEND,
        max_coord=max_coord,
        history_n=history_n,
        scratchpad_chars=MAX_SCRATCHPAD_CHARS,
    )
    if skills_block:
        prompt = f"{prompt}\n\n{SKILLS_HEADER}\n{skills_block}"
    return prompt


def format_history(history: list[dict[str, Any]], history_n: int) -> str:
    """Render the last N (action, effect) pairs."""
    if not history:
        return "HISTORY: none yet; this is your first action."
    recent = history[-history_n:]
    lines = [f"HISTORY (most recent {len(recent)} of {len(history)} actions):"]
    for entry in recent:
        action = entry["action"]
        args = entry.get("args") or {}
        args_text = f" {args}" if args else ""
        lines.append(f"  step {entry['step']}: {action}{args_text} -> {entry['effect']}")
    return "\n".join(lines)


def format_status(
    step: int,
    actions_used: int,
    max_actions: int,
    resets_used: int,
    available_actions: list[int],
    state: str,
    levels_completed: int,
) -> str:
    names = ", ".join(
        "RESET" if a == 0 else f"ACTION{a}" for a in sorted(available_actions)
    )
    return (
        f"STATUS: step {step} | actions used {actions_used}/{max_actions} | "
        f"resets {resets_used} | engine state {state} | "
        f"levels completed {levels_completed}\n"
        f"AVAILABLE ACTIONS: {names or 'none reported'}"
    )


def user_message(
    status_text: str,
    observation_text: str,
    diff_text: str,
    history_text: str,
    scratchpad: str,
    retry_note: str | None = None,
) -> str:
    """Assemble the per-step user message."""
    blocks = [
        status_text,
        "",
        "OBSERVATION",
        observation_text,
        "",
        diff_text,
        "",
        history_text,
        "",
        "SCRATCHPAD (your notes from last step; rewrite it in your reply)",
        scratchpad.strip() or "(empty)",
    ]
    if retry_note:
        blocks += ["", f"FORMAT ERROR ON YOUR LAST REPLY: {retry_note}",
                   "Reply with the JSON object only."]
    blocks += ["", "Choose your next action. JSON only."]
    return "\n".join(blocks)


def render_skills_block(skills: list[dict[str, Any]], max_skills: int = 24) -> str:
    """Render skills/index.json entries into the prompt block for Round 1."""
    if not skills:
        return ""
    lines: list[str] = []
    by_kind: dict[str, list[dict[str, Any]]] = {}
    for skill in skills:
        by_kind.setdefault(skill.get("kind", "other"), []).append(skill)

    kind_titles = {
        "action_effect": "Action-effect rules (what an action tends to do)",
        "macro": "Macro-actions (action sequences that preceded progress)",
        "module": "Code modules you can call as tools",
        "goal": "Goal hypotheses (what tends to be true just before a win)",
    }
    for kind in ("action_effect", "macro", "module", "goal"):
        group = by_kind.get(kind) or []
        if not group:
            continue
        group = group[:max_skills]
        lines.append(f"\n{kind_titles[kind]}:")
        for skill in group:
            support = skill.get("support")
            precision = skill.get("precision")
            evidence = []
            if support is not None:
                evidence.append(f"support={support}")
            if precision is not None:
                evidence.append(f"precision={precision:.2f}")
            evidence_text = f" [{', '.join(evidence)}]" if evidence else ""
            lines.append(f"  - {skill['name']}: {skill['description']}{evidence_text}")
            hint = skill.get("usage_hint")
            if hint:
                lines.append(f"      how to use: {hint}")
    return "\n".join(lines)


def render_tools_block(modules: list[dict[str, Any]]) -> str:
    """Describe callable code modules and the call syntax for Round 1."""
    if not modules:
        return ""
    lines = [
        "",
        "CALLING A CODE MODULE",
        'Instead of an action you may reply with {"thought": ..., "action": "CALL",',
        '"args": {"module": "<name>", "params": {...}}}. The harness runs the module',
        "on the current frame and replies with its output; that costs you no game",
        "action, but it does cost a turn of thinking, so do not call modules in a loop.",
        "Available modules:",
    ]
    for module in modules:
        params = module.get("params") or {}
        params_text = ", ".join(f"{k}: {v}" for k, v in params.items()) or "none"
        lines.append(f"  - {module['name']}({params_text}) -> {module['returns']}")
        lines.append(f"      {module['description']}")
    return "\n".join(lines)
