"""Stage 3 · Validate: tests, replay, merge-equivalence. Failing edits are dropped.

Edits are tried one at a time, in order, each on top of the edits that already
passed. An edit is kept only if every check that applies to it passes:

1. **applies** -- it is well formed and fits the harness (no such step, core
   prompt deleted, name clash with the sandbox API, ...).
2. **static tests** -- skills: pass the sandbox's AST rules, define exactly the
   named function, carry a docstring, stay under the line cap. Prompts and
   steps: size limits, the reply format still asks for a python block, the step
   count stays in range. Always: the rendered system prompt stays under its cap.
3. **load test** -- every skill of the edited harness loads in a live sandbox.
4. **replay** (skills only; text edits cannot be replayed without a model):
   the parent's episodes are re-run cell by cell, with no model, under the
   edited harness and compared with the parent's own replay.
   - add from a promoted helper: the inline `def` is stripped from the cells so
     the skill runs instead; behaviour must be identical, and the skill must
     actually have been called.
   - delete: behaviour must be identical (the skill was not needed).
   - merge: calls to the merged names are renamed to the survivor; behaviour
     must be identical -- this is the merge-equivalence check.
   - add (new) / edit: up to the first point where behaviour diverges, the
     edited harness must not raise where the parent did not.
5. **skill test** -- for skills from the Meta LLM, the edit's own test snippet
   runs on real recorded states (start / middle / late of an episode) and must
   not raise.
"""

from __future__ import annotations

import ast
from typing import Any, Callable

from evolve.action_loop import build_sandbox
from evolve.edits import EditError, Workspace, apply_edit, describe, normalise
from evolve.harness import Harness
from evolve.replay import ReplayResult, api_at_state, replay, states_along
from evolve.sandbox import SandboxViolation, check_source, strip_function_defs


class _Rename(ast.NodeTransformer):
    def __init__(self, mapping: dict[str, str]) -> None:
        self.mapping = mapping

    def visit_Name(self, node: ast.Name) -> ast.Name:
        if node.id in self.mapping and isinstance(node.ctx, ast.Load):
            node.id = self.mapping[node.id]
        return node


def make_transform(edit: dict[str, Any]) -> Callable[[str], str] | None:
    strip = edit.get("replay_strip") or []
    rename = edit.get("replay_rename") or {}
    if edit["target"] == "skill" and edit["op"] == "merge":
        rename = {n: edit["name"] for n in edit.get("names", []) if n != edit["name"]} | rename
    if not strip and not rename:
        return None

    def transform(code: str) -> str:
        for name, key in strip:
            code = strip_function_defs(code, name, key)
        if rename:
            try:
                tree = _Rename(rename).visit(ast.parse(code))
                code = ast.unparse(tree)
            except SyntaxError:
                pass
        return code

    return transform


# ---------------------------------------------------------------------------
# Individual checks. Each returns (ok, message).
# ---------------------------------------------------------------------------


def static_tests(harness: Harness, edit: dict[str, Any], cfg: dict[str, Any]) -> tuple[bool, str]:
    limits = cfg["validate"]
    target, op = edit["target"], edit["op"]
    if target == "skill" and op != "delete":
        name, source = edit["name"], edit["content"]
        try:
            tree = check_source(source)
        except SandboxViolation as error:
            return False, f"sandbox rules: {error}"
        functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
        others = [n for n in tree.body if not isinstance(n, ast.FunctionDef)
                  and not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))]
        if [f.name for f in functions] != [name]:
            return False, f"source must define exactly one top-level function named {name!r}"
        if others:
            return False, "source may contain only the function (no top-level statements)"
        if ast.get_docstring(functions[0]) is None:
            return False, "skill has no docstring (the player only sees signature + docstring)"
        if len(source.strip().splitlines()) > int(limits["max_skill_lines"]):
            return False, f"skill longer than {limits['max_skill_lines']} lines"
    if target == "prompt":
        for key, text in harness.prompts.items():
            if len(text) > int(limits["max_prompt_chars"]):
                return False, f"prompt {key!r} is {len(text)} chars (> {limits['max_prompt_chars']})"
        if "```python" not in harness.prompts.get("format", ""):
            return False, "the format prompt no longer asks for a ```python block"
    if target == "step":
        n = len(harness.steps)
        if not int(limits["min_steps"]) <= n <= int(limits["max_steps"]):
            return False, f"{n} steps (allowed {limits['min_steps']}..{limits['max_steps']})"
        for index, step in enumerate(harness.steps, start=1):
            if not step.strip():
                return False, f"step {index} is empty"
            if len(step) > int(limits["max_step_chars"]):
                return False, f"step {index} is {len(step)} chars (> {limits['max_step_chars']})"
    rendered = harness.render_system(int(cfg["budget"]["actions_per_turn"]))
    if len(rendered) > int(limits["max_system_chars"]):
        return False, f"system prompt would be {len(rendered)} chars (> {limits['max_system_chars']})"
    return True, f"static ok (system prompt {len(rendered)} chars)"


def load_test(harness: Harness, cfg: dict[str, Any]) -> tuple[bool, str]:
    api = api_at_state([], cfg)
    _sandbox, _counter, failed = build_sandbox(api, harness, float(cfg["budget"]["cell_time_limit_s"]))
    if failed:
        name, error = next(iter(failed.items()))
        return False, f"skill {name} fails to load: {error}"
    return True, f"all {len(harness.skills)} skills load"


def _compare(base: ReplayResult, cand: ReplayResult) -> tuple[int, int | None]:
    """(turns compared, first turn index where the candidate diverged)."""
    # Only turns the parent itself reproduced, and only up to its own first
    # divergence: after that the two runs are on different game states.
    limit = len(base.reproduced)
    if False in base.reproduced:
        limit = base.reproduced.index(False)
    for i in range(min(limit, len(cand.reproduced))):
        if not cand.reproduced[i]:
            return limit, i
    if len(cand.reproduced) < limit:
        return limit, len(cand.reproduced)
    return limit, None


def replay_test(
    harness: Harness, edit: dict[str, Any], episodes: list[dict[str, Any]],
    baselines: dict[int, ReplayResult], cfg: dict[str, Any],
) -> tuple[bool, str, dict[str, Any]]:
    if edit["target"] != "skill":
        return True, "n/a (text edit: replay cannot test model behaviour)", {}
    transform = make_transform(edit)
    op, name = edit["op"], edit.get("name")
    # Adding a function, deleting an unused one and merging equivalent ones
    # must not change behaviour at all. Only an edit may, on purpose.
    must_match = op in ("add", "delete", "merge")
    detail: dict[str, Any] = {"episodes": []}
    exercised = 0
    for episode in episodes:
        base = baselines[episode["episode"]]
        cand = replay(episode["records"], harness, cfg, transform=transform)
        compared, diverged = _compare(base, cand)
        calls = cand.skill_calls.get(name, 0) if name else 0
        exercised += calls
        detail["episodes"].append(
            {"episode": episode["episode"], "turns_compared": compared,
             "diverged_at": diverged, "skill_calls": calls}
        )
        if must_match and diverged is not None:
            what = "merge is not behaviour-equivalent" if op == "merge" else "behaviour changed"
            return False, f"{what}: episode {episode['episode']} diverges at turn {diverged}", detail
        if op == "merge":
            # Same actions is not enough: compare what the skills *returned*,
            # call by call, on the real recorded inputs.
            merged = set(edit.get("names") or []) | {name}
            before = [fp for skill, fp in base.trace if skill in merged]
            after = [fp for skill, fp in cand.trace if skill == name]
            if before != after:
                first = next(
                    (i for i, (b, a) in enumerate(zip(before, after)) if b != a),
                    min(len(before), len(after)),
                )
                return False, (
                    f"merge is not behaviour-equivalent: episode {episode['episode']}, "
                    f"call {first} of {len(before)} returns a different value"
                ), detail
        if not must_match and diverged is not None:
            if diverged < len(cand.errors) and cand.errors[diverged] and not base.errors[diverged]:
                return False, (
                    f"edited skill raises where the parent did not: episode "
                    f"{episode['episode']} turn {diverged}"
                ), detail
    if op == "add" and edit.get("replay_strip") and exercised == 0:
        return False, "promoted helper was never exercised by replay (check is vacuous)", detail
    if op == "merge" and exercised == 0:
        detail["note"] = "merge-equivalence vacuous: merged skills never called in replay"
    return True, (
        f"replay ok over {len(episodes)} episodes"
        + (f", skill called {exercised} times" if name else "")
    ), detail


def skill_test(
    harness: Harness, edit: dict[str, Any], states: list[tuple[str, list]], cfg: dict[str, Any]
) -> tuple[bool, str]:
    if edit["target"] != "skill" or edit["op"] == "delete" or edit.get("source") != "meta":
        return True, "n/a"
    test = edit.get("test")
    if not test or not str(test).strip():
        return False, "no test snippet provided"
    for label, prefix in states:
        api = api_at_state(prefix, cfg)
        sandbox, _counter, failed = build_sandbox(api, harness, float(cfg["budget"]["cell_time_limit_s"]))
        if failed:
            return False, f"skills fail to load: {failed}"
        result = sandbox.run(str(test), filename="<test>")
        if result.error:
            return False, f"test fails at state '{label}': {result.error}"
    return True, f"test passes on {len(states)} recorded states"


# ---------------------------------------------------------------------------


def validate(
    parent: Harness,
    raw_edits: list[dict[str, Any]],
    episodes: list[dict[str, Any]],
    cfg: dict[str, Any],
    version: str,
    round_index: int,
    log: Callable[[str], None] = print,
) -> tuple[Harness, list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    ws = Workspace.from_parent(parent, version, round_index)
    baselines = {e["episode"]: replay(e["records"], parent, cfg) for e in episodes}
    fidelity = {
        e: {"turns": b.turns, "reproduced": b.n_reproduced, "first_divergence": b.first_divergence}
        for e, b in baselines.items()
    }
    longest = max(episodes, key=lambda e: len(e["records"]))
    states = states_along(longest["records"], cfg, tuple(cfg["validate"]["test_state_fractions"]))

    passed: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_edits, start=1):
        edit_id = f"r{round_index}-e{index}"
        source = raw.get("source", "meta") if isinstance(raw, dict) else "meta"
        try:
            edit = normalise(raw, source)
        except EditError as error:
            dropped.append({"id": edit_id, "source": source, "what": str(raw)[:120],
                            "stage": "applies", "reason": f"malformed: {error}", "edit": raw})
            continue
        edit["id"] = edit_id
        what = describe(edit)
        trial = ws.clone()
        checks: list[dict[str, str]] = []

        def drop(stage: str, reason: str) -> None:
            log(f"    drop {edit_id} [{source}] {what}: {reason}")
            dropped.append({"id": edit_id, "source": source, "what": what, "stage": stage,
                            "reason": reason, "edit": edit, "checks": checks})

        try:
            apply_edit(trial, edit)
        except EditError as error:
            drop("applies", str(error))
            continue
        checks.append({"check": "applies", "result": "ok"})

        ok, message = static_tests(trial.harness, edit, cfg)
        checks.append({"check": "static tests", "result": message})
        if not ok:
            drop("static tests", message)
            continue
        if edit["target"] == "skill":
            ok, message = load_test(trial.harness, cfg)
            checks.append({"check": "load test", "result": message})
            if not ok:
                drop("load test", message)
                continue
        ok, message, detail = replay_test(trial.harness, edit, episodes, baselines, cfg)
        checks.append({"check": "replay" if edit["op"] != "merge" else "replay + merge-equivalence",
                       "result": message})
        if not ok:
            drop("replay", message)
            continue
        ok, message = skill_test(trial.harness, edit, states, cfg)
        checks.append({"check": "skill test", "result": message})
        if not ok:
            drop("skill test", message)
            continue

        ws = trial
        log(f"    pass {edit_id} [{source}] {what}")
        passed.append({"id": edit_id, "source": source, "what": what, "edit": edit,
                       "rationale": edit.get("rationale", ""), "checks": checks,
                       "replay_detail": detail})

    child = ws.harness
    child.edits = [
        {"id": p["id"], "source": p["source"], "what": p["what"], "rationale": p["rationale"]}
        for p in passed
    ]
    return child, passed, dropped, {"fidelity": fidelity, "test_states": [s[0] for s in states]}
