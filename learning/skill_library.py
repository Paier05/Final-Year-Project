"""Load the validated skill library and expose it to the Round 1 harness."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from harness.prompt import render_skills_block, render_tools_block
from learning.mine import INDEX_PATH
from learning.modules import MODULES, run_module


@dataclass
class SkillLibrary:
    skills: list[dict[str, Any]] = field(default_factory=list)
    call_counts: dict[str, int] = field(default_factory=dict)

    @property
    def modules(self) -> list[dict[str, Any]]:
        return [s for s in self.skills if s.get("kind") == "module"]

    def prompt_block(self) -> str:
        return render_skills_block(self.skills)

    def tools_block(self) -> str:
        """Only modules that passed validation are offered as callable tools."""
        described = []
        for skill in self.modules:
            entry = MODULES.get(skill["name"])
            if entry is None:
                continue
            described.append(
                {
                    "name": skill["name"],
                    "description": entry["description"],
                    "params": entry["params"],
                    "returns": entry["returns"],
                }
            )
        return render_tools_block(described)

    def run_module(
        self, name: str, params: dict[str, Any], grid: np.ndarray
    ) -> str:
        allowed = {s["name"] for s in self.modules}
        if name not in allowed:
            return (
                f"module {name!r} is not in the validated library; "
                f"available: {', '.join(sorted(allowed)) or 'none'}"
            )
        self.call_counts[name] = self.call_counts.get(name, 0) + 1
        return run_module(name, params, grid)


def load_library(path: str = INDEX_PATH) -> SkillLibrary:
    if not os.path.exists(path):
        return SkillLibrary()
    with open(path, encoding="utf-8") as handle:
        index = json.load(handle)

    skills: list[dict[str, Any]] = []
    for entry in index.get("skills", []):
        file_path = os.path.join(os.path.dirname(path), entry["file"])
        if os.path.exists(file_path):
            with open(file_path, encoding="utf-8") as handle:
                skills.append(json.load(handle))
        else:
            skills.append(entry)
    return SkillLibrary(skills=skills)
