"""Strict JSON action parsing.

Issue #8: output must be strict JSON {"thought", "action", "args"}. On a parse
failure, retry once, then fall back to a no-op / random valid action. All
failures are counted so the report can state a parse-failure rate.
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass
from typing import Any

ACTION_NAMES = {
    "RESET": 0,
    "ACTION1": 1,
    "ACTION2": 2,
    "ACTION3": 3,
    "ACTION4": 4,
    "ACTION5": 5,
    "ACTION6": 6,
    "ACTION7": 7,
}
ID_TO_NAME = {value: name for name, value in ACTION_NAMES.items()}

CLICK_ACTION = 6
MAX_COORD = 63


class ParseFailure(ValueError):
    """The model's reply could not be turned into an action."""


@dataclass
class Decision:
    action_id: int
    action_name: str
    args: dict[str, Any]
    thought: str
    scratchpad: str | None
    is_module_call: bool = False
    module: str | None = None
    module_params: dict[str, Any] | None = None


def _extract_json_object(text: str) -> dict[str, Any]:
    """Find and parse the JSON object in a model reply.

    Tolerates a markdown fence or stray prose around the object, because that
    is a formatting slip rather than a wrong decision -- but anything that is
    not a JSON object at all is a parse failure.
    """
    if not text or not text.strip():
        raise ParseFailure("empty reply")

    cleaned = text.strip()
    # Strip a <think>...</think> block if the gateway inlines reasoning.
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()
    # Strip markdown fences.
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, flags=re.DOTALL)
    if fence:
        cleaned = fence.group(1).strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        # Fall back to the first balanced {...} span in the text.
        start = cleaned.find("{")
        if start == -1:
            raise ParseFailure("no JSON object found in reply")
        depth = 0
        in_string = False
        escaped = False
        end = -1
        for index in range(start, len(cleaned)):
            char = cleaned[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    end = index + 1
                    break
        if end == -1:
            raise ParseFailure("unterminated JSON object in reply")
        try:
            parsed = json.loads(cleaned[start:end])
        except json.JSONDecodeError as error:
            raise ParseFailure(f"invalid JSON: {error.msg}") from error

    if not isinstance(parsed, dict):
        raise ParseFailure(f"expected a JSON object, got {type(parsed).__name__}")
    return parsed


def _coerce_coord(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise ParseFailure(f"{name} must be an integer, got a boolean")
    if isinstance(value, (int, float)):
        coord = int(round(float(value)))
    elif isinstance(value, str):
        match = re.search(r"-?\d+", value)
        if not match:
            raise ParseFailure(f"{name} is not a number: {value!r}")
        coord = int(match.group(0))
    else:
        raise ParseFailure(f"{name} must be an integer, got {type(value).__name__}")
    if not 0 <= coord <= MAX_COORD:
        raise ParseFailure(f"{name}={coord} is outside 0..{MAX_COORD}")
    return coord


def parse_decision(
    text: str,
    available_actions: list[int],
    allow_modules: bool = False,
) -> Decision:
    """Parse a model reply into a Decision, or raise ParseFailure."""
    parsed = _extract_json_object(text)

    raw_action = parsed.get("action")
    if raw_action is None:
        raise ParseFailure('missing "action" field')
    action_text = str(raw_action).strip().upper().replace(" ", "").replace("-", "_")

    thought = str(parsed.get("thought") or "")[:2000]
    scratchpad = parsed.get("scratchpad")
    scratchpad_text = None if scratchpad is None else str(scratchpad)

    args = parsed.get("args")
    if args is None:
        args = {}
    if not isinstance(args, dict):
        raise ParseFailure(f'"args" must be an object, got {type(args).__name__}')

    # --- module call (Round 1 only) ---------------------------------------
    if action_text in ("CALL", "CALL_MODULE", "MODULE"):
        if not allow_modules:
            raise ParseFailure("module calls are not available in this round")
        module = args.get("module")
        if not module:
            raise ParseFailure('a CALL needs args.module')
        params = args.get("params") or {}
        if not isinstance(params, dict):
            raise ParseFailure("args.params must be an object")
        return Decision(
            action_id=-1,
            action_name="CALL",
            args=dict(args),
            thought=thought,
            scratchpad=scratchpad_text,
            is_module_call=True,
            module=str(module),
            module_params=params,
        )

    # Accept bare integers and "6" as well as "ACTION6".
    if action_text.isdigit():
        action_id = int(action_text)
        if action_id not in ID_TO_NAME:
            raise ParseFailure(f"unknown action id {action_id}")
    elif action_text in ACTION_NAMES:
        action_id = ACTION_NAMES[action_text]
    else:
        raise ParseFailure(f"unknown action {raw_action!r}")

    name = ID_TO_NAME[action_id]

    if action_id == CLICK_ACTION:
        # Accept {x,y}, {col,row}, or a 2-element coordinate list.
        if "x" in args or "y" in args:
            if "x" not in args or "y" not in args:
                raise ParseFailure("ACTION6 needs both x and y")
            x = _coerce_coord(args["x"], "x")
            y = _coerce_coord(args["y"], "y")
        elif "col" in args and "row" in args:
            x = _coerce_coord(args["col"], "col")
            y = _coerce_coord(args["row"], "row")
        elif isinstance(args.get("coord"), (list, tuple)) and len(args["coord"]) == 2:
            x = _coerce_coord(args["coord"][0], "coord[0]")
            y = _coerce_coord(args["coord"][1], "coord[1]")
        else:
            raise ParseFailure('ACTION6 requires args {"x": <int>, "y": <int>}')
        return Decision(
            action_id=action_id,
            action_name=name,
            args={"x": x, "y": y},
            thought=thought,
            scratchpad=scratchpad_text,
        )

    return Decision(
        action_id=action_id,
        action_name=name,
        args={},
        thought=thought,
        scratchpad=scratchpad_text,
    )


def fallback_decision(
    available_actions: list[int], rng: random.Random, reason: str
) -> Decision:
    """No-op/random valid action used after a parse failure and its one retry.

    Prefers a non-RESET available action so the fallback does not destroy
    progress; clicks get a random in-bounds coordinate.
    """
    candidates = [a for a in available_actions if a in ID_TO_NAME and a != 0]
    if not candidates:
        candidates = [a for a in available_actions if a in ID_TO_NAME] or [5]
    action_id = rng.choice(candidates)
    args: dict[str, Any] = {}
    if action_id == CLICK_ACTION:
        args = {
            "x": rng.randint(0, MAX_COORD),
            "y": rng.randint(0, MAX_COORD),
        }
    return Decision(
        action_id=action_id,
        action_name=ID_TO_NAME[action_id],
        args=args,
        thought=f"[harness fallback after parse failure: {reason}]",
        scratchpad=None,
    )
