"""Seed phase + the M0 sanity gate.

The seed phase is the ONLY place in the whole experiment where true labels are
used for training.  It stands in for "start from a pretrained base LLM": it gives
the Solver partial competence, and everything after it has to come from tasks the
Challenger invents.

M0 asks whether a *reachable frontier* exists at all.  If majority-vote
pseudo-labels are worthless at the frontier, the R-Zero loop cannot work here,
and the honest move is to re-tune the domain rather than run a loop that trains
on noise.
"""

from __future__ import annotations

import os

import numpy as np

import domain as D
import solver as S

SEED_BUCKETS = [D.BUCKET_INDEX[(1, G, C)] for G in D.GRID_SIZES for C in D.NUM_COLORS]
"""All depth-1 buckets.

The issue specifies the single easiest bucket ``(1,3,2)``.  That was tried first
and left the Solver at 0% on every bucket with a different G or C, because those
input features were never activated during seeding (see ``WORK_LOG-4.md``).
Seeding on all depth-1 buckets is the issue's own "strengthen the seed phase"
remedy: it gives *broad but shallow* competence, which is the honest analogue of
a pretrained base model, while still leaving every depth > 1 unlabelled.
"""

SEED_STEPS = 1200
"""How long to seed.

This is the knob that sets how wide the frontier is, and it is genuinely
two-sided.  Seed too long and the Solver is near-perfect on most buckets, the
frontier shrinks to one corner of the grid, and there is nothing for the loop to
climb; seed too briefly and it is below 50% almost everywhere, majority votes are
noise, and the loop trains on junk.  1200 steps was chosen by sweeping (600 /
1200 / 2500, see ``WORK_LOG-4.md``) as the setting that leaves 16 buckets in the
5-95% band with the hardest bucket still at 0%.
"""


def seed_batch(bucket_ids, rng, batch_size):
    bids = [int(b) for b in rng.choice(bucket_ids, size=batch_size)]
    programs = [D.sample_from_bucket(b, 1, rng)[0] for b in bids]
    # GROUND TRUTH: seed phase only -- the guard enforces the purpose.
    return D.make_tasks(bids, programs, rng, with_labels=True, purpose="seed")


def seed_train(sol, bucket_ids, steps=1200, batch_size=128, rng=None, log_every=0):
    """Train on ground-truth labels from ``bucket_ids``.  Seed phase only."""
    rng = rng or np.random.default_rng(0)
    losses = []
    for step in range(steps):
        batch = seed_batch(bucket_ids, rng, batch_size)
        enc = S.encode_tasks(batch)
        labels, cell_mask = D.encode_targets(batch.outputs, batch.bucket_ids)
        losses.append(sol.train_step(enc, labels, cell_mask))
        if log_every and (step + 1) % log_every == 0:
            print(
                "  seed step %5d  loss %.4f"
                % (step + 1, float(np.mean(losses[-log_every:])))
            )
    return losses


def pseudo_label_stats(sol, batch, m=10, rng=None):
    """Pseudo-label quality on a batch, measured against ground truth.

    Measurement only.  The loop calls ``majority_vote`` directly and never sees
    the accuracy numbers computed here.
    """
    # GROUND TRUTH: reporting only.
    D.assert_ground_truth_allowed("eval")
    enc = S.encode_tasks(batch)
    labels, cell_mask = D.encode_targets(batch.outputs, batch.bucket_ids)
    preds = sol.sample_answers(enc, m, rng)
    pseudo, p_hat = S.majority_vote(preds, cell_mask)
    return {
        "pseudo_label_accuracy": float(S.exact_match(pseudo, labels, cell_mask).mean()),
        "single_sample_accuracy": float(
            np.mean(
                [S.exact_match(preds[k], labels, cell_mask).mean() for k in range(m)]
            )
        ),
        "greedy_accuracy": float(
            S.exact_match(sol.predict(enc), labels, cell_mask).mean()
        ),
        "mean_p_hat": float(p_hat.mean()),
        "frac_in_band": float(np.mean(np.abs(p_hat - 0.5) <= 0.25)),
    }


CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "seed_cache")


def _cache_path(seed, steps, committee):
    return os.path.join(CACHE_DIR, "seed%d_s%d_k%d.npz" % (seed, steps, committee))


def make_seeded_solver(seed=0, steps=SEED_STEPS, committee=10, verbose=False, cache=True):
    """Build and seed a Solver.  Shared by the M0 gate and every run mode.

    The seed phase depends only on ``(seed, steps, committee)``, never on the
    mode, so it is cached to disk.  Beyond saving most of the wall clock, this
    makes every mode for a given seed start from *byte-identical* weights, which
    turns the mode comparison into a paired one: a difference between ``rzero``
    and ``uniform`` at the same seed cannot be an artefact of a luckier
    initialisation.
    """
    path = _cache_path(seed, steps, committee)
    rng = np.random.default_rng(seed)
    sol = S.Committee(rng, k=committee) if committee > 1 else S.Solver(rng)

    if cache and os.path.exists(path):
        blob = np.load(path)
        members = sol.members if committee > 1 else [sol]
        for j, mem in enumerate(members):
            for name in mem.params:
                mem.params[name] = blob["m%d_%s" % (j, name)]
        # Advance the rng exactly as training would have, so downstream sampling
        # does not silently correlate with whether the cache was warm.
        rng = np.random.default_rng(seed + 10_000_000)
        return sol, rng

    seed_train(sol, SEED_BUCKETS, steps=steps, rng=rng, log_every=500 if verbose else 0)
    if cache:
        os.makedirs(CACHE_DIR, exist_ok=True)
        members = sol.members if committee > 1 else [sol]
        np.savez(
            path,
            **{
                "m%d_%s" % (j, name): mem.params[name]
                for j, mem in enumerate(members)
                for name in mem.params
            },
        )
    return sol, np.random.default_rng(seed + 10_000_000)


def run_m0(seed=0, steps=SEED_STEPS, m=10, committee=10, verbose=True):
    sol, _ = make_seeded_solver(
        seed=seed, steps=steps, committee=committee, verbose=verbose
    )
    if verbose:
        print("Solver params: %d (committee of %d)" % (sol.num_params(), committee))

    test = D.held_out_set()
    accs = np.array([S.evaluate(sol, test[b]) for b in range(D.NUM_BUCKETS)])

    if verbose:
        print("\nPer-bucket greedy exact-match after seeding (* = seeded):")
        for d in D.DEPTHS:
            cells = []
            for G in D.GRID_SIZES:
                for C in D.NUM_COLORS:
                    b = D.BUCKET_INDEX[(d, G, C)]
                    cells.append(
                        "%s%5.1f" % ("*" if b in SEED_BUCKETS else " ", 100 * accs[b])
                    )
            print("  d=%d |%s" % (d, " ".join(cells)))
        print(
            "      |"
            + " ".join(
                "%6s" % ("G%dC%d" % (G, C))
                for G in D.GRID_SIZES
                for C in D.NUM_COLORS
            )
        )

    frontier = [
        b
        for b in range(D.NUM_BUCKETS)
        if 0.05 <= accs[b] <= 0.95 and b not in SEED_BUCKETS
    ]
    if verbose:
        print(
            "\nFrontier buckets (5-95%%, unseeded): %s"
            % [D.BUCKETS[b] for b in frontier]
        )

    stats = {}
    probe = frontier if frontier else list(np.argsort(-accs)[:5])
    for b in probe:
        stats[D.BUCKETS[b]] = pseudo_label_stats(
            sol, test[b], m=m, rng=np.random.default_rng(1234 + b)
        )

    if verbose and stats:
        print("\nPseudo-label quality on frontier buckets (m=%d):" % m)
        print(
            "  %-12s %8s %8s %8s %8s %8s"
            % ("(d,G,C)", "vote", "single", "greedy", "p_hat", "in-band")
        )
        for z, s in stats.items():
            print(
                "  %-12s %7.1f%% %7.1f%% %7.1f%% %8.2f %7.1f%%"
                % (
                    str(z),
                    100 * s["pseudo_label_accuracy"],
                    100 * s["single_sample_accuracy"],
                    100 * s["greedy_accuracy"],
                    s["mean_p_hat"],
                    100 * s["frac_in_band"],
                )
            )

    # The issue's gate names the single easiest bucket; the mean over all seeded
    # buckets is reported alongside it because seeding now covers nine of them.
    easiest_acc = float(accs[D.SEED_BUCKET_ID])
    seed_acc = float(np.mean([accs[b] for b in SEED_BUCKETS]))
    gate = {
        "easiest_bucket_acc": easiest_acc,
        "mean_seeded_bucket_acc": seed_acc,
        "hardest_bucket_acc": float(accs[D.HARDEST_BUCKET_ID]),
        "frontier_buckets": [list(D.BUCKETS[b]) for b in frontier],
        "per_bucket_acc": {str(D.BUCKETS[b]): float(accs[b]) for b in range(D.NUM_BUCKETS)},
        "pseudo_label_stats": {str(k): v for k, v in stats.items()},
        "gate_seed_ge_90": bool(easiest_acc >= 0.90),
        "gate_frontier_ge_25": bool(
            any(0.25 <= accs[b] <= 0.95 for b in range(D.NUM_BUCKETS)
                if b not in SEED_BUCKETS)
        ),
        "gate_hardest_near_zero": bool(accs[D.HARDEST_BUCKET_ID] <= 0.05),
        # The check that actually matters: pseudo-labels must beat the Solver's
        # own greedy output, otherwise training on them is self-distillation.
        "gate_vote_beats_greedy": bool(
            any(
                s["pseudo_label_accuracy"] > s["greedy_accuracy"]
                for s in stats.values()
            )
        ),
        "gate_vote_beats_single": bool(
            any(
                s["pseudo_label_accuracy"] > s["single_sample_accuracy"]
                for s in stats.values()
            )
        ),
    }
    if verbose:
        print("\nM0 gate:")
        for k, v in gate.items():
            if k.startswith("gate_"):
                print("  %-28s %s" % (k, "PASS" if v else "FAIL"))
        print("  easiest bucket acc    %.1f%%" % (100 * gate["easiest_bucket_acc"]))
        print("  mean seeded acc       %.1f%%" % (100 * gate["mean_seeded_bucket_acc"]))
        print("  hardest bucket acc    %.1f%%" % (100 * gate["hardest_bucket_acc"]))
    return sol, accs, stats, gate


if __name__ == "__main__":
    import json

    _sol, _accs, _stats, _gate = run_m0()
    os.makedirs("results", exist_ok=True)
    with open("results/m0_gate.json", "w") as fh:
        json.dump(_gate, fh, indent=2)
    print("\nwrote results/m0_gate.json")
