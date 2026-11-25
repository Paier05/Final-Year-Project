"""Per-game goal-progress scorers (issue #15).

Everything learned about a game while building its scorer lives under
scorer/<game>/: GAME_NOTES.md, the scorer and the fact-check's ground truth.
None of it reaches the player or the Meta LLM: the player's sandbox has no
file access, `read_state` output goes to the trajectory and never to the
sandbox API, and for these games the Analyze report and the Meta prompt carry
the score only (DISCLOSE_PARTS = False; the user's choice, 2026-11-25).

ls20 keeps #14's scorer, evolve/goal_score.py, unchanged.

Each scorer module provides:
    PARTS, DEFAULT_WEIGHTS
    DISCLOSE_PARTS          whether Analyze and the Meta prompt may name the parts
    read_state(env)         the goal-relevant game state, logged after every action
    score_episode(records, game_id, weights) -> result dict (score, cleared, parts, ...)
    describe_failure(result) -> one line, or None when parts are not disclosed
    ground_truth(game_id)   the fact-check's GroundTruth (ls20: evolve/factcheck.py's own)
"""

from __future__ import annotations

import importlib
from types import ModuleType

# Short name -> the game id the run uses (environment_files/<short>/<version>/).
GAME_IDS = {
    "ls20": "ls20-9607627b",
    "ft09": "ft09-0d8bbf25",
    "vc33": "vc33-5430563c",
}

_MODULES = {
    "ls20": "evolve.goal_score",
    "ft09": "scorer.ft09.score",
    "vc33": "scorer.vc33.score",
}


def short_name(game_id: str) -> str:
    return str(game_id).split("-")[0].lower()


def game_id(name: str) -> str:
    """'ft09' or 'ft09-0d8bbf25' -> 'ft09-0d8bbf25'."""
    short = short_name(name)
    if short not in GAME_IDS:
        raise ValueError(f"no scorer for game {name!r}; known: {', '.join(sorted(GAME_IDS))}")
    return GAME_IDS[short]


def for_game(game: str) -> ModuleType:
    short = short_name(game)
    if short not in _MODULES:
        raise ValueError(f"no scorer for game {game!r}; known: {', '.join(sorted(_MODULES))}")
    return importlib.import_module(_MODULES[short])


def discloses_parts(game: str | None) -> bool:
    """True for ls20 (and when no game is given: #14's behaviour)."""
    return True if game is None else bool(getattr(for_game(game), "DISCLOSE_PARTS", True))
