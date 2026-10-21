"""Driver for issue #8.

    python run.py --stage games        # freeze the public game list + split
    python run.py --stage preflight    # check model credentials only
    python run.py --round 0            # baseline sweep
    python run.py --stage skills       # mine + validate skills from dev data
    python run.py --round 1            # skills sweep
    python run.py --stage analyse      # summary.csv + figures

`--round N` runs the sweep for that round. Everything is reproducible from
config.yaml plus results/games.json.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any

import yaml

from harness import games as games_mod
from harness.episode import run_episode
from harness.model import AbortExperiment, ModelClient, load_api_key

RESULTS_DIR = "results"
EPISODES_PATH = os.path.join(RESULTS_DIR, "episodes.jsonl")
RUNINFO_PATH = os.path.join(RESULTS_DIR, "run_info.json")


def load_config(path: str = "config.yaml") -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def make_client(config: dict[str, Any]) -> ModelClient:
    model_cfg = config["model"]
    limits = config.get("limits", {})
    return ModelClient(
        base_url=model_cfg["base_url"],
        model=model_cfg["model"],
        api_key=load_api_key(),
        temperature=float(model_cfg["temperature"]),
        top_p=float(model_cfg["top_p"]),
        max_tokens=int(model_cfg["max_tokens"]),
        thinking=str(model_cfg.get("thinking", "low")),
        request_timeout_s=int(model_cfg["request_timeout_s"]),
        max_transient_retries=int(model_cfg["max_transient_retries"]),
        abort_after_consecutive_rate_limits=int(
            limits.get("abort_after_consecutive_rate_limits", 3)
        ),
        global_token_cap=int(limits.get("global_token_cap", 40_000_000)),
    )


# ---------------------------------------------------------------------------
# Stages
# ---------------------------------------------------------------------------


def stage_games(config: dict[str, Any]) -> None:
    split_cfg = config["split"]
    print("Enumerating public ARC-AGI-3 games via the arc-agi toolkit...")
    games = games_mod.fetch_games()
    split = games_mod.build_split(
        games,
        seed=int(split_cfg["seed"]),
        forced_dev=list(split_cfg["forced_dev"]),
        dev_fraction_of_rest=float(split_cfg["dev_fraction_of_rest"]),
    )
    payload = games_mod.write_games_file(
        games, split, int(split_cfg["seed"]), list(split_cfg["forced_dev"])
    )
    print(f"\n{payload['n_games']} public games written to {games_mod.GAMES_PATH}")
    print(f"  dev  ({len(split['dev'])}): {', '.join(games_mod.short_id(g) for g in split['dev'])}")
    print(f"  test ({len(split['test'])}): {', '.join(games_mod.short_id(g) for g in split['test'])}")

    missing_baseline = [
        g["short_id"] for g in games if not g["human_baseline_actions_level1"]
    ]
    if missing_baseline:
        print(f"  no level-1 human baseline for: {', '.join(missing_baseline)}")
    else:
        print("  every game has a level-1 human baseline, so level_score is defined")

    n_episodes = len(games) * len(config["run"]["seeds"])
    print(
        f"\nSweep size per round: {len(games)} games x "
        f"{len(config['run']['seeds'])} seeds = {n_episodes} episodes, "
        f"up to {n_episodes * int(config['budget']['max_actions'])} model calls."
    )


def stage_preflight(config: dict[str, Any]) -> None:
    client = make_client(config)
    print(f"Checking {client.base_url} for model {client.model} ...")
    info = client.preflight()
    print("OK:", json.dumps(info)[:500])


def _append_episode(row: dict[str, Any]) -> None:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(EPISODES_PATH, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")


def _completed_keys(round_index: int) -> set[tuple[str, int]]:
    """(game, seed) pairs already recorded for this round, so a run resumes."""
    done: set[tuple[str, int]] = set()
    if not os.path.exists(EPISODES_PATH):
        return done
    with open(EPISODES_PATH, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if int(row.get("round", -1)) == round_index and not row.get("error"):
                done.add((row["game"], int(row["seed"])))
    return done


def stage_round(
    config: dict[str, Any],
    round_index: int,
    only_games: list[str] | None = None,
    only_seeds: list[int] | None = None,
    resume: bool = True,
) -> None:
    import arc_agi

    games_file = games_mod.load_games_file()
    client = make_client(config)
    print(f"Preflight against {client.base_url} ...")
    client.preflight()
    print("Credentials OK.\n")

    skills_block = tools_block = None
    module_runner = None
    if round_index >= 1:
        from learning.skill_library import load_library

        library = load_library()
        if not library.skills:
            raise SystemExit(
                "Round 1 needs a skill library. Run `python run.py --stage skills` "
                "after Round 0 has produced dev trajectories."
            )
        skills_block = library.prompt_block()
        tools_block = library.tools_block()
        module_runner = library.run_module
        print(
            f"Loaded {len(library.skills)} validated skills "
            f"({len(library.modules)} callable modules)."
        )

    all_games = [g["game_id"] for g in games_file["games"]]
    target_games = only_games or all_games
    seeds = only_seeds or list(config["run"]["seeds"])
    done = _completed_keys(round_index) if resume else set()

    arcade = arc_agi.Arcade()
    started = time.monotonic()
    aborted: str | None = None
    n_run = 0

    try:
        for game_id in target_games:
            split = games_mod.split_of(games_file, game_id)
            baseline = games_mod.baseline_for(games_file, game_id)
            for seed in seeds:
                if (game_id, seed) in done:
                    print(f"[round {round_index}] {game_id} seed {seed}: already done")
                    continue
                print(
                    f"[round {round_index}] {game_id} ({split}) seed {seed} ... ",
                    end="",
                    flush=True,
                )
                result = run_episode(
                    arcade=arcade,
                    client=client,
                    game_id=game_id,
                    seed=seed,
                    round_index=round_index,
                    split=split,
                    config=config,
                    human_baseline_actions=baseline,
                    skills_block=skills_block,
                    tools_block=tools_block,
                    module_runner=module_runner,
                )
                row = result.as_row()
                row["skill_calls_by_name"] = result.skill_calls_by_name
                _append_episode(row)
                n_run += 1
                print(
                    f"{'SOLVED' if result.solved else 'unsolved'} "
                    f"({result.end_reason}) actions={result.actions_used} "
                    f"resets={result.resets_used} "
                    f"tok={result.tokens_in + result.tokens_out} "
                    f"{result.wall_time_s:.0f}s"
                    + (f" ERROR {result.error}" if result.error else "")
                )
    except AbortExperiment as error:
        aborted = str(error)
    except KeyboardInterrupt:
        aborted = "interrupted by user"

    elapsed = time.monotonic() - started
    info = {
        "round": round_index,
        "episodes_run_this_invocation": n_run,
        "wall_time_s": round(elapsed, 1),
        "model": config["model"],
        "budget": config["budget"],
        "observation": config["observation"],
        "usage": client.usage.as_dict(),
        "aborted": aborted,
    }
    os.makedirs(RESULTS_DIR, exist_ok=True)
    existing: list[dict[str, Any]] = []
    if os.path.exists(RUNINFO_PATH):
        with open(RUNINFO_PATH, encoding="utf-8") as handle:
            existing = json.load(handle)
    existing.append(info)
    with open(RUNINFO_PATH, "w", encoding="utf-8") as handle:
        json.dump(existing, handle, indent=2)

    print(f"\nRound {round_index}: ran {n_run} episodes in {elapsed / 60:.1f} min")
    print(f"Token usage this invocation: {client.usage.as_dict()}")
    if aborted:
        print(f"\n*** EXPERIMENT STOPPED: {aborted}", file=sys.stderr)
        raise SystemExit(2)


def stage_skills(config: dict[str, Any]) -> None:
    from learning.mine import mine_and_validate

    games_file = games_mod.load_games_file()
    report = mine_and_validate(
        dev_games=games_file["split"]["dev"],
        test_games=games_file["split"]["test"],
        round_index=0,
    )
    print(json.dumps(report, indent=2)[:4000])


def stage_analyse(config: dict[str, Any]) -> None:
    from analysis.summarise import build_summary
    from analysis.figures import build_all_figures

    summary_path = build_summary()
    print(f"wrote {summary_path}")
    paths = build_all_figures()
    for path in paths:
        print(f"wrote {path}")


# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="ARC-AGI-3 Level 1 experiment (#8)")
    parser.add_argument("--round", type=int, choices=[0, 1], default=None)
    parser.add_argument(
        "--stage",
        choices=["games", "preflight", "skills", "analyse"],
        default=None,
    )
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument(
        "--games", default=None, help="comma-separated game ids (debug subset)"
    )
    parser.add_argument(
        "--seeds", default=None, help="comma-separated seeds (debug subset)"
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="re-run episodes already present in results/episodes.jsonl",
    )
    args = parser.parse_args()

    if args.round is None and args.stage is None:
        parser.error("give --round 0/1 or --stage games|preflight|skills|analyse")

    config = load_config(args.config)

    if args.stage == "games":
        stage_games(config)
        return
    if args.stage == "preflight":
        stage_preflight(config)
        return
    if args.stage == "skills":
        stage_skills(config)
        return
    if args.stage == "analyse":
        stage_analyse(config)
        return

    only_games = args.games.split(",") if args.games else None
    only_seeds = [int(s) for s in args.seeds.split(",")] if args.seeds else None
    stage_round(
        config,
        int(args.round),
        only_games=only_games,
        only_seeds=only_seeds,
        resume=not args.no_resume,
    )


if __name__ == "__main__":
    main()
