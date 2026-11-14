"""Stage 3 · Validate, skill-name check (issue #14, fix 1).

#12's Validate checked each edit on its own, so text could keep naming a skill
that no longer existed: v6 and v7 told the player to call `find_goal()`, which
Validate had dropped in the same round, and players hit 37 NameErrors on it in
one version. This check reads every text of the *candidate* harness, after the
edits are applied, and finds each name that is used like a skill but is not
one.

What is read:

- prompts and steps (prose);
- every skill's docstring (prose) and code (parsed, not regex-matched).

What counts as a skill reference:

- prose: call-like text `name(...)`, and a backticked identifier. Backticked
  code (`` `x = foo(g)` ``) is parsed and its calls are the references;
- code: every call of a bare name, found in the AST. Names the function binds
  itself (parameters, local variables, nested functions, imports) are not
  references.

Valid names: the skills of the candidate harness, the sandbox API and the
builtins the sandbox provides. NOT_SKILLS is the short allowlist of
identifiers that text legitimately backticks or writes call-like but that are
not skills: action names and the fields of the API's return values.

Deterministic, no model. `python -m evolve.skill_names DIR [DIR ...]` audits
saved harness versions.
"""

from __future__ import annotations

import ast
import keyword
import re
import sys
from typing import Any

from evolve.edits import RESERVED_NAMES
from evolve.harness import Harness, load_harness
from evolve.sandbox import _SAFE_BUILTIN_NAMES

# Sandbox built-ins: the API, the preloaded modules, and the whitelisted
# Python builtins (RESERVED_NAMES holds the first two plus dir(builtins)).
BUILTIN_NAMES = frozenset(RESERVED_NAMES) | frozenset(_SAFE_BUILTIN_NAMES)

# Identifiers that are not skills but appear backticked or call-like in
# harness text: action names, engine states, and the fields of what the API
# returns (see API_DOC in evolve/harness.py).
NOT_SKILLS = frozenset(
    {f"ACTION{i}" for i in range(1, 8)}
    | {"RESET", "GAME_OVER", "WIN", "NOT_FINISHED", "NOT_PLAYED", "AVAILABLE"}
    | {
        # action() result, objects() items, status(), history()
        "n_changed", "state", "levels_completed", "game_over", "effect", "id", "colour",
        "colour_name", "bbox", "size", "centroid", "actions_used", "actions_left", "turn",
        "turn_actions_left", "available_actions", "resets", "args",
        # argument and coordinate names the API text uses
        "a", "x", "y", "g", "n", "b", "r", "c", "r0", "c0", "r1", "c1", "row", "col", "rows",
        "cols", "old", "new", "cap", "python", "py", "json",
    }
)

CALL_RE = re.compile(r"(?<![\w.])([A-Za-z_][A-Za-z0-9_]*)\(")
BACKTICK_RE = re.compile(r"(?<!`)`([^`\n]+)`(?!`)")
IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
PLURAL_RE = re.compile(r"\((?:s|es)\)")  # "skill(s)" is English, not a call


def _bound_names(tree: ast.AST) -> set[str]:
    """Every name the code binds itself: parameters, assignment and loop
    targets, nested functions and classes, imports, exception names."""
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            bound.add(node.id)
        elif isinstance(node, ast.arg):
            bound.add(node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                bound.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bound.add(node.name)
    return bound


def _calls(tree: ast.AST) -> list[tuple[str, int]]:
    """(name, line) of every call of a bare name."""
    return [
        (node.func.id, node.lineno)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]


def _backticked(content: str) -> list[str]:
    """Skill-like names in one backticked span."""
    content = content.strip()
    if IDENT_RE.fullmatch(content):
        return [content]
    try:
        tree = ast.parse(content)
    except SyntaxError:
        # Not Python (e.g. `grid()/objects()`): fall back to call-like text.
        return [m.group(1) for m in CALL_RE.finditer(content)]
    bound = _bound_names(tree)
    return [name for name, _line in _calls(tree) if name not in bound]


def prose_references(text: str) -> list[tuple[str, int]]:
    """(name, line) of every skill-like reference in prose. Lines are 1-based."""
    found: list[tuple[str, int]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        spans = []
        for match in BACKTICK_RE.finditer(line):
            spans.append(match.span())
            found.extend((name, number) for name in _backticked(match.group(1)))
        for match in CALL_RE.finditer(line):
            if any(lo <= match.start() < hi for lo, hi in spans):
                continue  # already read as backticked code
            if PLURAL_RE.match(line, match.end() - 1):
                continue
            found.append((match.group(1), number))
    return found


def _is_valid(name: str, valid: set[str] | frozenset[str]) -> bool:
    return name in valid or name in NOT_SKILLS or keyword.iskeyword(name) or keyword.issoftkeyword(name)


def _skill_violations(name: str, source: str, valid: set[str]) -> list[dict[str, Any]]:
    file = f"skills/{name}.py"
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []  # the static tests reject unparseable skills
    out: list[dict[str, Any]] = []
    lines = source.splitlines()
    local = _bound_names(tree)
    for called, line in _calls(tree):
        if called not in local and not _is_valid(called, valid):
            out.append({"name": called, "file": file, "line": line, "where": "skill code",
                        "text": lines[line - 1].strip()[:120] if line <= len(lines) else ""})
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        doc = ast.get_docstring(node, clean=False)
        if not doc:
            continue
        first = node.body[0].lineno  # the docstring's first line in the file
        doc_lines = doc.splitlines()
        for called, line in prose_references(doc):
            if called not in local and not _is_valid(called, valid):
                out.append({"name": called, "file": file, "line": first + line - 1, "where": "skill docstring",
                            "text": doc_lines[line - 1].strip()[:120]})
    return out


def check_harness(harness: Harness) -> list[dict[str, Any]]:
    """Every reference to a skill that the harness does not have.

    Each item: {"name", "file", "line", "where", "text"}. An empty list means
    every name used like a skill is a skill of this harness or a sandbox
    built-in.
    """
    valid = set(harness.skills) | set(BUILTIN_NAMES)
    # A skill's parameters are fair to name in any text about it.
    for source in harness.skills.values():
        try:
            valid |= {a.arg for n in ast.walk(ast.parse(source)) if isinstance(n, ast.arguments)
                      for a in n.posonlyargs + n.args + n.kwonlyargs}
        except SyntaxError:
            continue
    out: list[dict[str, Any]] = []
    for key, text in harness.prompts.items():
        lines = text.splitlines()
        for name, line in prose_references(text):
            if not _is_valid(name, valid):
                out.append({"name": name, "file": f"prompts.json[{key}]", "line": line, "where": "prompt",
                            "text": lines[line - 1].strip()[:120]})
    for index, step in enumerate(harness.steps, start=1):
        lines = step.splitlines()
        for name, line in prose_references(step):
            if not _is_valid(name, valid):
                out.append({"name": name, "file": f"steps.json[{index}]", "line": line, "where": "step",
                            "text": lines[line - 1].strip()[:120]})
    for name in sorted(harness.skills):
        out.extend(_skill_violations(name, harness.skills[name], valid))
    return out


def _key(violation: dict[str, Any]) -> tuple[str, str]:
    # Without the line, and for steps without the index: an edit that shifts
    # text must not make an old violation look new.
    file = re.sub(r"^steps\.json\[\d+\]$", "steps.json", violation["file"])
    return (file, violation["name"])


def new_violations(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Violations in `after` that `before` did not have: what one edit caused."""
    old = {_key(v) for v in before}
    return [v for v in after if _key(v) not in old]


def describe(violations: list[dict[str, Any]], limit: int = 6) -> str:
    """One line for the drop reason and the CHANGELOG: name, file, line."""
    parts = [f"`{v['name']}` ({v['file']} line {v['line']})" for v in violations[:limit]]
    more = f" and {len(violations) - limit} more" if len(violations) > limit else ""
    return "names a skill that does not exist: " + "; ".join(parts) + more


def audit(paths: list[str]) -> int:
    total = 0
    for path in paths:
        path = path.rstrip("/\\")
        root, _, version = path.replace("\\", "/").rpartition("/")
        violations = check_harness(load_harness(version, root or "."))
        total += len(violations)
        print(f"{path}: {len(violations)} missing skill name(s)")
        for v in violations:
            print(f"  {v['name']:<24} {v['file']} line {v['line']} [{v['where']}]: {v['text']}")
    return total


if __name__ == "__main__":
    raise SystemExit(1 if audit(sys.argv[1:]) else 0)
