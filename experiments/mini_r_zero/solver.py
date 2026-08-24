"""The Solver: a step-wise numpy network, MC-dropout sampling, majority vote.

ARCHITECTURE, AND WHY IT IS NOT THE FLAT MLP THE ISSUE SUGGESTED
----------------------------------------------------------------
The issue proposes a flat MLP over one-hot ``[program tokens || input grid]``.
That was built first and it fails M0 for a structural reason (see
``WORK_LOG-4.md``): a flat MLP seeded on depth-1 programs has never activated
its depth-2 program slots, so depth-2 accuracy is ~0%.  Difficulty becomes a
cliff, there is no reachable frontier, and the R-Zero loop has nothing to
bootstrap from.

This Solver instead applies **one shared, op-conditioned block per program
step**, feeding its own soft prediction forward as the next step's input:

    state_0 = input grid
    state_t = softmax(block(state_{t-1}, op_t, size tags))
    answer  = argmax(state_d)

The block is a 2-hidden-layer MLP (~0.4M params) and the same weights are reused
at every step, so depth-1 competence transfers to depth 4 -- imperfectly, because
each step consumes the previous step's *predicted* grid and errors compound.
That compounding is what produces a graded difficulty slope instead of a cliff,
and it is also the honest analogue of a reasoning chain, where a mistake early in
the chain corrupts everything after it.

WHERE THE ``m`` ANSWERS COME FROM
---------------------------------
The issue rules out independent per-cell temperature sampling, and rightly: the
modal sample would equal the per-cell argmax, so the vote would return exactly
the greedy output and the loop would distil the Solver into itself.  It suggests
MC-dropout instead.  That was tried and also fails here, for the opposite reason
(see ``WORK_LOG-4.md``): dropout noise injected into a 4-step chain compounds,
every sample lands somewhere different, ``p_hat`` pins to 0.1, and the vote is
*far worse* than greedy -- equally useless as a training signal.

What works is the strongest reading of the issue's own phrase "m genuinely
different functions": a **committee of independently initialised Solvers**, each
voting with its own greedy answer.  Members agree on what they have all
mastered, diverge on what none of them has, and disagree partially in between --
which is exactly the ``p_hat`` signal R-Zero needs, and it makes the consensus
genuinely better than any single member.  MC-dropout is kept as an optional
top-up (``mc_dropout > 0``) but defaults to off.
"""

from __future__ import annotations

import numpy as np

import domain as D

HIDDEN = 256


def _he(rng, fan_in, fan_out):
    return (rng.standard_normal((fan_in, fan_out)) * np.sqrt(2.0 / fan_in)).astype(
        np.float32
    )


class Solver:
    def __init__(self, rng, hidden=HIDDEN, dropout=0.05, mc_dropout=0.0, lr=2e-3):
        self.rng = rng
        self.dropout = dropout
        self.mc_dropout = mc_dropout
        self.lr = lr
        self.hidden = hidden
        self.params = {
            "W1": _he(rng, D.STEP_INPUT_DIM, hidden),
            "b1": np.zeros(hidden, dtype=np.float32),
            "W2": _he(rng, hidden, hidden),
            "b2": np.zeros(hidden, dtype=np.float32),
            "W3": _he(rng, hidden, D.OUTPUT_DIM) * 0.1,
            "b3": np.zeros(D.OUTPUT_DIM, dtype=np.float32),
        }
        self._m = {k: np.zeros_like(v) for k, v in self.params.items()}
        self._v = {k: np.zeros_like(v) for k, v in self.params.items()}
        self._t = 0

    def num_params(self):
        return sum(v.size for v in self.params.values())

    def clone(self):
        """A frozen snapshot: the *frozen Solver* the Challenger probes."""
        other = Solver.__new__(Solver)
        other.rng = np.random.default_rng(int(self.rng.integers(1 << 62)))
        other.dropout = self.dropout
        other.mc_dropout = self.mc_dropout
        other.lr = self.lr
        other.hidden = self.hidden
        other.params = {k: v.copy() for k, v in self.params.items()}
        other._m = {k: np.zeros_like(v) for k, v in self.params.items()}
        other._v = {k: np.zeros_like(v) for k, v in self.params.items()}
        other._t = 0
        return other

    # -- one step ----------------------------------------------------------

    def _dropout_masks(self, rate, rng):
        """Two shared masks -> one subnetwork, applied to the whole batch."""
        if rate <= 0.0:
            return None
        keep = 1.0 - rate
        m1 = (rng.random(self.hidden) < keep).astype(np.float32) / keep
        m2 = (rng.random(self.hidden) < keep).astype(np.float32) / keep
        return (m1, m2)

    def _step(self, state, ops_onehot, tags, masks):
        x = np.concatenate([state, ops_onehot, tags], axis=1)
        p = self.params
        a1 = np.maximum(x @ p["W1"] + p["b1"], 0.0)
        if masks is not None:
            a1 = a1 * masks[0]
        a2 = np.maximum(a1 @ p["W2"] + p["b2"], 0.0)
        if masks is not None:
            a2 = a2 * masks[1]
        logits = a2 @ p["W3"] + p["b3"]
        return x, a1, a2, logits

    @staticmethod
    def _softmax(logits, cmask, n):
        z = logits.reshape(n, D.OUTPUT_CELLS, D.MAX_C)
        z = z + (1.0 - cmask[:, None, :]) * -1e9
        z = z - z.max(axis=2, keepdims=True)
        e = np.exp(z)
        return e / e.sum(axis=2, keepdims=True)

    @staticmethod
    def _to_state(probs, inside, n):
        """Pack a colour distribution back into the (cells x channels) state.

        The dtype follows ``probs`` rather than being pinned to float32, so the
        finite-difference gradient check in ``test_experiment.py`` can run the
        whole chain in float64.  Pinning it here silently truncated every state
        to float32 and made a correct gradient look 100% wrong.
        """
        st = np.zeros((n, D.OUTPUT_CELLS, D.MAX_C + 1), dtype=probs.dtype)
        st[:, :, : D.MAX_C] = probs * inside[:, :, None]
        st[:, :, D.PAD_CELL] = 1.0 - inside
        return st.reshape(n, D.STATE_DIM)

    # -- chain forward -----------------------------------------------------

    def _rollout(self, enc, masks, keep_cache=False):
        """Run the chain.  ``enc`` comes from ``encode_tasks``.

        Steps past a program's depth are inactive and carry the state through
        unchanged, so each task gets exactly as many block applications as its
        program has ops.
        """
        state0, inside, steps_onehot, active, tags, cmask = enc
        n = state0.shape[0]
        state = state0
        cache = []
        for t in range(D.MAX_D):
            x, a1, a2, logits = self._step(state, steps_onehot[t], tags, masks)
            probs = self._softmax(logits, cmask, n)
            new_state = self._to_state(probs, inside, n)
            a = active[:, t][:, None]
            state = a * new_state + (1.0 - a) * state
            if keep_cache:
                cache.append((x, a1, a2, probs, a))
        # On cells inside the grid the colour channels of the state *are* the
        # final colour distribution, so no extra forward pass is needed.
        final = state.reshape(n, D.OUTPUT_CELLS, D.MAX_C + 1)[:, :, : D.MAX_C]
        return final, cache

    def predict(self, enc):
        """Deterministic greedy prediction, ``(n, cells)`` colour indices."""
        probs, _ = self._rollout(enc, None)
        return probs.argmax(axis=2)

    def sample_answers(self, enc, m, rng=None):
        """``m`` whole-grid answers from ``m`` different dropout subnetworks."""
        rng = rng or self.rng
        n = enc[0].shape[0]
        out = np.empty((m, n, D.OUTPUT_CELLS), dtype=np.int64)
        for k in range(m):
            masks = self._dropout_masks(self.mc_dropout, rng)
            probs, _ = self._rollout(enc, masks)
            out[k] = probs.argmax(axis=2)
        return out

    # -- training (BPTT through the chain) ---------------------------------

    def train_step(self, enc, labels, cell_mask):
        """One Adam step on masked cross-entropy at the *final* step.

        There is no supervision for intermediate states -- that is the point, and
        it is why gradients have to flow back through the whole chain.
        """
        state0, inside, steps_onehot, active, tags, cmask = enc
        n = state0.shape[0]
        masks = self._dropout_masks(self.dropout, self.rng)
        probs, cache = self._rollout(enc, masks, keep_cache=True)

        onehot = np.zeros_like(probs)
        onehot[np.arange(n)[:, None], np.arange(D.OUTPUT_CELLS)[None, :], labels] = 1.0
        denom = max(float(cell_mask.sum()), 1.0)
        loss = float(
            -(cell_mask * np.log(np.maximum((probs * onehot).sum(axis=2), 1e-12))).sum()
            / denom
        )

        p = self.params
        grads = {k: np.zeros_like(v) for k, v in p.items()}

        # Seed the backward pass at the *final state*, not at a particular step's
        # logits: which step produced it differs per example.  Pushing this
        # through a step's softmax below reproduces the usual (probs - onehot).
        dfinal = -(onehot * cell_mask[:, :, None]) / (
            np.maximum(probs, 1e-12) * denom
        )
        dstate = np.zeros((n, D.STATE_DIM), dtype=dfinal.dtype)
        dstate.reshape(n, D.OUTPUT_CELLS, D.MAX_C + 1)[:, :, : D.MAX_C] = dfinal

        for t in range(D.MAX_D - 1, -1, -1):
            x, a1, a2, probs_t, a = cache[t]
            # An inactive step passed the state straight through, so its gradient
            # skips the block entirely.
            dnew = dstate * a
            dcarry = dstate * (1.0 - a)
            dprobs = (
                dnew.reshape(n, D.OUTPUT_CELLS, D.MAX_C + 1)[:, :, : D.MAX_C]
                * inside[:, :, None]
            )
            dlogits = probs_t * (
                dprobs - (dprobs * probs_t).sum(axis=2, keepdims=True)
            )
            dl = dlogits.reshape(n, D.OUTPUT_DIM)
            grads["W3"] += a2.T @ dl
            grads["b3"] += dl.sum(axis=0)
            da2 = dl @ p["W3"].T
            if masks is not None:
                da2 = da2 * masks[1]
            dz2 = da2 * (a2 > 0)
            grads["W2"] += a1.T @ dz2
            grads["b2"] += dz2.sum(axis=0)
            da1 = dz2 @ p["W2"].T
            if masks is not None:
                da1 = da1 * masks[0]
            dz1 = da1 * (a1 > 0)
            grads["W1"] += x.T @ dz1
            grads["b1"] += dz1.sum(axis=0)
            dstate = (dz1 @ p["W1"].T)[:, : D.STATE_DIM] + dcarry

        self._adam(grads)
        return loss

    def _adam(self, grads, b1=0.9, b2=0.999, eps=1e-8, clip=5.0):
        self._t += 1
        bc1 = 1.0 - b1**self._t
        bc2 = 1.0 - b2**self._t
        # Chained steps share weights, so raw gradients can spike; clipping keeps
        # the deep-program batches from destabilising the shared block.
        total = np.sqrt(sum(float((g * g).sum()) for g in grads.values()))
        scale = min(1.0, clip / (total + 1e-8))
        for k, g in grads.items():
            g = g * scale
            self._m[k] = b1 * self._m[k] + (1.0 - b1) * g
            self._v[k] = b2 * self._v[k] + (1.0 - b2) * (g * g)
            mhat = self._m[k] / bc1
            vhat = self._v[k] / bc2
            self.params[k] -= (self.lr * mhat / (np.sqrt(vhat) + eps)).astype(
                np.float32
            )


# ---------------------------------------------------------------------------
# Majority vote
# ---------------------------------------------------------------------------


def _grid_keys(preds, cell_mask):
    """Collapse each predicted grid to one int64 key (2 bits per cell)."""
    masked = preds * cell_mask.astype(np.int64)[None, :, :]
    # 25 cells x 2 bits = 50 bits, so int64 arithmetic stays exact.
    weights = 4 ** np.arange(D.OUTPUT_CELLS, dtype=np.int64)
    return (masked * weights[None, None, :]).sum(axis=2)


def majority_vote(preds, cell_mask):
    """Modal whole-grid answer and its agreement fraction.

    ``preds`` is ``(m, n, cells)``.  Returns ``(pseudo_labels, p_hat)`` with
    ``pseudo_labels`` of shape ``(n, cells)`` and ``p_hat`` of shape ``(n,)``.

    This is the *only* label source the training loop is allowed to use.
    """
    m, n, _ = preds.shape
    keys = _grid_keys(preds, cell_mask)  # (m, n)
    counts = (keys[None, :, :] == keys[:, None, :]).sum(axis=1)  # (m, n)
    best = counts.argmax(axis=0)
    p_hat = counts.max(axis=0) / float(m)
    pseudo = preds[best, np.arange(n)]
    return pseudo, p_hat


# ---------------------------------------------------------------------------
# Committee: m genuinely different functions
# ---------------------------------------------------------------------------


class Committee:
    """``k`` independently initialised Solvers, voting as one.

    MC-dropout alone turned out not to give an ensemble that beats its own greedy
    output (see ``WORK_LOG-4.md``), which makes majority-vote pseudo-labels
    worthless as a training signal.  Independently initialised members converge to
    genuinely different functions with genuinely different errors, so their
    consensus *is* better than any single member -- which is exactly the property
    R-Zero relies on when it votes over independently sampled reasoning chains.
    """

    def __init__(self, rng, k=10, **kw):
        seeds = rng.integers(1 << 62, size=k)
        self.members = [Solver(np.random.default_rng(int(s)), **kw) for s in seeds]
        self.k = k
        self.rng = rng

    def num_params(self):
        return sum(mem.num_params() for mem in self.members)

    def clone(self):
        other = Committee.__new__(Committee)
        other.members = [mem.clone() for mem in self.members]
        other.k = self.k
        other.rng = np.random.default_rng(int(self.rng.integers(1 << 62)))
        return other

    def predict(self, enc):
        """Greedy prediction of member 0 -- the "single model" reference."""
        return self.members[0].predict(enc)

    def member_predictions(self, enc):
        return np.stack([mem.predict(enc) for mem in self.members])

    def vote_predict(self, enc, cell_mask):
        """Committee consensus under greedy decoding."""
        preds = np.stack([mem.predict(enc) for mem in self.members])
        pseudo, _ = majority_vote(preds, cell_mask)
        return pseudo

    def sample_answers(self, enc, m, rng=None):
        """``m`` answers, one per committee member.

        Run with ``k == m`` (the default is ``k = m = 10``) so every sample is an
        independent function and ``p_hat`` is an unbiased agreement fraction.  If
        ``k < m`` some members would be counted twice and ``p_hat`` would be
        inflated by the duplication rather than by real consensus.
        """
        rng = rng or self.rng
        n = enc[0].shape[0]
        out = np.empty((m, n, D.OUTPUT_CELLS), dtype=np.int64)
        for j in range(m):
            mem = self.members[j % self.k]
            masks = mem._dropout_masks(mem.mc_dropout, rng)
            probs, _ = mem._rollout(enc, masks)
            out[j] = probs.argmax(axis=2)
        return out

    def train_step(self, enc, labels, cell_mask):
        return float(
            np.mean([mem.train_step(enc, labels, cell_mask) for mem in self.members])
        )


# ---------------------------------------------------------------------------
# Encoding / evaluation helpers
# ---------------------------------------------------------------------------


def encode_tasks(batch):
    """Everything the Solver needs from a ``TaskBatch``, minus the labels."""
    n = len(batch.programs)
    state0, inside = D.encode_state(batch.inputs, batch.bucket_ids)
    steps, active = D.encode_program_steps(batch.programs)
    onehot = np.zeros((D.MAX_D, n, D.OP_DIM), dtype=np.float32)
    for t in range(D.MAX_D):
        onehot[t, np.arange(n), steps[:, t]] = 1.0
    tags = D.encode_size_tags(batch.bucket_ids)
    cmask = D.color_mask(batch.bucket_ids)
    return state0, inside, onehot, active, tags, cmask


def exact_match(pred_cells, labels, cell_mask):
    """Per-example exact match over the valid cells of the grid."""
    agree = (pred_cells == labels) | (cell_mask == 0)
    return agree.all(axis=1)


def evaluate(solver, batch):
    """Greedy exact-match accuracy on a labelled batch.  Evaluation only.

    For a committee this is the *mean accuracy of a single member*, not the
    accuracy of the committee vote.  That keeps the headline number comparable to
    the paper's single Solver, and avoids flattering the method by reporting the
    ensemble's answer as though one model had produced it.  ``evaluate_vote``
    reports the consensus separately.
    """
    # GROUND TRUTH: evaluation only.
    D.assert_ground_truth_allowed("eval")
    enc = encode_tasks(batch)
    labels, cell_mask = D.encode_targets(batch.outputs, batch.bucket_ids)
    if isinstance(solver, Committee):
        preds = solver.member_predictions(enc)
        return float(
            np.mean([exact_match(p, labels, cell_mask).mean() for p in preds])
        )
    return float(exact_match(solver.predict(enc), labels, cell_mask).mean())


def evaluate_vote(solver, batch):
    """Exact-match accuracy of the committee consensus.  Evaluation only."""
    # GROUND TRUTH: evaluation only.
    D.assert_ground_truth_allowed("eval")
    enc = encode_tasks(batch)
    labels, cell_mask = D.encode_targets(batch.outputs, batch.bucket_ids)
    if not isinstance(solver, Committee):
        return evaluate(solver, batch)
    preds = solver.member_predictions(enc)
    pseudo, _ = majority_vote(preds, cell_mask)
    return float(exact_match(pseudo, labels, cell_mask).mean())
