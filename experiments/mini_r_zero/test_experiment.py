"""Correctness tests for the pieces that a wrong answer would hide.

Run with ``python test_experiment.py``.  No pytest dependency -- the repo has no
test tooling and the issue asks for a self-contained folder.

The gradient check is the important one: the Solver backpropagates through a
4-step chain of shared weights by hand, and a subtly wrong gradient would still
train *something*, just worse -- which would look exactly like "the loop does not
work" and would be attributed to the method instead of to the bug.
"""

from __future__ import annotations

import sys

import numpy as np

import challenger as Ch
import domain as D
import solver as S

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print("  PASS  %s" % name)
    else:
        print("  FAIL  %s %s" % (name, detail))
        FAILURES.append(name)


# ---------------------------------------------------------------------------


def test_dsl():
    print("DSL semantics")
    g = np.array([[0, 1, 2], [0, 0, 1], [2, 2, 0]])
    check("rot90 x4 == identity", np.array_equal(D.execute((0, 0, 0, 0), g, 3), g))
    check("flip_h x2 == identity", np.array_equal(D.execute((1, 1), g, 3), g))
    check("shift_rows x3 == identity (G=3)", np.array_equal(D.execute((2, 2, 2), g, 3), g))
    check("increment x3 == identity (C=3)", np.array_equal(D.execute((3, 3, 3), g, 3), g))
    check("swap_colors01 x2 == identity", np.array_equal(D.execute((5, 5), g, 3), g))
    check("rot90 x2 != identity", not np.array_equal(D.execute((0, 0), g, 3), g))
    check(
        "increment x2 != identity at C=3",
        not np.array_equal(D.execute((3, 3), g, 3), g),
    )
    # increment_colors must respect the palette
    out = D.execute((3,), np.array([[1, 1], [1, 1]]), 2)
    check("increment wraps within C", np.array_equal(out, np.zeros((2, 2))))


def test_identity_filter():
    print("Format check (identity programs)")
    check("increment x2 at C=2 is identity", D.is_identity(D.BUCKET_INDEX[(2, 3, 2)], (3, 3)))
    check(
        "increment x2 at C=3 is not identity",
        not D.is_identity(D.BUCKET_INDEX[(2, 3, 3)], (3, 3)),
    )
    check("rot90 x4 is identity", D.is_identity(D.BUCKET_INDEX[(4, 3, 2)], (0, 0, 0, 0)))
    # Every program flagged identity must really be a no-op on fresh grids.
    rng = np.random.default_rng(7)
    bid = D.BUCKET_INDEX[(3, 4, 3)]
    flagged = np.flatnonzero(D.identity_mask(bid))
    progs = D.bucket_programs(bid)
    ok = True
    for i in flagged[:40]:
        for _ in range(5):
            grid = rng.integers(0, 3, size=(4, 4))
            if not np.array_equal(D.execute(progs[i], grid, 3), grid):
                ok = False
    check("flagged-identity programs are no-ops on unseen grids", ok)


def test_ground_truth_guard():
    print("Ground-truth guard")
    for purpose in ("train", "challenger", "", None):
        try:
            D.assert_ground_truth_allowed(purpose)
            check("guard rejects purpose=%r" % purpose, False)
        except AssertionError:
            check("guard rejects purpose=%r" % purpose, True)
    try:
        D.assert_ground_truth_allowed("eval")
        D.assert_ground_truth_allowed("seed")
        check("guard allows seed and eval", True)
    except AssertionError as exc:
        check("guard allows seed and eval", False, str(exc))
    rng = np.random.default_rng(0)
    try:
        D.make_tasks([0], [(0,)], rng, with_labels=True, purpose="train")
        check("make_tasks refuses to label for training", False)
    except AssertionError:
        check("make_tasks refuses to label for training", True)


def test_encoding_roundtrip():
    print("Encoding")
    rng = np.random.default_rng(3)
    bids = [D.BUCKET_INDEX[(2, 3, 2)], D.BUCKET_INDEX[(3, 5, 4)]]
    progs = [(0, 1), (2, 3, 4)]
    batch = D.make_tasks(bids, progs, rng, with_labels=True, purpose="eval")
    state0, inside, onehot, active, tags, cmask = S.encode_tasks(batch)
    check("state rows are one-hot", np.allclose(state0.reshape(2, 25, 5).sum(2), 1.0))
    check("inside mask counts G*G cells", list(inside.sum(1)) == [9.0, 25.0])
    check("op one-hot is one per step", np.allclose(onehot.sum(2), 1.0))
    steps, act = D.encode_program_steps(progs)
    check("depth-2 program is right-padded", list(steps[0])[:2] == [0, 1])
    check("depth-3 program is right-padded", list(steps[1])[:3] == [2, 3, 4])
    check("active mask marks exactly the program's ops",
          list(act[0]) == [1, 1, 0, 0] and list(act[1]) == [1, 1, 1, 0])
    check("active mask sums to the depth", list(active.sum(1)) == [2.0, 3.0])
    check("colour mask matches palette", list(cmask[0]) == [1, 1, 0, 0] and list(cmask[1]) == [1, 1, 1, 1])
    labels, cell_mask = D.encode_targets(batch.outputs, bids)
    check("target mask matches inside mask", np.array_equal(cell_mask, inside))
    # A perfect prediction must score exact-match 1.0.
    check("exact_match rewards the true grid", S.exact_match(labels, labels, cell_mask).all())
    wrong = labels.copy()
    wrong[0, 0] = 1 - wrong[0, 0]
    check("exact_match punishes one wrong cell", not S.exact_match(wrong, labels, cell_mask)[0])
    # Cells outside the grid must be ignored.
    wrong2 = labels.copy()
    wrong2[0, 24] = 3
    check("exact_match ignores padding cells", S.exact_match(wrong2, labels, cell_mask)[0])


def test_majority_vote():
    print("Majority vote")
    cell_mask = np.ones((3, D.OUTPUT_CELLS), dtype=np.float32)
    preds = np.zeros((5, 3, D.OUTPUT_CELLS), dtype=np.int64)
    preds[:, 0] = 1          # unanimous
    preds[3:, 1] = 2         # 3 vs 2 split
    for k in range(5):       # all different
        preds[k, 2] = k
    pseudo, p_hat = S.majority_vote(preds, cell_mask)
    check("unanimous -> p_hat 1.0", p_hat[0] == 1.0)
    check("unanimous -> that answer", (pseudo[0] == 1).all())
    check("3-2 split -> p_hat 0.6", abs(p_hat[1] - 0.6) < 1e-9)
    check("3-2 split -> majority answer", (pseudo[1] == 0).all())
    check("all-different -> p_hat 0.2", abs(p_hat[2] - 0.2) < 1e-9)
    # Padding must not affect the key: differing padded cells still count as equal.
    cm = np.zeros((1, D.OUTPUT_CELLS), dtype=np.float32)
    cm[0, :9] = 1.0
    p2 = np.zeros((2, 1, D.OUTPUT_CELLS), dtype=np.int64)
    p2[1, 0, 20] = 3
    _, ph2 = S.majority_vote(p2, cm)
    check("padding cells excluded from the vote", ph2[0] == 1.0)


def test_solver_gradient():
    """Finite-difference check of the hand-written BPTT through the chain."""
    print("Solver gradient (finite differences through the 4-step chain)")
    rng = np.random.default_rng(11)
    sol = S.Solver(rng, hidden=16, dropout=0.0, mc_dropout=0.0)
    # float64 throughout: at float32 the finite-difference probe is swamped by
    # rounding and a correct gradient looks like a 3% error.
    sol.params = {k: v.astype(np.float64) for k, v in sol.params.items()}
    bids = [D.BUCKET_INDEX[(4, 3, 2)], D.BUCKET_INDEX[(3, 4, 3)]]
    progs = [(0, 1, 2, 3), (4, 5, 0)]
    batch = D.make_tasks(bids, progs, np.random.default_rng(5), with_labels=True, purpose="eval")
    enc = tuple(e.astype(np.float64) if e.dtype != np.int64 else e
                for e in S.encode_tasks(batch))
    labels, cell_mask = D.encode_targets(batch.outputs, bids)

    def loss_of(params):
        saved = sol.params
        sol.params = params
        probs, _ = sol._rollout(enc, None)
        n = probs.shape[0]
        onehot = np.zeros_like(probs)
        onehot[np.arange(n)[:, None], np.arange(D.OUTPUT_CELLS)[None, :], labels] = 1.0
        denom = max(float(cell_mask.sum()), 1.0)
        out = float(
            -(cell_mask * np.log(np.maximum((probs * onehot).sum(2), 1e-12))).sum() / denom
        )
        sol.params = saved
        return out

    # Capture analytic gradients without letting Adam move the weights.
    captured = {}
    real_adam = sol._adam
    sol._adam = lambda g, **kw: captured.update({k: v.copy() for k, v in g.items()})
    sol.train_step(enc, labels, cell_mask)
    sol._adam = real_adam

    eps = 1e-4
    worst, compared = 0.0, 0
    for name in ("W1", "b1", "W2", "b2", "W3", "b3"):
        arr = sol.params[name]
        idxs = [tuple(np.random.default_rng(i).integers(0, s) for s in arr.shape)
                for i in range(6)]
        for idx in idxs:
            up = {k: v.copy() for k, v in sol.params.items()}
            dn = {k: v.copy() for k, v in sol.params.items()}
            up[name][idx] += eps
            dn[name][idx] -= eps
            numeric = (loss_of(up) - loss_of(dn)) / (2 * eps)
            analytic = float(captured[name][idx])
            # Entries whose true gradient is ~0 carry no information: the
            # relative error there is dominated by float64 cancellation.
            if max(abs(numeric), abs(analytic)) < 1e-5:
                continue
            compared += 1
            worst = max(worst, abs(numeric - analytic) / max(abs(numeric), abs(analytic)))
    check("analytic gradient matches finite differences", worst < 1e-3 and compared >= 8,
          "(worst relative error %.4g over %d entries)" % (worst, compared))


def test_solver_learns():
    print("Solver can learn (sanity, not a benchmark)")
    rng = np.random.default_rng(2)
    sol = S.Solver(rng)
    import seed as SD

    bid = D.BUCKET_INDEX[(1, 3, 2)]
    SD.seed_train(sol, [bid], steps=400, rng=rng)
    test = D.held_out_set(n_per_bucket=32)
    acc = S.evaluate(sol, test[bid])
    check("400 steps reach >70% on the easiest bucket", acc > 0.70,
          "(got %.1f%%)" % (100 * acc))


def test_challenger():
    print("Challenger")
    rng = np.random.default_rng(4)
    ch = Ch.Challenger(rng)
    r = Ch.uncertainty_reward(np.array([0.0, 0.25, 0.5, 0.75, 1.0]))
    check("uncertainty reward peaks at p_hat=0.5", abs(r[2] - 1.0) < 1e-9)
    check("uncertainty reward is 0 at p_hat=0", abs(r[0]) < 1e-9)
    check("uncertainty reward is 0 at p_hat=1", abs(r[4]) < 1e-9)
    check("uncertainty reward is symmetric", abs(r[1] - r[3]) < 1e-9)

    # Repetition penalty: a batch piled onto one cluster must be penalised more
    # than a spread-out batch.
    same = Ch.repetition_penalty([0] * 16, [(0, 1)] * 16)
    spread = Ch.repetition_penalty(list(range(16)), [(i % 6,) for i in range(16)])
    check("repetition penalty punishes duplicates", same.mean() > spread.mean(),
          "(same %.2f vs spread %.2f)" % (same.mean(), spread.mean()))
    check("repetition penalty is 1.0 for a fully duplicated batch", abs(same[0] - 1.0) < 1e-9)

    # GRPO-lite must push probability toward the rewarded bucket.
    hot = D.BUCKET_INDEX[(2, 4, 3)]
    before = ch.bucket_probs()[hot]
    for _ in range(30):
        bids = [hot] * 32 + [D.SEED_BUCKET_ID] * 32
        progs = [D.sample_from_bucket(b, 1, rng)[0] for b in bids]
        rewards = np.array([1.0] * 32 + [0.0] * 32)
        ch.update(bids, progs, rewards)
    after = ch.bucket_probs()[hot]
    check("GRPO-lite raises the rewarded bucket's probability", after > before + 1e-3,
          "(%.4f -> %.4f)" % (before, after))
    check("bucket_probs stays a distribution", abs(ch.bucket_probs().sum() - 1.0) < 1e-6)

    # Fixed-curriculum policies.
    u = Ch.FixedChallenger("uniform")
    bids, _ = u.sample(2000, rng)
    check("uniform curriculum covers every bucket", len(set(bids)) == D.NUM_BUCKETS)
    h = Ch.FixedChallenger("hardest")
    bids, _ = h.sample(50, rng)
    check("hardest curriculum only samples the hardest bucket",
          set(bids) == {D.HARDEST_BUCKET_ID})


def main():
    for fn in (
        test_dsl,
        test_identity_filter,
        test_ground_truth_guard,
        test_encoding_roundtrip,
        test_majority_vote,
        test_solver_gradient,
        test_challenger,
        test_solver_learns,
    ):
        fn()
        print()
    if FAILURES:
        print("%d FAILED: %s" % (len(FAILURES), ", ".join(FAILURES)))
        return 1
    print("all tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
