"""The R-Zero loop: seed -> [challenge -> build dataset -> train] x iters.

Each iteration reproduces the paper's three phases:

* **Phase 1 (Challenger).**  The Challenger proposes a group of tasks; the
  *frozen* Solver answers each ``m`` times; ``p_hat`` is the majority-vote
  agreement.  GRPO-lite updates the Challenger on
  ``max(0, r_uncertainty - r_rep)``.
* **Phase 2 (dataset).**  Sample ``N`` candidates from the now-frozen Challenger
  and keep ``(x, pseudo_label)`` only where ``|p_hat - 1/2| <= delta``.
* **Phase 3 (Solver).**  Train the live Solver on the kept pseudo-labels.

The one thing the loop must never do is look at a true label.  Pseudo-labels come
from ``solver.majority_vote`` and nothing else; ``domain.assert_ground_truth_allowed``
raises if anything in here tries.
"""

from __future__ import annotations

import time

import numpy as np

import challenger as Ch
import domain as D
import seed as SD
import solver as S


def evaluate_all(sol, test):
    """Per-bucket and overall held-out accuracy.  Evaluation only."""
    per = {}
    for b in range(D.NUM_BUCKETS):
        per[str(D.BUCKETS[b])] = S.evaluate(sol, test[b])
    return per, float(np.mean(list(per.values())))


def build_dataset(sol, bucket_ids, programs, rng, m=10, delta=0.25, use_filter=True):
    """Phase 2: pseudo-label candidates and keep the ones near ``p_hat = 1/2``.

    Returns the kept batch, its pseudo-labels, and diagnostics.  No ground truth.
    """
    batch = D.make_tasks(bucket_ids, programs, rng)  # no labels requested
    enc = S.encode_tasks(batch)
    cell_mask = D.cell_mask_for(bucket_ids)
    preds = sol.sample_answers(enc, m, rng)
    pseudo, p_hat = S.majority_vote(preds, cell_mask)

    ok = Ch.format_ok(bucket_ids, programs)
    if use_filter:
        keep = (np.abs(p_hat - 0.5) <= delta) & ok
    else:
        # Ablation: no difficulty filter.  Degenerate tasks are still dropped,
        # otherwise this would also silently ablate the format check.
        keep = ok
    idx = np.flatnonzero(keep)
    return batch, pseudo, p_hat, idx


def train_on_pseudo(sol, batch, pseudo, idx, rng, epochs=4, batch_size=128):
    """Phase 3: fit the Solver to its own consensus on the kept tasks."""
    if len(idx) == 0:
        return 0.0, 0
    sub = D.TaskBatch(
        [batch.bucket_ids[i] for i in idx],
        [batch.programs[i] for i in idx],
        [batch.inputs[i] for i in idx],
    )
    enc_all = S.encode_tasks(sub)
    labels = pseudo[idx]
    cell_mask = D.cell_mask_for(sub.bucket_ids)
    n = len(idx)
    losses = []
    for _ in range(epochs):
        order = rng.permutation(n)
        for s in range(0, n, batch_size):
            sel = order[s : s + batch_size]
            if len(sel) < 8:
                continue
            enc = tuple(
                e[:, sel] if e.ndim == 3 and e.shape[0] == D.MAX_D else e[sel]
                for e in enc_all
            )
            losses.append(sol.train_step(enc, labels[sel], cell_mask[sel]))
    return float(np.mean(losses)) if losses else 0.0, n


def run_loop(
    mode="rzero",
    seed=0,
    iters=8,
    m=10,
    delta=0.25,
    group_size=256,
    challenger_steps=8,
    n_candidates=1500,
    committee=10,
    seed_steps=None,
    use_rep_penalty=True,
    use_filter=True,
    single_model=False,
    verbose=True,
):
    """Run one full experiment and return a per-iteration log.

    ``single_model=True`` is the *ablation*: the Challenger probes the live Solver
    instead of a frozen snapshot, and the Solver then trains on labels it is
    simultaneously changing.  The default (False) matches the paper's two-model
    setup.
    """
    t0 = time.time()
    rng = np.random.default_rng(seed)
    sol, _ = SD.make_seeded_solver(
        seed=seed, steps=seed_steps or SD.SEED_STEPS, committee=committee
    )
    test = D.held_out_set()

    if mode in ("uniform", "hardest"):
        ch = Ch.FixedChallenger(mode)
    else:
        # "oracle" uses the same trained Challenger as "rzero"; the only
        # difference is that phase 3 trains on true labels instead of the vote.
        ch = Ch.Challenger(rng, use_rep_penalty=use_rep_penalty)

    per, overall = evaluate_all(sol, test)
    log = {
        "mode": mode,
        "seed": seed,
        "config": {
            "iters": iters, "m": m, "delta": delta, "group_size": group_size,
            "challenger_steps": challenger_steps, "n_candidates": n_candidates,
            "committee": committee, "seed_steps": seed_steps or SD.SEED_STEPS,
            "use_rep_penalty": use_rep_penalty, "use_filter": use_filter,
            "single_model": single_model,
        },
        "iterations": [
            {
                "iteration": 0,
                "accuracy": overall,
                "per_bucket": per,
                "mean_difficulty": ch.mean_difficulty(),
                "bucket_probs": list(ch.bucket_probs()),
            }
        ],
    }
    if verbose:
        print("[%s seed=%d] iter 0  acc %.1f%%" % (mode, seed, 100 * overall))

    for it in range(1, iters + 1):
        # --- Phase 1: train the Challenger against a frozen Solver -----------
        frozen = sol if single_model else sol.clone()
        ch_diag = {}
        if ch.trained:
            for _ in range(challenger_steps):
                bids, progs = ch.sample(group_size, rng)
                batch = D.make_tasks(bids, progs, rng)  # never labelled
                enc = S.encode_tasks(batch)
                cell_mask = D.cell_mask_for(bids)
                preds = frozen.sample_answers(enc, m, rng)
                _, p_hat = S.majority_vote(preds, cell_mask)
                r, ch_diag = Ch.compose_reward(
                    bids, progs, p_hat, use_rep_penalty=use_rep_penalty
                )
                ch.update(bids, progs, r)

        # --- Phase 2: build the dataset from the frozen Challenger ----------
        bids, progs = ch.sample(n_candidates, rng)
        batch, pseudo, p_hat, idx = build_dataset(
            frozen, bids, progs, rng, m=m, delta=delta, use_filter=use_filter
        )
        kept_fraction = len(idx) / float(n_candidates)

        # Measured for the record only -- never fed back into training.
        pl_acc = pseudo_label_accuracy(batch, pseudo, idx)

        # --- Phase 3: train the Solver --------------------------------------
        if mode == "oracle":
            # Ceiling baseline: identical curriculum, real labels.
            targets = oracle_labels(batch, idx)
            loss, n_kept = train_on_pseudo(sol, batch, targets, idx, rng)
        else:
            loss, n_kept = train_on_pseudo(sol, batch, pseudo, idx, rng)

        per, overall = evaluate_all(sol, test)
        entry = {
            "iteration": it,
            "accuracy": overall,
            "per_bucket": per,
            "pseudo_label_accuracy": pl_acc,
            "kept_fraction": kept_fraction,
            "n_kept": n_kept,
            "mean_p_hat": float(p_hat.mean()),
            "train_loss": loss,
            "mean_difficulty": float(
                np.mean([D.DIFFICULTY[b] for b in batch.bucket_ids])
            ),
            "policy_mean_difficulty": ch.mean_difficulty(),
            "bucket_probs": list(ch.bucket_probs()),
            "sampled_bucket_hist": np.bincount(
                batch.bucket_ids, minlength=D.NUM_BUCKETS
            ).tolist(),
        }
        entry.update(ch_diag)
        log["iterations"].append(entry)
        if verbose:
            print(
                "[%s seed=%d] iter %d  acc %.1f%%  pseudo %.1f%%  kept %.1f%%  "
                "diff %.3f  reject %.1f%%"
                % (
                    mode, seed, it, 100 * overall, 100 * pl_acc,
                    100 * kept_fraction, entry["mean_difficulty"],
                    100 * ch_diag.get("format_reject_rate", 0.0),
                )
            )

    log["wall_seconds"] = time.time() - t0
    return log


def oracle_labels(batch, idx):
    """True labels for the kept tasks -- the ``oracle`` ceiling baseline ONLY.

    Reached only from ``mode="oracle"``, which exists to show how much of the gap
    is due to pseudo-label noise rather than to the curriculum.
    """
    # GROUND TRUTH: the oracle ceiling deliberately trains on real labels.
    D.assert_ground_truth_allowed("oracle")
    out = np.zeros((len(batch.programs), D.OUTPUT_CELLS), dtype=np.int64)
    for i in idx:
        truth = D.execute(
            batch.programs[i], batch.inputs[i], D.BUCKETS[batch.bucket_ids[i]][2]
        )
        G = D.BUCKETS[batch.bucket_ids[i]][1]
        for r in range(G):
            out[i, r * D.MAX_G : r * D.MAX_G + G] = truth[r]
    return out


def pseudo_label_accuracy(batch, pseudo, idx):
    """How often the pseudo-label is actually right.  REPORTING ONLY.

    This is the one number that needs ground truth outside evaluation, and the
    paper reports it too (Table 5).  It is computed *after* the dataset has been
    built, is returned only into the JSON log, and is never read by the
    Challenger, the filter, or the Solver's training step.
    """
    if len(idx) == 0:
        return 0.0
    # GROUND TRUTH: reporting only.  Nothing downstream consumes this.
    D.assert_ground_truth_allowed("eval")
    truth = [
        D.execute(
            batch.programs[i], batch.inputs[i], D.BUCKETS[batch.bucket_ids[i]][2]
        )
        for i in idx
    ]
    bids = [batch.bucket_ids[i] for i in idx]
    labels, cell_mask = D.encode_targets(truth, bids)
    return float(S.exact_match(pseudo[idx], labels, cell_mask).mean())
