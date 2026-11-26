"""Rejected edits (issue #16, changes 3 and 4).

Change 3, the repeat check. #15's ft09 run proposed the same skill and prompt
line in every round, rationale word for word, and nothing stopped it: the
"do not re-propose" guidance in the Meta prompt is a request, not a check.
Every edit rejected in a game's run goes to `<run dir>/rejected_edits.jsonl`:

- an edit dropped by any Validate check;
- every edit of a version rejected at the Gate.

Validate drops an edit that matches one in the store, before its other
checks. A match is the same type and the same target, and:

- code (skills): identical once normalised: docstring, comments, layout and
  every name the function binds itself (its own name, parameters, local
  variables) ignored. That is the identity rule `rule_edits` uses for helpers
  (`function_key`), extended to local names. With the function's name
  ignored, every skill is one target, "skill": the same code added under a
  new name is still the same code;
- text (prompts, steps): similarity >= `rules.reject_similarity` (0.9) after
  lowercasing and collapsing whitespace (difflib's ratio);
- delete / merge: the same set of skills (or prompt).

Edit types: promote (a rule-based add of the player's helper), merge, delete,
edit (any other add or edit). The store covers the whole run of one game.

Change 4, "Rejected since current parent": what the Meta LLM is shown about
the versions rejected at the Gate whose parent is the current parent, and
the edits dropped at Validate in those rounds. It starts over when a new
parent is accepted. Scores and costs only; a fact-check drop shows its label,
never the evidence.

Deterministic, no model.
"""

from __future__ import annotations

import ast
import difflib
import json
import os
import re
from typing import Any

from evolve.harness import Harness

STORE_FILE = "rejected_edits.jsonl"
DEFAULT_SIMILARITY = 0.9
MAX_DIFF_LINES = 30          # per edit, in the Meta section
MAX_SECTION_CHARS = 9000     # the whole Meta section; the oldest diffs are shortened first
SHORT_DIFF_LINES = 6         # what a shortened diff keeps


# ---------------------------------------------------------------------------
# What an edit is, for matching
# ---------------------------------------------------------------------------


def edit_type(edit: dict[str, Any]) -> str:
    if edit["op"] == "add" and edit["target"] == "skill" and edit.get("replay_strip"):
        return "promote"
    if edit["op"] in ("merge", "delete"):
        return edit["op"]
    return "edit"


def edit_target(edit: dict[str, Any]) -> str:
    """The target matched on. Skills share one ("skill"): their names are
    ignored. A prompt is its key; the turn procedure is one target ("step"),
    since step indices shift as steps are added and removed."""
    if edit["target"] == "prompt":
        return f"prompt:{edit.get('name')}"
    return edit["target"]


class _Locals(ast.NodeVisitor):
    """Every name a function binds itself, in order of first appearance."""

    def __init__(self) -> None:
        self.names: list[str] = []

    def bind(self, name: str | None) -> None:
        if name and name not in self.names:
            self.names.append(name)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.bind(node.name)
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.bind(node.name)
        self.generic_visit(node)

    def visit_arg(self, node: ast.arg) -> None:
        self.bind(node.arg)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.bind(node.id)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        self.bind(node.name)
        self.generic_visit(node)

    def visit_alias(self, node: ast.alias) -> None:
        self.bind((node.asname or node.name).split(".")[0])


class _Rename(ast.NodeTransformer):
    def __init__(self, mapping: dict[str, str]) -> None:
        self.mapping = mapping

    def visit_Name(self, node: ast.Name) -> ast.Name:
        node.id = self.mapping.get(node.id, node.id)
        return node

    def visit_arg(self, node: ast.arg) -> ast.arg:
        node.arg = self.mapping.get(node.arg, node.arg)
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        node.name = self.mapping.get(node.name, node.name)
        return self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
        node.name = self.mapping.get(node.name, node.name)
        return self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> ast.AST:
        if node.name:
            node.name = self.mapping.get(node.name, node.name)
        return self.generic_visit(node)

    def visit_alias(self, node: ast.alias) -> ast.alias:
        if node.asname:
            node.asname = self.mapping.get(node.asname, node.asname)
        return node


def canonical_code(source: str) -> str:
    """A skill's code with its docstring, comments, layout and every name it
    binds itself replaced by position. Free names (the sandbox API, other
    skills, modules) are kept: they are what the code does."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return normalise_text(source)
    node = next((n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))), None)
    if node is None:
        return normalise_text(source)
    body = node.body
    if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) \
            and isinstance(body[0].value.value, str):
        node.body = body[1:] or [ast.Pass()]
    finder = _Locals()
    finder.visit(node)
    mapping = {name: f"_v{i}" for i, name in enumerate(finder.names)}
    renamed = _Rename(mapping).visit(node)
    return ast.unparse(ast.fix_missing_locations(renamed))


def normalise_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").lower()).strip()


def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def content_key(edit: dict[str, Any], parent: Harness | None) -> tuple[str, Any]:
    """(kind, normalised content): kind is code, text or set."""
    target, op = edit["target"], edit["op"]
    if op in ("delete", "merge") and target in ("skill", "prompt"):
        names = edit.get("names") if op == "merge" else [edit.get("name")]
        return "set", sorted(str(n) for n in names or [])
    if target == "skill":
        return "code", canonical_code(edit.get("content") or "")
    if target == "step" and op == "delete":
        # The step it removes, in the parent's numbering.
        index = edit.get("index")
        text = ""
        if parent is not None and isinstance(index, int) and 1 <= index <= len(parent.steps):
            text = parent.steps[index - 1]
        return "text", normalise_text(text)
    return "text", normalise_text(edit.get("content") or "")


def matches(kind: str, a: Any, b: Any, threshold: float) -> float | None:
    """The similarity if `a` repeats `b`, else None."""
    if kind == "text":
        score = 1.0 if a == b else similarity(a, b)
        return score if score >= threshold else None
    return 1.0 if a == b else None


# ---------------------------------------------------------------------------
# The store
# ---------------------------------------------------------------------------


class RejectedStore:
    """`rejected_edits.jsonl`: one line per rejected edit, append-only.

    Lines are keyed by id, so writing the same rejection twice (a stage run
    again after a cut) adds nothing."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.entries: list[dict[str, Any]] = []
        if os.path.exists(path):
            with open(path, encoding="utf-8") as handle:
                self.entries = [json.loads(line) for line in handle if line.strip()]
        self._ids = {e["id"] for e in self.entries}

    def add(self, entry: dict[str, Any]) -> bool:
        if entry["id"] in self._ids:
            return False
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        self.entries.append(entry)
        self._ids.add(entry["id"])
        return True

    def match(self, edit: dict[str, Any], parent: Harness | None,
              threshold: float = DEFAULT_SIMILARITY) -> tuple[dict[str, Any], float] | None:
        """The earlier rejected edit this one repeats (the closest; the
        earliest of equals), with the similarity."""
        kind, content = content_key(edit, parent)
        kind_type, target = edit_type(edit), edit_target(edit)
        best: tuple[dict[str, Any], float] | None = None
        for entry in self.entries:
            if entry["type"] != kind_type or entry["target"] != target or entry["kind"] != kind:
                continue
            score = matches(kind, content, entry["content"], threshold)
            if score is not None and (best is None or score > best[1]):
                best = (entry, score)
        return best


def make_entry(entry_id: str, round_index: int, version: str | None, edit: dict[str, Any],
               parent: Harness | None, rejected_by: str, **extra: Any) -> dict[str, Any]:
    kind, content = content_key(edit, parent)
    return {
        "id": entry_id, "round": round_index, "version": version,
        "type": edit_type(edit), "target": edit_target(edit), "op": edit["op"],
        "name": edit.get("name") if edit["target"] != "step" else (edit.get("index") or edit.get("indices")),
        "source": edit.get("source"), "kind": kind, "content": content,
        "rejected_by": rejected_by, **extra,
    }


def _attempts(rdir: str) -> list[dict[str, Any]]:
    for name in ("validation.json", "attempts.json"):
        path = os.path.join(rdir, name)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
            return data["attempts"] if isinstance(data, dict) else data
    return []


def sync(store: RejectedStore, root: str, archive: dict[str, Any], load_parent: Any) -> int:
    """Bring the store up to date with what the run directory records:
    every Validate drop in every round's attempts, and every edit of every
    version rejected at the Gate. Idempotent. `load_parent(name)` returns a
    harness (for the text of a deleted step). Returns lines added."""
    added = 0
    decisions = {r["round"]: r for r in archive.get("rounds") or []}
    rounds = sorted({int(d.split("_")[1]) for d in os.listdir(os.path.join(root, "reports"))
                     if d.startswith("round_") and d.split("_")[1].isdigit()}) \
        if os.path.isdir(os.path.join(root, "reports")) else []
    parents: dict[str, Harness | None] = {}

    def parent_of(name: str | None) -> Harness | None:
        if name is None:
            return None
        if name not in parents:
            try:
                parents[name] = load_parent(name)
            except (OSError, KeyError, ValueError):
                parents[name] = None
        return parents[name]

    for round_index in rounds:
        if round_index == 0:
            continue
        rdir = os.path.join(root, "reports", f"round_{round_index}")
        attempts = _attempts(rdir)
        decision = decisions.get(round_index)
        version = f"v{round_index}"
        parent_name = (decision or {}).get("parent_before")
        if parent_name is None and attempts:
            # Not gated yet: the parent is the archive's current one.
            last = (archive.get("rounds") or [{}])[-1]
            parent_name = last.get("parent_after")
        parent = parent_of(parent_name)
        for attempt in attempts:
            if "dropped" not in attempt:
                continue
            for item in attempt["dropped"]:
                edit = item.get("edit")
                if item.get("stage") == "propose" or not _canonical(edit):
                    continue  # over the edit cap (never validated), or malformed
                index = item["id"].split("-e")[-1]
                added += store.add(make_entry(
                    f"r{round_index}-a{attempt['attempt']}-e{index}", round_index, version, edit, parent,
                    f"validate: {item['stage']}", attempt=attempt["attempt"], edit_id=item["id"],
                    what=item.get("what"), **({"repeat_of": item["repeat_of"]} if item.get("repeat_of") else {})))
        if decision and decision.get("decision") == "rejected" and attempts:
            final = attempts[-1]
            entry = next((v for v in archive["versions"] if v["version"] == decision["child"]), None)
            reason = ((entry or {}).get("gate") or {}).get("reason", "")
            for item in final.get("passed") or []:
                index = item["id"].split("-e")[-1]
                added += store.add(make_entry(
                    f"r{round_index}-gate-e{index}", round_index, decision["child"], item["edit"], parent,
                    f"gate: {reason}", attempt=final["attempt"], edit_id=item["id"], what=item.get("what")))
    return added


def _canonical(edit: Any) -> bool:
    return isinstance(edit, dict) and edit.get("op") in ("add", "edit", "delete", "merge") \
        and edit.get("target") in ("skill", "prompt", "step")


# ---------------------------------------------------------------------------
# Change 4: "Rejected since current parent"
# ---------------------------------------------------------------------------

CHECK_NAMES = {
    "applies": "tests", "static tests": "tests", "load test": "tests", "skill test": "tests",
    "replay": "replay", "fact-check": "fact-check", "skill-name check": "skill-name",
    "state-change": "state-change", "repeat": "repeat",
}


def check_name(item: dict[str, Any]) -> str:
    stage = item.get("stage") or ""
    if stage == "replay" and "merge" in str(item.get("reason") or ""):
        return "merge-eq"
    return CHECK_NAMES.get(stage, stage)


def _before_after(edit: dict[str, Any], parent: Harness) -> tuple[str, str]:
    target, op = edit["target"], edit["op"]
    if target == "skill":
        if op == "merge":
            before = "\n".join(parent.skills.get(n, "") for n in edit.get("names") or [])
        else:
            before = parent.skills.get(edit.get("name") or "", "")
        return before, "" if op == "delete" else str(edit.get("content") or "")
    if target == "prompt":
        before = parent.prompts.get(edit.get("name") or "", "")
        return before, "" if op == "delete" else str(edit.get("content") or "")
    steps = parent.steps
    pick = (lambda i: steps[i - 1] if isinstance(i, int) and 1 <= i <= len(steps) else "")
    if op == "merge":
        before = "\n".join(pick(i) for i in edit.get("indices") or [])
    elif op == "add":
        before = ""
    else:
        before = pick(edit.get("index"))
    return before, "" if op == "delete" else str(edit.get("content") or "")


def edit_diff(edit: dict[str, Any], parent: Harness) -> list[str]:
    before, after = _before_after(edit, parent)
    lines = list(difflib.unified_diff(before.splitlines(), after.splitlines(), lineterm="", n=1))
    return [line for line in lines if not line.startswith(("---", "+++"))]


def describe_edit(edit: dict[str, Any]) -> str:
    where = (edit.get("indices") or edit.get("index")) if edit["target"] == "step" else \
        (", ".join(edit.get("names") or []) + f" -> {edit.get('name')}" if edit["op"] == "merge"
         else edit.get("name"))
    return f"{edit['op']} {edit['target']} {where} (type {edit_type(edit)}, from {edit.get('source', 'meta')})"


def rejected_since_parent(archive: dict[str, Any], root: str, parent: Harness,
                          parent_entry: dict[str, Any]) -> dict[str, Any]:
    """The data of the section, oldest first. Rounds whose parent was the
    current parent: Gate-rejected children and every Validate drop."""
    by_seed = {e["seed"]: e.get("score") for e in parent_entry.get("episodes") or []}
    out: dict[str, Any] = {
        "parent": parent.version, "parent_score_mean": parent_entry.get("score_mean"),
        "parent_scores": [by_seed[s] for s in sorted(by_seed)], "parent_cost_mean": parent_entry.get("cost_mean"),
        "seeds": sorted(by_seed), "versions": [], "dropped": [],
    }
    for decision in archive.get("rounds") or []:
        if decision.get("parent_before") != parent.version:
            continue
        round_index = decision["round"]
        attempts = _attempts(os.path.join(root, "reports", f"round_{round_index}"))
        if decision.get("decision") == "rejected" and attempts:
            entry = next((v for v in archive["versions"] if v["version"] == decision["child"]), {})
            scores = {e["seed"]: e.get("score") for e in entry.get("episodes") or []}
            out["versions"].append({
                "version": decision["child"], "round": round_index,
                "score_mean": entry.get("score_mean"), "scores": [scores.get(s) for s in sorted(by_seed)],
                "cost_mean": entry.get("cost_mean"), "gate_reason": (entry.get("gate") or {}).get("reason"),
                "edits": [{"what": describe_edit(i["edit"]), "diff": edit_diff(i["edit"], parent)}
                          for i in attempts[-1].get("passed") or []],
            })
        for attempt in attempts:
            for item in attempt.get("dropped") or []:
                edit = item.get("edit")
                if item.get("stage") == "propose" or not _canonical(edit):
                    continue
                check = check_name(item)
                dropped = {"round": round_index, "attempt": attempt["attempt"], "what": describe_edit(edit),
                           "check": check, "diff": edit_diff(edit, parent)}
                if check == "fact-check":
                    label = (item.get("factcheck") or {}).get("verdict") or "false"
                    dropped["label"] = label  # the label only, never the evidence
                else:
                    dropped["reason"] = str(item.get("reason") or "")[:160]
                out["dropped"].append(dropped)
    return out


def _num(value: Any) -> str:
    return "?" if value is None else f"{value:.3f}".rstrip("0").rstrip(".") if isinstance(value, float) else str(value)


def render_section(data: dict[str, Any]) -> str:
    """The section the Meta LLM reads. Every rejected version keeps its
    summary line; diffs are capped per edit, and the oldest are shortened
    (then left out) first if the section is too long."""
    head = (f"REJECTED SINCE CURRENT PARENT ({data['parent']}), oldest first. Everything tried on top of "
            f"{data['parent']} that failed: versions rejected at the Gate and edits dropped at Validate. The "
            "repeat check drops an edit that repeats any of these.")
    if not data["versions"] and not data["dropped"]:
        return head + "\nNone so far."
    seeds = ", ".join(str(s) for s in data["seeds"])
    gate_items: list[dict[str, Any]] = []
    for version in data["versions"]:
        gate_items.append({"round": version["round"], "diff": None, "text": (
            f"- {version['version']} (round {version['round']}): rejected at the Gate: {version['gate_reason']}. "
            f"Progress {_num(version['score_mean'])} vs parent {_num(data['parent_score_mean'])} "
            f"(seeds {seeds}: {', '.join(_num(s) for s in version['scores'])} vs "
            f"{', '.join(_num(s) for s in data['parent_scores'])}); cost {_num(version['cost_mean'])} vs "
            f"{_num(data['parent_cost_mean'])}. Its edits:")})
        for edit in version["edits"]:
            gate_items.append({"round": version["round"], "text": f"    - {edit['what']}", "diff": edit["diff"]})
    drop_items = []
    for item in data["dropped"]:
        why = f"fact-check ({item['label']})" if item["check"] == "fact-check" else \
            f"{item['check']}: {item['reason']}"
        drop_items.append({"round": item["round"], "text": f"- round {item['round']}: {item['what']}: dropped by {why}",
                           "diff": item["diff"]})
    everything = gate_items + drop_items

    def build(limits: list[int | None]) -> str:
        lines = [head, f"Versions rejected at the Gate ({len(data['versions'])}):" if gate_items
                 else "Versions rejected at the Gate: none."]
        for i, item in enumerate(everything):
            if i == len(gate_items):
                lines.append(f"Edits dropped at Validate ({len(drop_items)}):")
            lines.append(item["text"])
            diff, limit = item["diff"], limits[i]
            if not diff:
                continue
            if limit == 0:
                lines.append("        (diff left out: section too long)")
                continue
            shown = diff[:MAX_DIFF_LINES if limit is None else limit]
            lines.extend("        " + line for line in shown)
            if len(diff) > len(shown):
                lines.append(f"        ... ({len(diff) - len(shown)} more diff lines)")
        if not drop_items:
            lines.append("Edits dropped at Validate: none.")
        return "\n".join(lines)

    limits: list[int | None] = [None] * len(everything)
    text = build(limits)
    oldest_first = sorted(range(len(everything)), key=lambda i: (everything[i]["round"], i))
    for cap in (SHORT_DIFF_LINES, 0):
        for i in oldest_first:
            if len(text) <= MAX_SECTION_CHARS:
                return text
            if everything[i]["diff"]:
                limits[i] = cap
                text = build(limits)
    return text
