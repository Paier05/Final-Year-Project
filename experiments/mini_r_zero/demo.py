"""One-command reproduction of the headline result.

    python demo.py

Runs the M0 sanity gate, the four curricula at 3 seeds each, and regenerates the
three figures into ``results/``.  Designed to fit a laptop CPU inside 30 minutes.

The M3 ablations are deliberately *not* run here -- they add ~3x the wall clock
and feed a table rather than the plots.  Run them with:

    python run.py --mode rzero --ablate no-rep-penalty --seeds 3
    python run.py --mode rzero --ablate no-filter      --seeds 3
    python run.py --mode rzero --ablate single-model   --seeds 3
"""

from __future__ import annotations

import time

import plots
import run

MODES = ["rzero", "uniform", "hardest", "oracle"]
ITERS = 15
SEEDS = 3


def main():
    t0 = time.time()
    print("=" * 70)
    print("M0 sanity gate")
    print("=" * 70)
    run.main(["--m0"])

    for mode in MODES:
        print("\n" + "=" * 70)
        print("mode: %s (%d seeds, %d iterations)" % (mode, SEEDS, ITERS))
        print("=" * 70)
        run.main(
            ["--mode", mode, "--seeds", str(SEEDS), "--iters", str(ITERS), "--quiet"]
        )

    print("\n" + "=" * 70)
    print("figures")
    print("=" * 70)
    plots.main()
    print("\ntotal wall clock: %.1f minutes" % ((time.time() - t0) / 60.0))


if __name__ == "__main__":
    raise SystemExit(main())
