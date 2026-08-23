"""The Solver: a small numpy MLP, plus MC-dropout sampling and majority vote.

Architecture: ``INPUT_DIM -> 512 -> 512 -> 25 cells x 4 colours`` with ReLU and
dropout, ~0.4M parameters, trained with a hand-rolled Adam.  Per-cell softmax is
masked to the colours that exist in each task's palette.

WHY MC-DROPOUT AND NOT PER-CELL TEMPERATURE SAMPLING
----------------------------------------------------
Independent per-cell sampling would make the modal whole-grid sample equal to
the per-cell argmax, so the majority vote would return exactly the greedy output
and the loop would be distilling the Solver into itself -- no information enters
and no improvement is possible.  Instead each of the ``m`` samples uses a
different dropout mask *shared across the batch*, i.e. ``m`` genuinely different
subnetworks, and the vote is taken over whole grids.  That is this toy's
stand-in for "sample m independent reasoning paths".
"""

from __future__ import annotations

import numpy as np

import domain as D

HIDDEN = 512


def _he(rng, fan_in, fan_out):
    return (rng.standard_normal((fan_in, fan_out)) * np.sqrt(2.0 / fan_in)).astype(
        np.float32
    )


class Solver:
    def __init__(self, rng, hidden=HIDDEN, dropout=0.1, mc_dropout=0.25, lr=2e-3):
        self.rng = rng
        self.dropout = dropout
        self.mc_dropout = mc_dropout
        self.lr = lr
        self.params = {
            "W1": _he(rng, D.INPUT_DIM, hidden),
            "b1": np.zeros(hidden, dtype=np.float32),
            "W2": _he(rng, hidden, hidden),
            "b2": np.zeros(hidden, dtype=np.float32),
            "W3": _he(rng, hidden, D.OUTPUT_DIM),
            "b3": np.zeros(D.OUTPUT_DIM, dtype=np.float32),
        }
        self._m = {k: np.zeros_like(v) for k, v in self.params.items()}
        self._v = {k: np.zeros_like(v) for k, v in self.params.items()}
        self._t = 0

    def num_params(self):
        return sum(v.size for v in self.params.values())

    def clone(self):
        """A frozen snapshot, used as the *frozen Solver* the Challenger probes."""
        other = Solver.__new__(Solver)
        other.rng = np.random.default_rng(self.rng.integers(1 << 62))
        other.dropout = self.dropout
        other.mc_dropout = self.mc_dropout
        other.lr = self.lr
        other.params = {k: v.copy() for k, v in self.params.items()}
        other._m = {k: np.zeros_like(v) for k, v in self.params.items()}
        other._v = {k: np.zeros_like(v) for k, v in self.params.items()}
        other._t = 0
        return other

    # -- forward -----------------------------------------------------------

    def _forward(self, x, masks=None):
        """``masks`` is a pair of shared dropout masks, or None for a clean pass."""
        p = self.params
        a1 = np.maximum(x @ p["W1"] + p["b1"], 0.0)
        if masks is not None:
            a1 = a1 * masks[0]
        a2 = np.maximum(a1 @ p["W2"] + p["b2"], 0.0)
        if masks is not None:
            a2 = a2 * masks[1]
        logits = a2 @ p["W3"] + p["b3"]
        return a1, a2, logits

    def _masked_logits(self, logits, cmask):
        """Reshape to ``(n, cells, colours)`` and forbid absent colours."""
        n = logits.shape[0]
        z = logits.reshape(n, D.OUTPUT_CELLS, D.MAX_C)
        return z + (1.0 - cmask[:, None, :]) * -1e9

    def _dropout_masks(self, rate, rng):
        """Two shared masks -> one subnetwork applied to the whole batch."""
        if rate <= 0.0:
            return None
        keep = 1.0 - rate
        m1 = (rng.random(self.params["b1"].shape) < keep).astype(np.float32) / keep
        m2 = (rng.random(self.params["b2"].shape) < keep).astype(np.float32) / keep
        return (m1, m2)

    def predict(self, x, cmask):
        """Deterministic greedy prediction, ``(n, cells)`` colour indices."""
        _, _, logits = self._forward(x)
        return self._masked_logits(logits, cmask).argmax(axis=2)

    def sample_answers(self, x, cmask, m, rng=None):
        """``m`` whole-grid answers from ``m`` different dropout subnetworks."""
        rng = rng or self.rng
        out = np.empty((m, x.shape[0], D.OUTPUT_CELLS), dtype=np.int64)
        for k in range(m):
            masks = self._dropout_masks(self.mc_dropout, rng)
            _, _, logits = self._forward(x, masks)
            out[k] = self._masked_logits(logits, cmask).argmax(axis=2)
        return out

    # -- training ----------------------------------------------------------

    def train_step(self, x, labels, cell_mask, cmask):
        """One Adam step on masked per-cell cross-entropy.  Returns the loss."""
        n = x.shape[0]
        masks = self._dropout_masks(self.dropout, self.rng)
        a1, a2, logits = self._forward(x, masks)
        z = self._masked_logits(logits, cmask)
        z = z - z.max(axis=2, keepdims=True)
        e = np.exp(z)
        probs = e / e.sum(axis=2, keepdims=True)

        onehot = np.zeros_like(probs)
        onehot[np.arange(n)[:, None], np.arange(D.OUTPUT_CELLS)[None, :], labels] = 1.0

        denom = max(cell_mask.sum(), 1.0)
        loss = float(
            -(cell_mask * np.log(np.maximum((probs * onehot).sum(axis=2), 1e-12))).sum()
            / denom
        )

        dlogits = (probs - onehot) * cell_mask[:, :, None] / denom
        dlogits = dlogits.reshape(n, D.OUTPUT_DIM).astype(np.float32)

        p = self.params
        grads = {}
        grads["W3"] = a2.T @ dlogits
        grads["b3"] = dlogits.sum(axis=0)
        da2 = dlogits @ p["W3"].T
        if masks is not None:
            da2 = da2 * masks[1]
        dz2 = da2 * (a2 > 0)
        grads["W2"] = a1.T @ dz2
        grads["b2"] = dz2.sum(axis=0)
        da1 = dz2 @ p["W2"].T
        if masks is not None:
            da1 = da1 * masks[0]
        dz1 = da1 * (a1 > 0)
        grads["W1"] = x.T @ dz1
        grads["b1"] = dz1.sum(axis=0)

        self._adam(grads)
        return loss

    def _adam(self, grads, b1=0.9, b2=0.999, eps=1e-8):
        self._t += 1
        bc1 = 1.0 - b1**self._t
        bc2 = 1.0 - b2**self._t
        for k, g in grads.items():
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

    ``preds`` is ``(m, n, cells)``.  Returns ``(pseudo_labels, p_hat)`` where
    ``pseudo_labels`` is ``(n, cells)`` and ``p_hat`` is ``(n,)``.

    This is the *only* label source the training loop is allowed to use.
    """
    m, n, _ = preds.shape
    keys = _grid_keys(preds, cell_mask)  # (m, n)
    eq = keys[None, :, :] == keys[:, None, :]  # (m, m, n)
    counts = eq.sum(axis=1)  # (m, n): agreement of each sample
    best = counts.argmax(axis=0)  # (n,)
    p_hat = counts.max(axis=0) / float(m)
    pseudo = preds[best, np.arange(n)]
    return pseudo, p_hat


# ---------------------------------------------------------------------------
# Evaluation helpers
# ---------------------------------------------------------------------------


def exact_match(pred_cells, labels, cell_mask):
    """Per-example exact match over the valid cells of the grid."""
    agree = (pred_cells == labels) | (cell_mask == 0)
    return agree.all(axis=1)


def encode_tasks(batch):
    x = D.encode_batch(batch.programs, batch.inputs, batch.bucket_ids)
    cmask = D.color_mask(batch.bucket_ids)
    return x, cmask


def evaluate(solver, batch):
    """Greedy exact-match accuracy on a labelled batch.  Evaluation only."""
    # GROUND TRUTH: evaluation only.
    D.assert_ground_truth_allowed("eval")
    x, cmask = encode_tasks(batch)
    labels, cell_mask = D.encode_targets(batch.outputs, batch.bucket_ids)
    pred = solver.predict(x, cmask)
    return float(exact_match(pred, labels, cell_mask).mean())
