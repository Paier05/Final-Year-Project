"""The Challenger: a categorical policy over ``(bucket, program)``.

The policy is hierarchical -- logits over the 36 difficulty buckets, and logits
over the programs inside each bucket -- rather than one flat vector over all
13,986 ``(bucket, program)`` pairs.  Both are still just logit vectors, but the
split means bucket-level credit assignment does not have to be rediscovered
through thousands of sparsely-visited program slots, and it makes the curriculum
plot read directly off the policy.

Rewards follow the paper:

    r_uncertainty(x) = 1 - 2 * |p_hat(x) - 1/2|      # peaks at p_hat = 0.5
    r_rep(x_i)       = lam * |C_k| / B               # C_k = x_i's cluster
    r(x_i)           = max(0, r_uncertainty - r_rep) # 0 if the format check fails

``p_hat`` comes from the frozen Solver's majority vote.  **No ground-truth label
is involved anywhere in this file** -- the Challenger has no way to know whether
the tasks it invents are being answered correctly, only how much the Solver
agrees with itself.
"""

from __future__ import annotations

import numpy as np

import domain as D


def uncertainty_reward(p_hat):
    """``1 - 2|p_hat - 1/2|``: peaks at total ambiguity, zero at both extremes."""
    return 1.0 - 2.0 * np.abs(np.asarray(p_hat, dtype=np.float64) - 0.5)


def _cluster_key(bucket_id, program):
    """Cheap near-duplicate key: ``(bucket, first op)``.

    The paper clusters by BLEU distance between question texts.  Here the issue
    suggests ``(depth, first op)``; the bucket already carries the depth, and
    including G and C keeps tasks that merely share a depth from being treated as
    duplicates of each other.
    """
    return (bucket_id, program[0])


def repetition_penalty(bucket_ids, programs, lam=1.0):
    """``lam * |C_k| / B`` for each item in the batch."""
    keys = [_cluster_key(b, p) for b, p in zip(bucket_ids, programs)]
    counts = {}
    for k in keys:
        counts[k] = counts.get(k, 0) + 1
    B = float(len(keys))
    return lam * np.array([counts[k] for k in keys], dtype=np.float64) / B


def format_ok(bucket_ids, programs):
    """False where the program is semantically the identity.

    R-Zero zeroes the reward for malformed questions.  The toy analogue is the
    degenerate task: a program that does nothing is trivially answerable, so the
    Solver agrees with itself at some fixed rate and the Challenger could farm
    uncertainty from it forever without ever proposing anything real.  This is
    where reward hacking would show up, so the loop logs how often it fires.
    """
    return np.array(
        [not D.is_identity(b, p) for b, p in zip(bucket_ids, programs)], dtype=bool
    )


def compose_reward(bucket_ids, programs, p_hat, lam=1.0, use_rep_penalty=True):
    """Full Challenger reward plus the diagnostics the loop logs."""
    r_unc = uncertainty_reward(p_hat)
    r_rep = (
        repetition_penalty(bucket_ids, programs, lam)
        if use_rep_penalty
        else np.zeros_like(r_unc)
    )
    ok = format_ok(bucket_ids, programs)
    r = np.maximum(0.0, r_unc - r_rep)
    r = np.where(ok, r, 0.0)
    return r, {
        "mean_r_uncertainty": float(r_unc.mean()),
        "mean_r_rep": float(r_rep.mean()),
        "mean_reward": float(r.mean()),
        "format_reject_rate": float(1.0 - ok.mean()),
    }


class Challenger:
    """Hierarchical categorical policy trained with GRPO-lite."""

    def __init__(self, rng, lr=0.5, lam=1.0, use_rep_penalty=True):
        self.rng = rng
        self.lr = lr
        self.lam = lam
        self.use_rep_penalty = use_rep_penalty
        self.bucket_logits = np.zeros(D.NUM_BUCKETS, dtype=np.float64)
        self.program_logits = {
            b: np.zeros(len(D.bucket_programs(b)), dtype=np.float64)
            for b in range(D.NUM_BUCKETS)
        }
        self.trained = True

    # -- distributions -----------------------------------------------------

    @staticmethod
    def _softmax(z):
        e = np.exp(z - z.max())
        return e / e.sum()

    def bucket_probs(self):
        return self._softmax(self.bucket_logits)

    def program_probs(self, bucket_id):
        return self._softmax(self.program_logits[bucket_id])

    def mean_difficulty(self):
        return float(np.dot(self.bucket_probs(), D.DIFFICULTY))

    # -- sampling ----------------------------------------------------------

    def sample(self, n, rng=None):
        """Sample ``n`` tasks as ``(bucket_ids, programs)``.

        Identity programs are deliberately left in the support: the format check
        has to be able to fire, otherwise the reward-hacking rate is unobservable.
        """
        rng = rng or self.rng
        bucket_ids = list(rng.choice(D.NUM_BUCKETS, size=n, p=self.bucket_probs()))
        bucket_ids = [int(b) for b in bucket_ids]
        programs = []
        for b in bucket_ids:
            progs = D.bucket_programs(b)
            idx = rng.choice(len(progs), p=self.program_probs(b))
            programs.append(progs[int(idx)])
        return bucket_ids, programs

    # -- GRPO-lite ---------------------------------------------------------

    def update(self, bucket_ids, programs, rewards):
        """Group-normalised REINFORCE.

        Advantages are ``(r - mean) / std`` over the sampled group, exactly GRPO's
        group baseline, and there is no value function -- which is the whole point
        of GRPO and keeps this to a handful of lines.
        """
        r = np.asarray(rewards, dtype=np.float64)
        std = r.std()
        if std < 1e-8:
            # A group with no reward spread carries no signal; a zero-std
            # normalisation would just amplify floating-point noise.
            return 0.0
        adv = (r - r.mean()) / (std + 1e-8)

        bp = self.bucket_probs()
        gb = np.zeros_like(self.bucket_logits)
        gp = {}
        n = len(bucket_ids)
        for i, (b, prog) in enumerate(zip(bucket_ids, programs)):
            # d log p(b) / d logits = onehot(b) - p
            gb -= adv[i] * bp
            gb[b] += adv[i]
            if b not in gp:
                gp[b] = (np.zeros_like(self.program_logits[b]), self.program_probs(b))
            grad, pp = gp[b]
            idx = D.bucket_programs(b).index(prog)
            grad -= adv[i] * pp
            grad[idx] += adv[i]

        self.bucket_logits += self.lr * gb / n
        for b, (grad, _) in gp.items():
            self.program_logits[b] += self.lr * grad / n
        # Keep logits bounded so the policy can still move after a long run.
        self.bucket_logits -= self.bucket_logits.mean()
        np.clip(self.bucket_logits, -20.0, 20.0, out=self.bucket_logits)
        return float(np.abs(adv).mean())


class FixedChallenger:
    """A non-learning curriculum: the paper's *untrained Challenger* baselines."""

    def __init__(self, mode):
        if mode not in ("uniform", "hardest"):
            raise ValueError("unknown fixed curriculum: %r" % mode)
        self.mode = mode
        self.trained = False
        if mode == "uniform":
            self._probs = np.full(D.NUM_BUCKETS, 1.0 / D.NUM_BUCKETS)
        else:
            self._probs = np.zeros(D.NUM_BUCKETS)
            self._probs[D.HARDEST_BUCKET_ID] = 1.0

    def bucket_probs(self):
        return self._probs

    def mean_difficulty(self):
        return float(np.dot(self._probs, D.DIFFICULTY))

    def sample(self, n, rng):
        bucket_ids = [int(b) for b in rng.choice(D.NUM_BUCKETS, size=n, p=self._probs)]
        programs = []
        for b in bucket_ids:
            progs = D.bucket_programs(b)
            programs.append(progs[int(rng.integers(len(progs)))])
        return bucket_ids, programs

    def update(self, *_args, **_kw):
        return 0.0
