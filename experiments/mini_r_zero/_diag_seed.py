"""Throwaway diagnostic: which seed sets produce a reachable frontier?

Not part of the deliverable -- deleted once M0 is settled.
"""
import sys

import numpy as np

import domain as D
import solver as S
import seed as SD


def profile(name, seed_buckets, steps=4000, seed=0):
    rng = np.random.default_rng(seed)
    sol = S.Solver(rng)
    SD.seed_train(sol, seed_buckets, steps=steps, rng=rng)
    test = D.held_out_set()
    accs = np.array([S.evaluate(sol, test[b]) for b in range(D.NUM_BUCKETS)])
    print("\n=== %s (%d steps, %d seed buckets) ===" % (name, steps, len(seed_buckets)))
    for d in D.DEPTHS:
        row = []
        for G in D.GRID_SIZES:
            for C in D.NUM_COLORS:
                b = D.BUCKET_INDEX[(d, G, C)]
                tag = "*" if b in seed_buckets else " "
                row.append("%s%5.1f" % (tag, 100 * accs[b]))
        print("d=%d |%s" % (d, " ".join(row)))
    print("     |" + " ".join("%6s" % ("G%dC%d" % (G, C))
                              for G in D.GRID_SIZES for C in D.NUM_COLORS))
    frontier = [b for b in range(D.NUM_BUCKETS)
                if 0.05 <= accs[b] <= 0.95 and b not in seed_buckets]
    print("frontier:", [D.BUCKETS[b] for b in frontier])
    for b in frontier[:4]:
        st = SD.pseudo_label_stats(sol, test[b], m=10, rng=np.random.default_rng(9 + b))
        print("   %s vote=%.1f%% single=%.1f%% greedy=%.1f%% p_hat=%.2f band=%.1f%%" % (
            D.BUCKETS[b], 100 * st["pseudo_label_accuracy"],
            100 * st["single_sample_accuracy"], 100 * st["greedy_accuracy"],
            st["mean_p_hat"], 100 * st["frac_in_band"]))
    return accs


which = sys.argv[1] if len(sys.argv) > 1 else "all"

if which in ("all", "a"):
    profile("A: all d=1 buckets", [D.BUCKET_INDEX[(1, G, C)]
                                   for G in D.GRID_SIZES for C in D.NUM_COLORS])

if which in ("all", "b"):
    profile("B: all d<=2 at G=3,C=2 plus all d=1",
            sorted(set([D.BUCKET_INDEX[(1, G, C)]
                        for G in D.GRID_SIZES for C in D.NUM_COLORS]
                       + [D.BUCKET_INDEX[(2, 3, 2)]])))

if which in ("all", "c"):
    profile("C: all d<=2 buckets", [D.BUCKET_INDEX[(d, G, C)]
                                    for d in (1, 2)
                                    for G in D.GRID_SIZES for C in D.NUM_COLORS])
