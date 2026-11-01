"""The edit vocabulary of stage 2 and how an edit is applied to a harness.

Every edit is a dict:

    {"op": "add" | "edit" | "delete" | "merge",
     "target": "skill" | "prompt" | "step",
     "name": ...,  "names": [...],          # skills and prompts
     "index": n,   "indices": [i, j],       # steps, 1-based, parent numbering
     "content": "...", "test": "...",       # new text / source, skill test
     "rationale": "...", "source": "rule" | "meta", "id": "r2-e3"}

Step indices always refer to the *parent's* numbering, whatever was added or
removed before them in the same round. LLMs get shifting indices wrong, and a
dropped edit would otherwise silently re-target every later one, so steps carry
stable ids while edits are applied.
"""

from __future__ import annotations

import builtins
import copy
from dataclasses import dataclass, field
from typing import Any

from evolve.harness import CORE_PROMPTS, Harness

OPS = ("add", "edit", "delete", "merge")
TARGETS = ("skill", "prompt", "step")

# Names a skill may not take: the sandbox API, the preloaded modules, builtins.
RESERVED_NAMES = frozenset(
    {"action", "grid", "objects", "diff", "status", "history", "notes", "COLOURS",
     "np", "math", "collections", "itertools", "functools", "heapq", "print"}
) | frozenset(dir(builtins))


class EditError(ValueError):
    """The edit is malformed or does not apply to this harness."""


@dataclass
class Workspace:
    harness: Harness
    step_ids: list[int]
    next_step_id: int = 1000
    applied: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_parent(cls, parent: Harness, version: str, round_index: int) -> "Workspace":
        child = parent.child(version, round_index)
        return cls(harness=child, step_ids=list(range(1, len(child.steps) + 1)))

    def clone(self) -> "Workspace":
        return copy.deepcopy(self)


def normalise(edit: dict[str, Any], source: str) -> dict[str, Any]:
    """Coerce an LLM-written edit into the canonical shape, or raise."""
    if not isinstance(edit, dict):
        raise EditError("edit is not an object")
    op = str(edit.get("op", "")).lower().strip()
    target = str(edit.get("target", "")).lower().strip().rstrip("s")
    if op not in OPS:
        raise EditError(f"unknown op {op!r}")
    if target not in TARGETS:
        raise EditError(f"unknown target {edit.get('target')!r}")
    out: dict[str, Any] = {"op": op, "target": target, "source": source}
    for key in ("name", "content", "test", "rationale"):
        if edit.get(key) is not None:
            out[key] = str(edit[key])
    if edit.get("names") is not None:
        out["names"] = [str(n) for n in edit["names"]]
    if edit.get("index") is not None:
        out["index"] = _as_index(edit["index"])
    if edit.get("indices") is not None:
        out["indices"] = [_as_index(i) for i in edit["indices"]]
    for key in ("replay_strip", "replay_rename"):
        if key in edit:
            out[key] = edit[key]
    return out


def _as_index(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise EditError(f"step index {value!r} is not an integer") from error


def describe(edit: dict[str, Any]) -> str:
    target = edit["target"]
    if target == "step":
        where = edit.get("indices") or edit.get("index")
        return f"{edit['op']} step {where}"
    names = edit.get("names")
    if edit["op"] == "merge" and names:
        return f"merge {target}s {', '.join(names)} -> {edit.get('name')}"
    return f"{edit['op']} {target} {edit.get('name')}"


def apply_edit(ws: Workspace, edit: dict[str, Any]) -> None:
    """Apply in place. Raises EditError if the edit cannot apply."""
    target = edit["target"]
    if target == "skill":
        _apply_named(ws.harness.skills, edit, kind="skill", core=())
    elif target == "prompt":
        _apply_named(ws.harness.prompts, edit, kind="prompt", core=CORE_PROMPTS)
    else:
        _apply_step(ws, edit)
    ws.applied.append(edit)


def _require(edit: dict[str, Any], key: str) -> Any:
    value = edit.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        raise EditError(f"{edit['op']} {edit['target']} needs '{key}'")
    return value


def _apply_named(table: dict[str, str], edit: dict[str, Any], kind: str, core: tuple) -> None:
    op = edit["op"]
    if op == "merge":
        names = edit.get("names") or []
        if len(names) < 2:
            raise EditError(f"merge {kind} needs at least two 'names'")
        missing = [n for n in names if n not in table]
        if missing:
            raise EditError(f"merge {kind}: no such {kind} {missing}")
        name = _require(edit, "name")
        content = _require(edit, "content")
        if kind == "skill" and name in RESERVED_NAMES:
            raise EditError(f"'{name}' is a reserved name")
        if any(n in core for n in names if n != name):
            raise EditError(f"core {kind} cannot be merged away")
        for n in names:
            table.pop(n, None)
        table[name] = content
        return

    name = _require(edit, "name")
    if op == "add":
        if name in table:
            raise EditError(f"{kind} {name!r} already exists (use edit)")
        if kind == "skill" and name in RESERVED_NAMES:
            raise EditError(f"'{name}' is a reserved name")
        table[name] = _require(edit, "content")
    elif op == "edit":
        if name not in table:
            raise EditError(f"no {kind} named {name!r}")
        table[name] = _require(edit, "content")
    elif op == "delete":
        if name not in table:
            raise EditError(f"no {kind} named {name!r}")
        if name in core:
            raise EditError(f"core {kind} {name!r} cannot be deleted")
        del table[name]


def _position(ws: Workspace, index: int) -> int:
    try:
        return ws.step_ids.index(index)
    except ValueError as error:
        raise EditError(f"step {index} does not exist (or was removed earlier)") from error


def _apply_step(ws: Workspace, edit: dict[str, Any]) -> None:
    steps, ids = ws.harness.steps, ws.step_ids
    op = edit["op"]
    if op == "add":
        content = _require(edit, "content")
        index = int(edit.get("index") or (max(ids, default=0) + 1))
        position = ids.index(index) if index in ids else len(steps)
        steps.insert(position, content)
        ids.insert(position, ws.next_step_id)
        ws.next_step_id += 1
    elif op == "edit":
        steps[_position(ws, _require(edit, "index"))] = _require(edit, "content")
    elif op == "delete":
        position = _position(ws, _require(edit, "index"))
        del steps[position]
        del ids[position]
    elif op == "merge":
        indices = edit.get("indices") or []
        if len(indices) < 2:
            raise EditError("merge step needs at least two 'indices'")
        positions = sorted(_position(ws, i) for i in indices)
        content = _require(edit, "content")
        keep = positions[0]
        for position in reversed(positions[1:]):
            del steps[position]
            del ids[position]
        steps[keep] = content
