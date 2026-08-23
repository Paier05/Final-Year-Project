"""Seed phase + the M0 sanity gate.

The seed phase is the ONLY place in the whole experiment where true labels are
used for training.  It stands in for "start from a pretrained base LLM": it
gives the Solver partial competence, and everything after it has to come from
tasks the Challenger invents.

M0 asks whether a *reachable frontier* exists at all.  If majority-vote
pseudo-labels are worthless at the frontier, the R-Zero loop cannot work here,
and the honest move is to re-tune the domain rather than run a loop that trains
on noise.
"""

from __future__ import annotations

import numpy as np

import domain as D
import solver as S


def seed_train(
    sol,
    bucket_ids,
    steps=3000,
    batch_size=128,
    rng=None,
    log_every=0,
):
    """Train on ground-truth labels from ``bucket_ids``.  Seed phase only."""
    rng = rng or np.random.default_rng(0)
    losses = []
    for step in range(steps):
        bids = [int(b) for b in rng.choice(bucket_ids, size=batch_size)]
        programs = [D.sample_from_bucket(b, 1, rng)[0] for b in bids]
        # GROUND TRUTH: seed phase only -- the guard enforces the purpose.
        batch = D.make_tasks(bids, programs, rng, with_labels=True, purpose="seed")
        x, cmask = S.encode_tasks(batch)
        labels, cell_mask = D.encode_targets(batch.outputs, batch.bucket_ids)
        loss = sol.train_step(x, labels, cell_mask, cmask)
        losses.append(loss)
        if log_every and (step + 1) % log_every == 0:
            print("  seed step %5d  loss %.4f" % (step + 1, float(np.mean(losses[-log_every:]))))
    return losses


def pseudo_label_stats(sol, batch, m=10, rng=None):
    """Pseudo-label quality on a batch, measured against ground truth.

    Measurement only -- the numbers computed here are reported, never fed back
    into training.  The loop calls ``majority_vote`` directly and never sees the
    ``accuracy`` field.
    """
    x, cmask = S.encode_tasks(batch)
    preds = sol.sample_answers(x, cmask, m, rng)
    pseudo, p_hat = S.majority_vote(preds, D.encode_targets(batch.outputs, batch.bucket_ids)[1])
    labels, cell_mask = D.encode_targets(batch.outputs, batch.bucket_ids)
    # GROUND TRUTH: evaluation/reporting only.
    D.assert_ground_truth_allowed("eval")
    pseudo_acc = float(S.exact_match(pseudo, labels, cell_mask).mean())
    single_acc = float(
        np.mean([S.exact_match(preds[k], labels, cell_mask).mean() for k in range(m)])
    )
    greedy_acc = float(S.exact_match(sol.predict(x, cmask), labels, cell_mask).mean())
    return {
        "pseudo_label_accuracy": pseudo_acc,
        "single_sample_accuracy": single_acc,
        "greedy_accuracy": greedy_acc,
        "mean_p_hat": float(p_hat.mean()),
        "frac_in_band": float(np.mean(np.abs(p_hat - 0.5) <= 0.25)),
    }


def run_m0(seed=0, steps=3000, m=10, verbose=True, seed_buckets=None):
    rng = np.random.default_rng(seed)
    sol = S.Solver(rng)
    if seed_buckets is None:
        seed_buckets = [D.SEED_BUCKET_ID]
    if verbose:
        print("Solver params: %d" % sol.num_params())
        print("Seeding on buckets %s for %d steps..." % (
            [D.BUCKETS[b] for b in seed_buckets], steps))
    seed_train(sol, seed_buckets, steps=steps, rng=rng, log_every=500 if verbose else 0)

    test = D.held_out_set()
    accs = np.array([S.evaluate(sol, test[b]) for b in range(D.NUM_BUCKETS)])

    if verbose:
        print("\nPer-bucket greedy exact-match after seeding:")
        print("  %-12s %8s" % ("(d,G,C)", "acc"))
        for b in range(D.NUM_BUCKETS):
            print("  %-12s %7.1f%%" % (str(D.BUCKETS[b]), 100 * accs[b]))

    # Frontier = buckets the Solver is partly, but not fully, competent at.
    frontier = [b for b in range(D.NUM_BUCKETS) if 0.05 <= accs[b] <= 0.95]
    if verbose:
        print("\nFrontier buckets (5%%-95%% accuracy): %s"
              % [D.BUCKETS[b] for b in frontier])

    stats = {}
    probe = frontier if frontier else list(np.argsort(-accs)[1:6])
    for b in probe:
        rng_b = np.random.default_rng(1234 + b)
        stats[D.BUCKETS[b]] = pseudo_label_stats(sol, test[b], m=m, rng=rng_b)

    if verbose:
        print("\nPseudo-label quality on probe buckets (m=%d):" % m)
        print("  %-12s %8s %8s %8s %8s %8s"
              % ("(d,G,C)", "vote", "single", "greedy", "p_hat", "in-band"))
        for z, s in stats.items():
            print("  %-12s %7.1f%% %7.1f%% %7.1f%% %8.2f %7.1f%%" % (
                str(z), 100 * s["pseudo_label_accuracy"],
                100 * s["single_sample_accuracy"], 100 * s["greedy_accuracy"],
                s["mean_p_hat"], 100 * s["frac_in_band"]))

    gate = {
        "seed_bucket_acc": float(accs[D.SEED_BUCKET_ID]),
        "hardest_bucket_acc": float(accs[D.HARDEST_BUCKET_ID]),
        "gate_seed_ge_90": bool(accs[D.SEED_BUCKET_ID] >= 0.90),
        "gate_frontier_ge_25": bool(
            any(0.25 <= accs[b] <= 0.95 for b in range(D.NUM_BUCKETS)
                if b != D.SEED_BUCKET_ID)
        ),
        "gate_hardest_near_zero": bool(accs[D.HARDEST_BUCKET_ID] <= 0.05),
        "gate_vote_beats_single": bool(
            any(s["pseudo_label_accuracy"] > s["single_sample_accuracy"]
                for s in stats.values())
        ),
    }
    if verbose:
        print("\nM0 gate:")
        for k, v in gate.items():
            if k.startswith("gate_"):
                print("  %-28s %s" % (k, "PASS" if v else "FAIL"))
        print("  seed bucket acc   %.1f%%" % (100 * gate["seed_bucket_acc"]))
        print("  hardest bucket    %.1f%%" % (100 * gate["hardest_bucket_acc"]))
    return sol, accs, stats, gate


if __name__ == "__main__":
    run_m0()
