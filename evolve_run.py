"""Driver for the evo-harness runs on ls20, Level 1 (issue #9, follow-up #12).

    python evolve_run.py --stage preflight             # credentials + inference
    python evolve_run.py --stage pilot                 # one real v0 episode, for cost
    python evolve_run.py --rounds 5                    # round 0 + rounds 1..5 (resumable)
    python evolve_run.py --stage figures               # figures from archive.json
    python evolve_run.py --stage rescore9              # #9's episodes on #12's score
    python evolve_run.py --stub --rounds 2 --root DIR  # offline self-test, no model

The output root is `root` in the config (#12: results/evolve_12; #9's
results/evolve is never written). Credentials: QWEN_API_KEY and
QWEN_BASE_URL, from the environment or .env.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from urllib.parse import urlsplit

import yaml

from harness.model import AbortExperiment, load_api_key
from evolve import loop


def redact(text: str) -> str:
    """Strip the endpoint URL and key from anything printed (the issue treats
    both as credentials; harness.model's errors include the URL)."""
    for name, placeholder in (("QWEN_BASE_URL", "<QWEN_BASE_URL>"), ("QWEN_API_KEY", "<QWEN_API_KEY>")):
        try:
            secret = load_api_key(name)
        except AbortExperiment:
            continue
        if secret:
            text = str(text).replace(secret.rstrip("/"), placeholder)
            # Connection errors name the host and path, not the configured URL.
            host = urlsplit(secret).hostname
            if host:
                text = text.replace(host, placeholder)
    return text


# Progress lines also go to this file, opened and closed on every write. On
# 2026-11-02 the detached #12 run's redirected stdout stopped receiving them
# at 16:37 while the run itself went on (py-spy showed no thread blocked), so
# monitoring must not depend on stdout alone.
EVENT_LOG: str | None = None


def log(message: str) -> None:
    text = redact(message)
    print(text, flush=True)
    if EVENT_LOG:
        with open(EVENT_LOG, "a", encoding="utf-8") as handle:
            handle.write(text + "\n")


def load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def stage_preflight(cfg: dict) -> None:
    for section in ("player", "meta"):
        client = loop.make_client(cfg, section)
        # Print the model id only; the endpoint URL is a credential here.
        try:
            info = client.preflight()
        except AbortExperiment as error:
            raise AbortExperiment(redact(str(error))) from None
        print(f"{section}: {client.model} OK (probe reply {info.get('probe')!r})")


def stage_pilot(cfg: dict, root: str) -> None:
    """One real v0 episode on the first seed, written outside the experiment's
    tree, scored like a run episode. Also checks that the logged game states
    equal the states rebuilt by replay (what rescoring #9 relies on)."""
    from evolve.action_loop import read_records, run_episode
    from evolve.goal_score import read_state, states_by_replay, states_from_records
    from evolve.replay import make_env
    from evolve.score import episode_metrics
    from evolve.seed_v0 import build_v0

    paths = loop.Paths(root)
    seed = int(cfg["seeds"][0])
    client = loop.make_client(cfg, "player", seed=seed)
    outcome = run_episode(
        env=make_env(cfg["game"], seed=seed), client=client, harness=build_v0(), round_index=0,
        episode=seed, seed=seed, cfg=cfg, traj_root=paths.trajectories, frame_root=paths.frames,
        probe=read_state,
    )
    row = outcome.as_dict()
    records = read_records(outcome.trajectory)
    row |= episode_metrics(records, row, cfg)
    logged, _ = states_from_records(records)
    replayed, _ = states_by_replay(records, cfg["game"])
    row["logged_states_equal_replay"] = logged == replayed
    print(json.dumps(row, indent=1, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(description="evo-harness run (#9, #12)")
    parser.add_argument("--stage", choices=["preflight", "pilot", "figures", "rescore9"])
    parser.add_argument("--rounds", type=int, default=None)
    parser.add_argument("--config", default="config_evolve.yaml")
    parser.add_argument("--root", default=None, help="output root (default: `root` in the config)")
    parser.add_argument("--stub", action="store_true",
                        help="offline self-test: stub player and stub Meta LLM, no model calls")
    args = parser.parse_args()
    cfg = load_config(args.config)
    root_default = cfg.get("root", os.path.join("results", "evolve"))

    if args.stage == "preflight":
        try:
            stage_preflight(cfg)
        except AbortExperiment as error:
            print(f"*** PREFLIGHT FAILED: {error}", file=sys.stderr)
            raise SystemExit(2)
        return
    if args.stage == "pilot":
        try:
            stage_pilot(cfg, args.root or os.path.join("data", "evolve12_pilot"))
        except AbortExperiment as error:
            print(f"*** PILOT STOPPED: {redact(str(error))}", file=sys.stderr)
            raise SystemExit(2)
        return
    if args.stage == "figures":
        from analysis.evolution12 import build_all

        for path in build_all(args.root or root_default):
            print("wrote", path)
        return
    if args.stage == "rescore9":
        from analysis.rescore_9 import main as rescore

        rescore(cfg, os.path.join("results", "evolve"), args.root or root_default)
        return

    rounds = args.rounds if args.rounds is not None else int(cfg["rounds"])
    if args.stub:
        from evolve.stub import StubExtractor, StubMeta, StubPlayer

        root = args.root or os.path.join("data", "evolve12_stub")
        cfg["budget"]["max_actions"] = 40
        cfg["budget"]["max_turns"] = 30
        # StubMeta returns 6 edits; let all of them reach Validate so every
        # drop path, the fact-check included, runs end to end.
        cfg["meta"]["max_edits"] = 8
        player_factory = lambda k: StubPlayer(seed=k)  # noqa: E731
        meta_factory = StubMeta
        fact_factory = StubExtractor
        print("*** STUB MODE: stub player, Meta LLM and claim extractor, no model calls. Not a result. ***")
    else:
        root = args.root or root_default
        print("preflight ...")
        try:
            stage_preflight(cfg)
        except AbortExperiment as error:
            print(f"*** PREFLIGHT FAILED: {error}", file=sys.stderr)
            raise SystemExit(2)
        player_factory = lambda seed: loop.make_client(cfg, "player", seed=seed)  # noqa: E731
        meta_factory = (lambda: loop.make_client(cfg, "meta")) if cfg["meta"]["enabled"] else None
        fact_factory = lambda: loop.make_client(cfg, "meta")  # noqa: E731

    global EVENT_LOG
    EVENT_LOG = os.path.join("data", os.path.basename(os.path.normpath(root)) + "_events.log")
    os.makedirs("data", exist_ok=True)
    log(f"--- run started, rounds={rounds}, root={root}, events -> {EVENT_LOG}")
    started = time.monotonic()
    title = cfg.get("experiment", "").split(":")[0] or "issue #12"
    try:
        archive = loop.run(cfg, loop.Paths(root, title=title), rounds, player_factory, meta_factory,
                           log=log, fact_factory=fact_factory)
    except AbortExperiment as error:
        print(f"\n*** RUN STOPPED: {redact(str(error))}", file=sys.stderr)
        raise SystemExit(2)
    print(f"\ndone in {(time.monotonic() - started) / 60:.1f} min")
    for entry in archive["versions"]:
        print(f"  {entry['version']:>3} parent={entry['parent'] or '-':>3} progress={entry['score_mean']} "
              f"cost={entry['cost_mean']} gate={entry['gate_mean']} clears={entry['n_clears']}/"
              f"{entry['n_episodes']} decision={entry['gate']['decision']}")


if __name__ == "__main__":
    main()
