"""MiniGrid-Exec: the toy task family.

A task is ``(program, input grid) -> output grid``.  A program is an ordered
sequence of ``d`` ops drawn from a 6-op DSL; executing it on a ``G x G`` grid of
colours ``0..C-1`` gives the answer.

Difficulty is the vector ``z = (d, G, C)`` with ``d in 1..4``, ``G in {3,4,5}``,
``C in {2,3,4}`` -> 36 buckets.  Programs are enumerated exhaustively inside a
bucket, so the whole task family is finite and inspectable.

GROUND TRUTH POLICY
-------------------
``execute`` computes the true answer.  It is *evaluation-only* plus the one-off
seed phase.  Every caller in the training loop must go through
``solver.majority_vote`` instead.  Call sites that legitimately touch ground
truth are marked ``# GROUND TRUTH`` and funnel through
``assert_ground_truth_allowed`` so a leak is loud rather than silent.
"""

from __future__ import annotations

import itertools
from typing import Iterable

import numpy as np

# ---------------------------------------------------------------------------
# DSL
# ---------------------------------------------------------------------------

OP_NAMES = (
    "rot90",
    "flip_h",
    "shift_rows",
    "increment_colors",
    "swap_quadrants",
    "swap_colors01",
)
NUM_OPS = len(OP_NAMES)

DEPTHS = (1, 2, 3, 4)
GRID_SIZES = (3, 4, 5)
NUM_COLORS = (2, 3, 4)

MAX_D = max(DEPTHS)
MAX_G = max(GRID_SIZES)
MAX_C = max(NUM_COLORS)

PAD_OP = NUM_OPS  # program-slot token meaning "no op here"
PAD_CELL = MAX_C  # grid-cell token meaning "outside this grid"


def _rot90(g, C):
    return np.rot90(g, k=1)


def _flip_h(g, C):
    return g[:, ::-1]


def _shift_rows(g, C):
    return np.roll(g, 1, axis=0)


def _increment_colors(g, C):
    return (g + 1) % C


def _swap_quadrants(g, C):
    # For even G this is exactly a quadrant swap; for odd G it is the natural
    # cyclic generalisation, which keeps the op total on every grid size.
    G = g.shape[0]
    return np.roll(g, (G // 2, G // 2), axis=(0, 1))


def _swap_colors01(g, C):
    out = g.copy()
    out[g == 0] = 1
    out[g == 1] = 0
    return out


_OPS = (
    _rot90,
    _flip_h,
    _shift_rows,
    _increment_colors,
    _swap_quadrants,
    _swap_colors01,
)


def execute(program, grid, C):
    """Run ``program`` on ``grid``.  This is the ground-truth oracle."""
    out = np.ascontiguousarray(grid)
    for op in program:
        out = np.ascontiguousarray(_OPS[op](out, C))
    return out


# ---------------------------------------------------------------------------
# Ground-truth access guard
# ---------------------------------------------------------------------------

_GT_ALLOWED = {"seed", "eval", "oracle"}
"""Purposes permitted to read a true label.

``seed`` is the one-off pretraining phase, ``eval`` is measurement, and
``oracle`` is the deliberately-cheating ceiling baseline from the issue's M1
(same curriculum as ``rzero``, but trained on real labels).  ``oracle`` is listed
here rather than smuggled in under ``seed`` so that a labelled run is impossible
to start by accident and obvious in the code that requests it.  No claim about
learning without labels is ever made from an ``oracle`` run.
"""


def assert_ground_truth_allowed(purpose):
    """Gate every ground-truth read.

    Acceptance criterion 6.7: labels may be read only in the seed phase and in
    evaluation.  Any other purpose string is a bug in the training loop, so it
    raises rather than warns.
    """
    if purpose not in _GT_ALLOWED:
        raise AssertionError(
            "ground-truth label read with purpose=%r; only %s may read true "
            "labels (see issue #4 section 6)" % (purpose, sorted(_GT_ALLOWED))
        )


# ---------------------------------------------------------------------------
# Buckets
# ---------------------------------------------------------------------------

BUCKETS = tuple(
    (d, G, C) for d in DEPTHS for G in GRID_SIZES for C in NUM_COLORS
)
NUM_BUCKETS = len(BUCKETS)
BUCKET_INDEX = {z: i for i, z in enumerate(BUCKETS)}

SEED_BUCKET = (1, 3, 2)
SEED_BUCKET_ID = BUCKET_INDEX[SEED_BUCKET]
HARDEST_BUCKET = (4, 5, 4)
HARDEST_BUCKET_ID = BUCKET_INDEX[HARDEST_BUCKET]


def difficulty_score(bucket_id):
    """Scalar difficulty in [0, 1]: the mean of the three normalised axes.

    Used only for the "mean sampled difficulty rises monotonically" plot; the
    loop itself never sees it.  All three axes are weighted equally because the
    issue's difficulty vector gives no reason to prefer one.
    """
    d, G, C = BUCKETS[bucket_id]
    return ((d - 1) / 3.0 + (G - 3) / 2.0 + (C - 2) / 2.0) / 3.0


DIFFICULTY = np.array([difficulty_score(i) for i in range(NUM_BUCKETS)])


def programs_of_depth(d):
    return tuple(itertools.product(range(NUM_OPS), repeat=d))


_PROGRAM_CACHE = {d: programs_of_depth(d) for d in DEPTHS}


def bucket_programs(bucket_id):
    return _PROGRAM_CACHE[BUCKETS[bucket_id][0]]


# ---------------------------------------------------------------------------
# Format check: reject semantically-identity programs
# ---------------------------------------------------------------------------


def _probe_grids(G, C, n=24):
    """Fixed, deterministic probe grids used to test program semantics."""
    rng = np.random.default_rng(1000 * G + C)
    probes = rng.integers(0, C, size=(n, G, G))
    # Two structured probes: a constant grid and a positional gradient, which
    # between them catch ops that only permute cells and ops that only recolour.
    probes[0] = np.zeros((G, G), dtype=probes.dtype)
    probes[1] = np.arange(G * G).reshape(G, G) % C
    return probes


_IDENTITY_CACHE = {}


def is_identity(bucket_id, program):
    """True if ``program`` is a no-op on this grid size / palette.

    The toy analogue of R-Zero's format check.  Without it the Challenger can
    farm free uncertainty from degenerate tasks (``shift`` then ``unshift``),
    which is this domain's version of reward hacking.
    """
    key = (bucket_id, program)
    hit = _IDENTITY_CACHE.get(key)
    if hit is not None:
        return hit
    _, G, C = BUCKETS[bucket_id]
    probes = _probe_grids(G, C)
    result = True
    for probe in probes:
        # Not a ground-truth *label* read: this inspects a program's semantics,
        # never the answer to a task the Solver has been asked to solve.
        if not np.array_equal(execute(program, probe, C), probe):
            result = False
            break
    _IDENTITY_CACHE[key] = result
    return result


_IDENTITY_MASK_CACHE = {}


def identity_mask(bucket_id):
    """Boolean mask over ``bucket_programs(bucket_id)``: True where identity."""
    hit = _IDENTITY_MASK_CACHE.get(bucket_id)
    if hit is not None:
        return hit
    progs = bucket_programs(bucket_id)
    mask = np.array([is_identity(bucket_id, p) for p in progs], dtype=bool)
    _IDENTITY_MASK_CACHE[bucket_id] = mask
    return mask


# ---------------------------------------------------------------------------
# Encoding
# ---------------------------------------------------------------------------

OUTPUT_CELLS = MAX_G * MAX_G
OUTPUT_DIM = OUTPUT_CELLS * MAX_C

STATE_DIM = OUTPUT_CELLS * (MAX_C + 1)
SIZE_DIM = len(GRID_SIZES) + len(NUM_COLORS)
OP_DIM = NUM_OPS + 1
STEP_INPUT_DIM = STATE_DIM + OP_DIM + SIZE_DIM


def encode_program_steps(programs):
    """``(steps, active)``: ``(n, MAX_D)`` op tokens and an activity mask.

    Programs are right-padded and ``active[i, t]`` is 1.0 only while ``t`` is
    inside program ``i``.  Inactive steps carry the state through untouched
    rather than running the block on a pad token, so a depth-1 task is exactly
    one block application on the clean input grid, and a depth-4 task chains four
    of them.  Depth therefore controls how far prediction error compounds, which
    is what makes it a difficulty *slope* rather than a cliff.
    """
    programs = list(programs)
    n = len(programs)
    steps = np.full((n, MAX_D), PAD_OP, dtype=np.int64)
    active = np.zeros((n, MAX_D), dtype=np.float32)
    for i, prog in enumerate(programs):
        steps[i, : len(prog)] = prog
        active[i, : len(prog)] = 1.0
    return steps, active


def encode_state(grids, buckets):
    """Initial soft state ``(n, STATE_DIM)`` plus the ``(n, cells)`` inside mask.

    Channels ``0..MAX_C-1`` hold the colour distribution, channel ``MAX_C`` flags
    cells outside this task's grid.
    """
    grids = list(grids)
    buckets = list(buckets)
    n = len(grids)
    state = np.zeros((n, OUTPUT_CELLS, MAX_C + 1), dtype=np.float32)
    inside = np.zeros((n, OUTPUT_CELLS), dtype=np.float32)
    for i in range(n):
        _, G, _C = BUCKETS[buckets[i]]
        grid = grids[i]
        state[i, :, PAD_CELL] = 1.0
        for r in range(G):
            for c in range(G):
                cell = r * MAX_G + c
                state[i, cell, PAD_CELL] = 0.0
                state[i, cell, int(grid[r, c])] = 1.0
                inside[i, cell] = 1.0
    return state.reshape(n, STATE_DIM), inside


def encode_size_tags(buckets):
    """``(n, SIZE_DIM)`` one-hot tags for G and C."""
    buckets = list(buckets)
    tags = np.zeros((len(buckets), SIZE_DIM), dtype=np.float32)
    for i, bid in enumerate(buckets):
        _, G, C = BUCKETS[bid]
        tags[i, GRID_SIZES.index(G)] = 1.0
        tags[i, len(GRID_SIZES) + NUM_COLORS.index(C)] = 1.0
    return tags


def encode_targets(grids, buckets):
    """Return ``(labels, mask)`` over the flattened ``MAX_G x MAX_G`` frame.

    ``labels[i, cell]`` is the target colour; ``mask[i, cell]`` is 1.0 for cells
    inside this task's grid and 0.0 for padding, so loss and accuracy ignore
    cells that do not exist.
    """
    grids = list(grids)
    buckets = list(buckets)
    n = len(grids)
    labels = np.zeros((n, OUTPUT_CELLS), dtype=np.int64)
    mask = np.zeros((n, OUTPUT_CELLS), dtype=np.float32)
    for i in range(n):
        _, G, _C = BUCKETS[buckets[i]]
        grid = grids[i]
        for r in range(G):
            for c in range(G):
                labels[i, r * MAX_G + c] = int(grid[r, c])
                mask[i, r * MAX_G + c] = 1.0
    return labels, mask


def cell_mask_for(buckets):
    """``(n, cells)`` mask of which cells exist, without needing any grid."""
    buckets = list(buckets)
    mask = np.zeros((len(buckets), OUTPUT_CELLS), dtype=np.float32)
    for i, bid in enumerate(buckets):
        _, G, _C = BUCKETS[bid]
        for r in range(G):
            mask[i, r * MAX_G : r * MAX_G + G] = 1.0
    return mask


def color_mask(buckets):
    """``(n, MAX_C)`` mask of which colours exist in each task's palette."""
    buckets = list(buckets)
    m = np.zeros((len(buckets), MAX_C), dtype=np.float32)
    for i, bid in enumerate(buckets):
        _, _G, C = BUCKETS[bid]
        m[i, :C] = 1.0
    return m


def decode_grids(pred_cells, buckets):
    """Turn flat per-cell predictions back into ``G x G`` grids."""
    out = []
    for i, bid in enumerate(buckets):
        _, G, _C = BUCKETS[bid]
        g = np.zeros((G, G), dtype=np.int64)
        for r in range(G):
            for c in range(G):
                g[r, c] = pred_cells[i, r * MAX_G + c]
        out.append(g)
    return out


# ---------------------------------------------------------------------------
# Task sampling
# ---------------------------------------------------------------------------


class TaskBatch:
    """A batch of tasks. ``outputs`` is filled only for seed/eval batches."""

    __slots__ = ("bucket_ids", "programs", "inputs", "outputs")

    def __init__(self, bucket_ids, programs, inputs, outputs=None):
        self.bucket_ids = bucket_ids
        self.programs = programs
        self.inputs = inputs
        self.outputs = outputs

    def __len__(self):
        return len(self.programs)


def sample_inputs(bucket_ids, rng):
    grids = []
    for bid in bucket_ids:
        _, G, C = BUCKETS[bid]
        grids.append(rng.integers(0, C, size=(G, G)))
    return grids


def make_tasks(bucket_ids, programs, rng, with_labels=False, purpose=None):
    """Build a task batch.  ``with_labels=True`` requires a legal purpose."""
    inputs = sample_inputs(bucket_ids, rng)
    outputs = None
    if with_labels:
        assert_ground_truth_allowed(purpose or "")  # GROUND TRUTH
        outputs = [
            execute(programs[i], inputs[i], BUCKETS[bucket_ids[i]][2])
            for i in range(len(programs))
        ]
    return TaskBatch(bucket_ids, programs, inputs, outputs)


def sample_from_bucket(bucket_id, n, rng, exclude_identity=True):
    progs = bucket_programs(bucket_id)
    if exclude_identity:
        idx = np.flatnonzero(~identity_mask(bucket_id))
    else:
        idx = np.arange(len(progs))
    choice = rng.choice(idx, size=n, replace=True)
    return [progs[i] for i in choice]


def held_out_set(n_per_bucket=48, seed=20260824):
    """Fixed evaluation set, one batch per bucket.

    Generated once from a fixed seed and never touched by the Challenger.
    """
    rng = np.random.default_rng(seed)
    batches = []
    for bid in range(NUM_BUCKETS):
        programs = sample_from_bucket(bid, n_per_bucket, rng)
        bucket_ids = [bid] * n_per_bucket
        # GROUND TRUTH: evaluation only.
        batches.append(
            make_tasks(bucket_ids, programs, rng, with_labels=True, purpose="eval")
        )
    return batches
