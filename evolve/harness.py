"""Harness versions: the `steps · prompts · skills/` the meta harness evolves.

A version lives in its own directory:

    results/evolve/harnesses/vN/
        manifest.json   version, parent, round, the edits that produced it
        prompts.json    ordered {key: text}; "system" and "format" are core
        steps.json      the turn procedure, one string per step
        skills/<name>.py  one function per file, preloaded into the sandbox

Everything the player sees is rendered from these files plus the fixed
sandbox API description, so two versions differ only in what is on disk.
"""

from __future__ import annotations

import ast
import copy
import json
import os
import shutil
from dataclasses import dataclass, field
from typing import Any

EVOLVE_DIR = os.path.join("results", "evolve")
HARNESS_ROOT = os.path.join(EVOLVE_DIR, "harnesses")

# Prompts that must always exist. They can be edited but not deleted, because
# the action loop depends on them (the rules and the reply format).
CORE_PROMPTS = ("system", "format")

# The sandbox API is code, not a harness component, so its description is fixed
# here rather than evolvable: editing the text could not change the behaviour.
API_DOC = """\
SANDBOX API (preloaded; your code runs in a persistent Python namespace)
- action(a, x=None, y=None) -> dict. Perform one game action. `a` is 1..7 for
  ACTION1..ACTION7, or 0 for RESET. ACTION6 needs x (column) and y (row), both
  in 0..63. Returns {{"action", "n_changed", "state", "levels_completed",
  "game_over", "effect"}}. At most {cap} actions per turn: a further call ends
  your cell. Calling an action that is not AVAILABLE raises an error and costs
  nothing.
- grid() -> numpy int array (rows x cols) of colour indices, current frame.
- objects(g=None) -> list of connected components of `g` (default: the current
  frame), background excluded, largest first. Each is {{"colour",
  "colour_name", "bbox": [r0, c0, r1, c1], "size", "centroid": [r, c]}}.
- diff(a, b) -> list of (row, col, old, new) for every cell that differs.
- status() -> dict: actions_used, actions_left, turn, turn_actions_left, state,
  levels_completed, available_actions, resets.
- history(n=10) -> the last n actions this episode, each {{"turn", "action",
  "args", "effect"}}.
- notes: a string shown back to you every turn. Assign to it to keep notes.
- COLOURS: dict colour index -> name.
- print(...) output is shown to you next turn (truncated at 4000 chars).
- np, math, collections, itertools, functools, heapq are preloaded. There is no
  file, network or randomness access, and no attribute starting with "_".
Variables and functions you define persist across turns."""


@dataclass
class Harness:
    version: str
    parent: str | None
    round_index: int
    prompts: dict[str, str]
    steps: list[str]
    skills: dict[str, str]  # name -> source
    edits: list[dict[str, Any]] = field(default_factory=list)

    # -- rendering ----------------------------------------------------------

    def render_system(self, actions_per_turn: int) -> str:
        parts: list[str] = [self.prompts["system"].strip()]
        for key, text in self.prompts.items():
            if key in CORE_PROMPTS or not text.strip():
                continue
            parts.append(text.strip())
        parts.append(self.render_steps(actions_per_turn))
        parts.append(API_DOC.format(cap=actions_per_turn))
        skills_doc = self.render_skills()
        if skills_doc:
            parts.append(skills_doc)
        parts.append(self.prompts["format"].strip())
        return "\n\n".join(parts)

    def render_steps(self, actions_per_turn: int) -> str:
        lines = ["TURN PROCEDURE (follow these steps every turn)"]
        for index, step in enumerate(self.steps, start=1):
            # replace, not format: an evolved step may legitimately contain
            # braces (a dict literal), which str.format would choke on.
            lines.append(f"{index}. {step.replace('{cap}', str(actions_per_turn)).strip()}")
        return "\n".join(lines)

    def render_skills(self) -> str:
        if not self.skills:
            return ""
        lines = [
            "SKILLS (preloaded functions; call them from your code)",
        ]
        for name in sorted(self.skills):
            signature, doc = skill_signature(self.skills[name])
            lines.append(f"- {signature}")
            for doc_line in doc.splitlines()[:6]:
                if doc_line.strip():
                    lines.append(f"    {doc_line.strip()}")
        return "\n".join(lines)

    # -- persistence --------------------------------------------------------

    @property
    def path(self) -> str:
        return os.path.join(HARNESS_ROOT, self.version)

    def save(self, root: str = HARNESS_ROOT) -> str:
        path = os.path.join(root, self.version)
        if os.path.exists(path):
            shutil.rmtree(path)
        os.makedirs(os.path.join(path, "skills"))
        _write_json(
            os.path.join(path, "manifest.json"),
            {
                "version": self.version,
                "parent": self.parent,
                "round": self.round_index,
                "prompt_order": list(self.prompts),
                "skills": sorted(self.skills),
                "n_steps": len(self.steps),
                "edits": self.edits,
            },
        )
        _write_json(os.path.join(path, "prompts.json"), self.prompts)
        _write_json(os.path.join(path, "steps.json"), self.steps)
        for name, source in self.skills.items():
            with open(os.path.join(path, "skills", f"{name}.py"), "w", encoding="utf-8") as handle:
                handle.write(source.rstrip() + "\n")
        return path

    def child(self, version: str, round_index: int) -> "Harness":
        """A deep copy that edits are applied to; the parent is never mutated."""
        return Harness(
            version=version,
            parent=self.version,
            round_index=round_index,
            prompts=copy.deepcopy(self.prompts),
            steps=list(self.steps),
            skills=dict(self.skills),
            edits=[],
        )


def load_harness(version: str, root: str = HARNESS_ROOT) -> Harness:
    path = os.path.join(root, version)
    with open(os.path.join(path, "manifest.json"), encoding="utf-8") as handle:
        manifest = json.load(handle)
    with open(os.path.join(path, "prompts.json"), encoding="utf-8") as handle:
        prompts = json.load(handle)
    with open(os.path.join(path, "steps.json"), encoding="utf-8") as handle:
        steps = json.load(handle)
    skills: dict[str, str] = {}
    skills_dir = os.path.join(path, "skills")
    for name in sorted(os.listdir(skills_dir)):
        if name.endswith(".py"):
            with open(os.path.join(skills_dir, name), encoding="utf-8") as handle:
                skills[name[:-3]] = handle.read()
    ordered = {key: prompts[key] for key in manifest.get("prompt_order", prompts) if key in prompts}
    return Harness(
        version=manifest["version"],
        parent=manifest.get("parent"),
        round_index=int(manifest.get("round", 0)),
        prompts=ordered,
        steps=steps,
        skills=skills,
        edits=manifest.get("edits", []),
    )


def skill_signature(source: str) -> tuple[str, str]:
    """(`name(args)`, docstring) of the first function in a skill's source."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return "<unparseable skill>", ""
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            args = ast.unparse(node.args)
            return f"{node.name}({args})", ast.get_docstring(node) or ""
    return "<no function>", ""


def _write_json(path: str, payload: Any) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
