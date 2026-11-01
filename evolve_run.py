"""Driver for issue #9: the 5-generation evo-harness run on ls20, Level 1.

    python evolve_run.py --stage preflight             # credentials + inference
    python evolve_run.py --stage pilot                 # one real v0 episode, for cost
    python evolve_run.py --rounds 5                    # round 0 + rounds 1..5 (resumable)
    python evolve_run.py --stage figures               # figures from archive.json
    python evolve_run.py --stub --rounds 2 --root DIR  # offline self-test, no model

Credentials: QWEN_API_KEY and QWEN_BASE_URL, from the environment or .env.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

import yaml

from harness.model import AbortExperiment
from evolve import loop


def load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def stage_preflight(cfg: dict) -> None:
    for section in ("player", "meta"):
        client = loop.make_client(cfg, section)
        # Print the model id only; the endpoint URL is a credential here.
        info = client.preflight()
        print(f"{section}: {client.model} OK (probe reply {info.get('probe')!r})")


def stage_pilot(cfg: dict, root: str) -> None:
    """One real v0 episode, written outside the experiment's tree."""
    from evolve.action_loop import run_episode
    from evolve.replay import make_env
    from evolve.seed_v0 import build_v0

    paths = loop.Paths(root)
    client = loop.make_client(cfg, "player")
    outcome = run_episode(
        env=make_env(cfg["game"]), client=client, harness=build_v0(), round_index=0,
        episode=0, cfg=cfg, traj_root=paths.trajectories, frame_root=paths.frames,
    )
    print(json.dumps(outcome.as_dict(), indent=1))


def main() -> None:
    parser = argparse.ArgumentParser(description="evo-harness run (#9)")
    parser.add_argument("--stage", choices=["preflight", "pilot", "figures"])
    parser.add_argument("--rounds", type=int, default=None)
    parser.add_argument("--config", default="config_evolve.yaml")
    parser.add_argument("--root", default=None, help="output root (default results/evolve)")
    parser.add_argument("--stub", action="store_true",
                        help="offline self-test: stub player and stub Meta LLM, no model calls")
    args = parser.parse_args()
    cfg = load_config(args.config)

    if args.stage == "preflight":
        stage_preflight(cfg)
        return
    if args.stage == "pilot":
        stage_pilot(cfg, args.root or os.path.join("data", "evolve_pilot"))
        return
    if args.stage == "figures":
        from analysis.evolution import build_all

        for path in build_all(args.root or os.path.join("results", "evolve")):
            print("wrote", path)
        return

    rounds = args.rounds if args.rounds is not None else int(cfg["rounds"])
    if args.stub:
        from evolve.stub import StubMeta, StubPlayer

        root = args.root or os.path.join("data", "evolve_stub")
        cfg["budget"]["max_actions"] = 40
        cfg["budget"]["max_turns"] = 30
        player_factory = lambda k: StubPlayer(seed=k)  # noqa: E731
        meta_factory = StubMeta
        print("*** STUB MODE: stub player and Meta LLM, no model calls. Not a result. ***")
    else:
        root = args.root or os.path.join("results", "evolve")
        print("preflight ...")
        stage_preflight(cfg)
        player_factory = lambda k: loop.make_client(cfg, "player")  # noqa: E731
        meta_factory = (lambda: loop.make_client(cfg, "meta")) if cfg["meta"]["enabled"] else None

    started = time.monotonic()
    try:
        archive = loop.run(cfg, loop.Paths(root), rounds, player_factory, meta_factory)
    except AbortExperiment as error:
        print(f"\n*** RUN STOPPED: {error}", file=sys.stderr)
        raise SystemExit(2)
    print(f"\ndone in {(time.monotonic() - started) / 60:.1f} min")
    for entry in archive["versions"]:
        print(f"  {entry['version']:>3} parent={entry['parent'] or '-':>3} mean={entry['score_mean']} "
              f"worst={entry['score_worst']} clears={entry['n_clears']}/{entry['n_episodes']} "
              f"gate={entry['gate']['decision']}")


if __name__ == "__main__":
    main()
