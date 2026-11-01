"""Offline stub policy, for verifying the harness without calling a model.

This is NOT part of the experiment and its results are never reported as
findings. It exists so the loop, the trajectory logging, the skill miner and
the figure scripts can all be exercised end to end while the real model
endpoint is unavailable.

It deliberately reads `AVAILABLE ACTIONS` out of the real prompt text, so a
malformed prompt shows up here as a broken stub run. It also emits a malformed
reply at a fixed rate so the parse-failure / retry / fallback path is covered.
"""

from __future__ import annotations

import random
import re
import time
from dataclasses import dataclass, field

from .actions import ID_TO_NAME, MAX_COORD
from .model import ModelResponse, Usage

AVAILABLE_RE = re.compile(r"^AVAILABLE ACTIONS: (.*)$", re.MULTILINE)


@dataclass
class StubClient:
    """Random-but-legal policy with the same surface as ModelClient."""

    seed: int = 0
    malformed_every: int = 17
    base_url: str = "stub://offline"
    model: str = "stub-random-policy"
    usage: Usage = field(default_factory=Usage)
    _calls: int = 0
    _rng: random.Random | None = None

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)

    def preflight(self) -> dict[str, object]:
        return {"stub": True}

    def complete(self, messages, max_tokens=None) -> ModelResponse:  # noqa: ANN001
        self._calls += 1
        rng = self._rng
        assert rng is not None

        user = messages[-1]["content"]
        if isinstance(user, list):
            user = next(
                (part.get("text", "") for part in user if part.get("type") == "text"),
                "",
            )

        match = AVAILABLE_RE.search(user)
        names = []
        if match:
            names = [n.strip() for n in match.group(1).split(",") if n.strip()]
        legal = [n for n in names if n in {v for v in ID_TO_NAME.values()}]
        legal = [n for n in legal if n != "RESET"] or ["ACTION5"]

        time.sleep(0)  # no network; keeps the shape of a real call

        if self._calls % self.malformed_every == 0:
            text = "I think I should press the button now."  # exercises the retry path
        else:
            action = rng.choice(legal)
            if action == "ACTION6":
                args = {
                    "x": rng.randint(0, MAX_COORD),
                    "y": rng.randint(0, MAX_COORD),
                }
            else:
                args = {}
            text = (
                '{"thought": "stub policy exploring", "action": "%s", "args": %s, '
                '"scratchpad": "stub run; call %d"}'
                % (action, str(args).replace("'", '"'), self._calls)
            )

        tokens_in = max(1, len(user) // 4)
        tokens_out = max(1, len(text) // 4)
        self.usage.add(tokens_in, tokens_out)
        return ModelResponse(
            text=text,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=1,
            raw_finish_reason="stop",
        )
