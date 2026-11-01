"""Public game enumeration and the frozen dev/test split.

The split is computed from a committed seed so it is reproducible, and it is
written to results/games.json. Skills are mined from the dev games only, so this
file is the thing that keeps the test split honest.
"""

from __future__ import annotations

import json
import os
import random
from typing import Any

RESULTS_DIR = "results"
GAMES_PATH = os.path.join(RESULTS_DIR, "games.json")


def short_id(game_id: str) -> str:
    """'ls20-9607627b' -> 'ls20'. The issue names dev games in short form."""
    return game_id.split("-", 1)[0].lower()


def fetch_games(arc_api_key: str = "") -> list[dict[str, Any]]:
    """Enumerate public games from the ARC API via the official toolkit."""
    import arc_agi

    arcade = arc_agi.Arcade(arc_api_key=arc_api_key)
    environments = arcade.get_environments()
    games: list[dict[str, Any]] = []
    for info in environments:
        baselines = list(info.baseline_actions or [])
        games.append(
            {
                "game_id": info.game_id,
                "short_id": short_id(info.game_id),
                "title": info.title,
                "tags": list(info.tags or []),
                "n_levels": len(baselines) if baselines else None,
                # baseline_actions is per level; index 0 is level 1.
                "human_baseline_actions_level1": baselines[0] if baselines else None,
                "baseline_actions_all_levels": baselines,
            }
        )
    games.sort(key=lambda g: g["game_id"])
    return games


def build_split(
    games: list[dict[str, Any]],
    seed: int,
    forced_dev: list[str],
    dev_fraction_of_rest: float = 0.5,
) -> dict[str, list[str]]:
    """Split games into dev/test.

    The issue mandates ls20, ft09 and vc33 in dev, plus about half the rest.
    The remainder is test. Selection of "the rest" is a seeded shuffle so it is
    reproducible from the committed seed.
    """
    forced = {name.lower() for name in forced_dev}
    all_ids = [g["game_id"] for g in games]
    by_short = {short_id(g): g for g in all_ids}

    missing = sorted(forced - set(by_short))
    if missing:
        raise RuntimeError(
            f"Issue-mandated dev games are not in the public list: {missing}. "
            f"Available short ids: {sorted(by_short)}"
        )

    dev = [by_short[name] for name in sorted(forced)]
    rest = [gid for gid in all_ids if gid not in set(dev)]

    rng = random.Random(seed)
    shuffled = list(rest)
    rng.shuffle(shuffled)
    n_dev_extra = round(len(shuffled) * dev_fraction_of_rest)
    dev_extra = sorted(shuffled[:n_dev_extra])
    test = sorted(shuffled[n_dev_extra:])

    return {
        "dev": sorted(dev + dev_extra),
        "test": test,
    }


def write_games_file(
    games: list[dict[str, Any]],
    split: dict[str, list[str]],
    split_seed: int,
    forced_dev: list[str],
    path: str = GAMES_PATH,
) -> dict[str, Any]:
    payload = {
        "n_games": len(games),
        "split_seed": split_seed,
        "forced_dev": forced_dev,
        "split": split,
        "games": games,
    }
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
    return payload


def load_games_file(path: str = GAMES_PATH) -> dict[str, Any]:
    if not os.path.exists(path):
        raise RuntimeError(
            f"{path} not found. Run `python run.py --stage games` first so the "
            "game list and split are frozen before any run."
        )
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def split_of(games_file: dict[str, Any], game_id: str) -> str:
    if game_id in games_file["split"]["dev"]:
        return "dev"
    if game_id in games_file["split"]["test"]:
        return "test"
    return "unknown"


def baseline_for(games_file: dict[str, Any], game_id: str) -> int | None:
    for game in games_file["games"]:
        if game["game_id"] == game_id:
            return game.get("human_baseline_actions_level1")
    return None
