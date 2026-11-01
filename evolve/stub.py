"""Offline stand-ins for the player and Meta LLMs, for the self-test only.

Like #8's harness/stub_model.py: NOT part of the experiment, and nothing they
produce is reported as a finding. They exist so the action loop, the sandbox,
replay, and all five meta-harness stages can run end to end with no model calls.

The stub player reads AVAILABLE ACTIONS out of the real prompt, so a broken
prompt shows up as a broken stub run. It also exercises the paths the real
model will hit: an inline helper defined and reused across turns (so Analyze
has something to promote), skill calls, a cell that raises, and a reply with no
code block (the parse-failure / retry path).
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass, field

from harness.model import ModelResponse, Usage

AVAILABLE_RE = re.compile(r"^AVAILABLE ACTIONS: (.*)$", re.MULTILINE)
TURN_RE = re.compile(r"^STATUS: turn (\d+)/", re.MULTILINE)

HELPER = '''def mover_centre(g=None):
    """Centroid of the smallest object (stub helper)."""
    objs = objects(g)
    if not objs:
        return None
    o = min(objs, key=lambda o: o["size"])
    return tuple(o["centroid"])
'''


@dataclass
class StubPlayer:
    seed: int = 0
    model: str = "stub-player"
    usage: Usage = field(default_factory=Usage)
    _calls: int = 0

    def complete(self, messages, max_tokens=None) -> ModelResponse:
        self._calls += 1
        prompt = messages[-1]["content"]
        turn = int(TURN_RE.search(prompt).group(1)) if TURN_RE.search(prompt) else 0
        rng = random.Random(hash((self.seed, turn, "FORMAT ERROR" in prompt)) & 0xFFFFFFFF)
        match = AVAILABLE_RE.search(prompt)
        available = [
            int(tok.replace("ACTION", ""))
            for tok in (match.group(1).split(", ") if match else [])
            if tok.startswith("ACTION")
        ] or [1]

        if turn == 3 and "FORMAT ERROR" not in prompt:
            text = "I will think about it without code."  # parse-failure path
        else:
            lines = []
            if turn % 4 == 0:
                lines.append(HELPER)  # an inline helper, re-defined every 4 turns
            if turn % 5 == 1:
                lines.append("cands = player_detector()")
            if turn == 2:
                lines.append("x = [1][3]")  # a cell that raises
            moves = [rng.choice(available) for _ in range(rng.randint(1, 6))]
            for move in moves:
                if move == 6:
                    lines.append(f"action(6, x={rng.randint(0, 63)}, y={rng.randint(0, 63)})")
                else:
                    lines.append(f"action({move})")
            lines.append("print(mover_centre())" if turn >= 4 else "print(status())")
            lines.append(f'notes = "stub turn {turn}"')
            text = "OBSERVE: stub.\n```python\n" + "\n".join(lines) + "\n```"
        tokens_in = len(json.dumps(messages)) // 4
        tokens_out = len(text) // 4
        self.usage.add(tokens_in, tokens_out)
        return ModelResponse(text=text, tokens_in=tokens_in, tokens_out=tokens_out, latency_ms=1)

    def preflight(self) -> dict:
        return {"stub": True}


@dataclass
class StubMeta:
    """Returns a fixed set of edits, including ones Validate must reject."""

    model: str = "stub-meta"
    usage: Usage = field(default_factory=Usage)

    def complete(self, messages, max_tokens=None) -> ModelResponse:
        edits = {
            "edits": [
                {
                    "op": "edit", "target": "step", "index": 4,
                    "content": "PLAN: choose up to {cap} actions; prefer the ones that moved the mover.",
                    "rationale": "stub: step edit",
                },
                {
                    "op": "add", "target": "prompt", "name": "strategy",
                    "content": "STRATEGY\n- Stub strategy line.",
                    "rationale": "stub: prompt add",
                },
                {
                    "op": "add", "target": "skill", "name": "count_colour",
                    "content": 'def count_colour(c, g=None):\n    """Number of cells of colour c."""\n'
                               '    g = grid() if g is None else np.asarray(g)\n    return int((g == c).sum())\n',
                    "test": "assert count_colour(4) >= 0",
                    "rationale": "stub: valid skill",
                },
                {
                    "op": "add", "target": "skill", "name": "evil",
                    "content": 'def evil():\n    """Reads a file."""\n    return open("x").read()\n',
                    "test": "evil()",
                    "rationale": "stub: must be dropped by the AST filter",
                },
                {
                    "op": "delete", "target": "prompt", "name": "format",
                    "rationale": "stub: must be dropped, format is core",
                },
            ]
        }
        text = "Here are my edits:\n```json\n" + json.dumps(edits, indent=1) + "\n```"
        self.usage.add(1000, len(text) // 4)
        return ModelResponse(text=text, tokens_in=1000, tokens_out=len(text) // 4, latency_ms=1)
