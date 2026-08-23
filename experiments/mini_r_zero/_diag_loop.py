"""Throwaway: why does the loop lose accuracy? Forgetting, or bad labels?"""
import sys

import numpy as np

import domain as D
import loop as L
import seed as SD
import solver as S

test = D.held_out_set()


def per_bucket(sol):
    return np.array([S.evaluate(sol, test[b]) for b in range(D.NUM_BUCKETS)])


def show(tag, before, after):
    print("\n%s: change in per-bucket accuracy (pp)" % tag)
    for d in D.DEPTHS:
        row = []
        for G in D.GRID_SIZES:
            for C in D.NUM_COLORS:
                b = D.BUCKET_INDEX[(d, G, C)]
                row.append("%+6.1f" % (100 * (after[b] - before[b])))
        print("  d=%d |%s" % (d, " ".join(row)))
    print("      |" + " ".join("%6s" % ("G%dC%d" % (G, C))
                               for G in D.GRID_SIZES for C in D.NUM_COLORS))
    seeded = [b for b in SD.SEED_BUCKETS]
    rest = [b for b in range(D.NUM_BUCKETS) if b not in seeded]
    print("  seeded buckets %+.1fpp   unseeded %+.1fpp   overall %+.1fpp" % (
        100 * (after[seeded].mean() - before[seeded].mean()),
        100 * (after[rest].mean() - before[rest].mean()),
        100 * (after.mean() - before.mean())))


# Is the drop caused by the size of the update? Sweep lr and epochs directly.
for lr, epochs in [(2e-3, 4), (5e-4, 2), (2e-4, 2), (1e-4, 4)]:
    sol, rng = SD.make_seeded_solver(seed=0)
    for mem in sol.members:
        mem.lr = lr
    before = per_bucket(sol)
    import challenger as Ch
    ch = Ch.Challenger(rng)
    accs = [before.mean()]
    pls = []
    for it in range(6):
        frozen = sol.clone()
        for _ in range(8):
            bids, progs = ch.sample(256, rng)
            batch = D.make_tasks(bids, progs, rng)
            enc = S.encode_tasks(batch)
            preds = frozen.sample_answers(enc, 10, rng)
            _, p_hat = S.majority_vote(preds, D.cell_mask_for(bids))
            r, _ = Ch.compose_reward(bids, progs, p_hat)
            ch.update(bids, progs, r)
        bids, progs = ch.sample(1500, rng)
        batch, pseudo, p_hat, idx = L.build_dataset(frozen, bids, progs, rng)
        pls.append(L.pseudo_label_accuracy(batch, pseudo, idx))
        L.train_on_pseudo(sol, batch, pseudo, idx, rng, epochs=epochs)
        accs.append(per_bucket(sol).mean())
    after = per_bucket(sol)
    print("\n=== lr=%g epochs=%d ===" % (lr, epochs))
    print("  acc:    " + " ".join("%.1f" % (100 * a) for a in accs))
    print("  pseudo: " + " ".join("%.1f" % (100 * a) for a in pls))
    print("  challenger mean difficulty: %.3f" % ch.mean_difficulty())
    show("lr=%g ep=%d" % (lr, epochs), before, after)
