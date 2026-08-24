"""CLI for the mini-R-Zero experiment.

    python run.py --mode rzero --seeds 3
    python run.py --mode uniform --seeds 3
    python run.py --ablate no-rep-penalty --seeds 3
    python run.py --m0                      # just the sanity gate

Every run writes ``results/<tag>.json``, and ``plots.py`` regenerates all three
figures from those files without retraining anything.
"""

from __future__ import annotations

import argparse
import json
import os
import time

import numpy as np

import loop as L
import seed as SD

RESULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")

ABLATIONS = {
    "none": {},
    "no-rep-penalty": {"use_rep_penalty": False},
    "no-filter": {"use_filter": False},
    "single-model": {"single_model": True},
}


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", default="rzero",
                    choices=["rzero", "uniform", "hardest", "oracle"],
                    help="curriculum source (oracle also trains on true labels)")
    ap.add_argument("--ablate", default="none", choices=sorted(ABLATIONS),
                    help="disable one component of the method")
    ap.add_argument("--seeds", type=int, default=3, help="number of random seeds")
    ap.add_argument("--iters", type=int, default=8, help="co-evolution iterations")
    ap.add_argument("--m", type=int, default=10, help="answers sampled per task")
    ap.add_argument("--delta", type=float, default=0.25, help="difficulty filter band")
    ap.add_argument("--seed-steps", type=int, default=SD.SEED_STEPS)
    ap.add_argument("--committee", type=int, default=10)
    ap.add_argument("--solver-lr", type=float, default=1e-4,
                    help="Solver LR during co-evolution (seed phase uses 2e-3)")
    ap.add_argument("--epochs", type=int, default=4,
                    help="passes over the kept pseudo-label set per iteration")
    ap.add_argument("--candidates", type=int, default=1500,
                    help="candidate tasks sampled per iteration (paper: N=8000)")
    ap.add_argument("--group-size", type=int, default=256, help="GRPO group size")
    ap.add_argument("--challenger-steps", type=int, default=8)
    ap.add_argument("--challenger-lr", type=float, default=2.0,
                    help="GRPO-lite step size for the Challenger policy")
    ap.add_argument("--tag", default=None, help="output filename stem")
    ap.add_argument("--m0", action="store_true", help="run only the M0 sanity gate")
    ap.add_argument("--quiet", action="store_true")
    return ap.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    os.makedirs(RESULTS, exist_ok=True)

    if args.m0:
        _sol, _accs, _stats, gate = SD.run_m0(
            steps=args.seed_steps, m=args.m, committee=args.committee
        )
        with open(os.path.join(RESULTS, "m0_gate.json"), "w") as fh:
            json.dump(gate, fh, indent=2)
        print("\nwrote results/m0_gate.json")
        return 0

    tag = args.tag or (
        args.mode if args.ablate == "none" else "%s-%s" % (args.mode, args.ablate)
    )
    t0 = time.time()
    runs = []
    for s in range(args.seeds):
        runs.append(
            L.run_loop(
                mode=args.mode,
                seed=s,
                iters=args.iters,
                m=args.m,
                delta=args.delta,
                group_size=args.group_size,
                challenger_steps=args.challenger_steps,
                challenger_lr=args.challenger_lr,
                n_candidates=args.candidates,
                committee=args.committee,
                seed_steps=args.seed_steps,
                solver_lr=args.solver_lr,
                epochs=args.epochs,
                verbose=not args.quiet,
                **ABLATIONS[args.ablate],
            )
        )

    curves = np.array([[it["accuracy"] for it in r["iterations"]] for r in runs])
    out = {
        "tag": tag,
        "mode": args.mode,
        "ablation": args.ablate,
        "seeds": args.seeds,
        "wall_seconds": time.time() - t0,
        "accuracy_mean": curves.mean(axis=0).tolist(),
        "accuracy_std": curves.std(axis=0).tolist(),
        "final_mean": float(curves[:, -1].mean()),
        "final_std": float(curves[:, -1].std()),
        "best_mean": float(curves.mean(axis=0).max()),
        "best_iteration": int(curves.mean(axis=0).argmax()),
        "runs": runs,
    }
    path = os.path.join(RESULTS, "%s.json" % tag)
    with open(path, "w") as fh:
        json.dump(out, fh)
    print(
        "\n[%s] final %.1f%% +- %.1f%%   best %.1f%% at iter %d   (%.0fs)"
        % (
            tag, 100 * out["final_mean"], 100 * out["final_std"],
            100 * out["best_mean"], out["best_iteration"], out["wall_seconds"],
        )
    )
    print("wrote %s" % os.path.relpath(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
