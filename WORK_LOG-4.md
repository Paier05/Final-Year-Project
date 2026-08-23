# Work Log — Issue #4: Build a minimal, self-contained demo of R-Zero (Challenger↔Solver co-evolution) on a toy domain

**Issue:** https://github.com/Paier05/Final-Year-Project/issues/4
**Branch:** `experiment/4-mini-r-zero-toy-demo`
**Started:** 2026-08-24

## Understanding the issue

R-Zero (Huang et al., arXiv:2508.05004) claims a model can improve on a task
family using **only tasks it invents for itself**, with no external labels. Two
copies of one base model alternate roles: a **Challenger** proposes questions,
rewarded for landing at the *frontier* of a frozen **Solver**'s competence
(majority-vote agreement `p̂ ≈ 0.5`), and the Solver then trains on the
majority-vote **pseudo-labels** of the questions that survived a difficulty
filter.

The ask here is **not** to reproduce R-Zero's numbers. It is to build the
smallest thing that exhibits the *mechanism*, on a toy domain (`MiniGrid-Exec`:
grid-transformation programs), CPU-only, under 30 minutes, and — just as
importantly — to characterise **when the loop fails**. The issue explicitly
lists four paper findings the experiment should try to see for itself
(trained > untrained Challenger; ablations hurt; pseudo-label accuracy decays;
eventual collapse) and asks the README to state honestly which reproduced.

The load-bearing constraint is the one in §6: **zero ground-truth labels may be
read anywhere except the seed phase and evaluation.** Every ground-truth call
site needs an assertion or comment. If that leaks, the experiment proves
nothing.

### Assumptions I'm making (issue is detailed, but a few gaps)

1. The issue's file tree lists `run.py` as the CLI, while §1 says a reader runs
   `python demo.py`. I read these as the same requirement stated twice and will
   make `run.py` the real CLI, with `demo.py` a thin wrapper that reproduces the
   three plots end-to-end. That satisfies both sentences.
2. The issue references `claude/self-evolution-teacher-student-training.md` for
   context. That path does not exist in this repo; the closest artefact is
   `Documentation_Generated/Self-Evolution_Teacher-Student_Training_ARC3.pdf`.
   Treating this as context-only — nothing in the milestones depends on it.
3. `main` currently has no Python code, no test suite, and no dependency
   manifest. I'll add a `requirements.txt` scoped to the experiment folder
   rather than introducing repo-wide tooling.
4. "Numpy-only if possible" (§7) — I'll take that literally for the models
   (hand-rolled MLP, Adam, REINFORCE) and use matplotlib only in `plots.py`.

## Plan

1. **Setup** — branch, work log, virtualenv with numpy + matplotlib (system
   Python 3.14 has neither).
2. **`domain.py`** — the 6-op DSL, difficulty buckets `z = (d, G, C)`, program
   enumeration within a bucket, execution, one-hot encoding, identity-program
   detection (the toy's format check), and a fixed held-out test set.
3. **`solver.py`** — numpy MLP, hand-rolled Adam, and crucially **MC-dropout**
   sampling of `m = 10` whole-grid answers plus majority vote. The issue warns
   that per-cell temperature sampling degenerates into self-distillation; I need
   genuinely different *functions*, not different samples from one function.
4. **M0 sanity gate** — seed on the easiest bucket only, then check the three
   gate conditions. **This is the decision point for the whole issue.** The
   issue records a prior prototype that stalled here with a depth-only
   difficulty axis. If pseudo-label accuracy at the frontier is ~0, I re-tune
   the domain; if a day of tuning can't fix it, I take the §8 escape hatch to
   Track B and say so.
5. **`challenger.py`** — categorical policy over `(bucket, program)`,
   `r_uncertainty`, repetition penalty via cheap `(depth, first op)` clustering,
   format check → 0, group-normalised REINFORCE (GRPO-lite).
6. **`loop.py` / `run.py`** — seed → [challenger update → dataset build →
   solver train] × iters, with `--mode` and `--ablate` switches and per-iteration
   JSON logging.
7. **M1 + M2** — baselines (`uniform`, `hardest`, `oracle`) then the real loop,
   ≥3 seeds, inside the 30-minute budget.
8. **M3** — `--no-rep-penalty`, `--no-filter`, `--single-model`, and a 15+
   iteration run hunting for the collapse curve.
9. **`plots.py`** — the three required plots, regenerable from JSON alone.
10. **README + PR** — including an honest accounting of what did *not*
    reproduce.

I am deliberately doing steps 2–4 before writing any of the R-Zero machinery.
M0 is a gate, and building the Challenger before knowing the frontier exists
would be building on sand.

## Progress log

### 2026-08-24 — Branch created, issue read, plan fixed

- What I did: Ran the step-0 preconditions (remote, `gh auth`, clean tree, not a
  worktree, `main` up to date), read issue #4 in full, created branch
  `experiment/4-mini-r-zero-toy-demo`, seeded this log.
- Why: Workflow step 3 — get the understanding and plan on record *before*
  writing code, so the plan can be judged against what actually happened.
- Result / what I found: The issue has no comments, so no post-hoc scope
  changes to account for. `main` is documentation-only — this will be the first
  code in the repo. System Python is 3.14.5 with neither numpy nor matplotlib
  installed, so an environment step is needed before anything can run.
- Next step: Set up the venv, then write `domain.py`.

### 2026-08-24 — M0 FAILS on the spec-faithful build; two distinct causes found

- What I did: Built `domain.py` and `solver.py` exactly to the issue's spec
  (flat MLP over one-hot `[program tokens || input grid]`, MC-dropout sampling,
  majority vote) and ran the M0 gate. Then ran a diagnostic sweep
  (`_diag_seed.py`) over three different seed sets to find out *why* it failed.
- Why: M0 is the gate for the entire issue and the issue warns a prior prototype
  died here. I wanted the failure characterised, not patched over.
- Result / what I found: **M0 fails.** Seeding on the easiest bucket alone gives
  100% on `(1,3,2)` and 0-17% on all 35 other buckets. `gate_frontier_ge_25`
  fails. The diagnostic sweep then separated two independent causes:

  **Cause 1 — the majority vote never beats greedy.** Across every frontier
  bucket in every seed set, `vote <= greedy`:

  | bucket | vote | single sample | greedy |
  |---|---|---|---|
  | (3,3,2) | 14.6% | 11.2% | **16.7%** |
  | (3,4,2) | 16.7% | 7.9% | **18.8%** |
  | (4,3,2) | 4.2% | 2.1% | **10.4%** |

  The vote does beat a *single* dropout sample (so the issue's stated M0 check
  passes on its own terms), but that is the wrong comparison: training on
  pseudo-labels that are no better than the Solver's own greedy output is
  self-distillation, and no information enters the loop. This is the same
  degeneracy the issue warns about for per-cell temperature sampling — I avoided
  the stated form of it and hit it in a different form. MC-dropout on a small
  MLP perturbs a memorised lookup; it does not produce *independent attempts*
  the way an LLM's sampled reasoning chains do, so the ensemble can at best
  recover greedy.

  **Cause 2 — there is no graded frontier, because the MLP cannot compose.**
  Seeded on all nine `d=1` buckets, depth-2 accuracy is 0.0-4.2% everywhere. A
  flat MLP over one-hot program slots has simply never seen slot 2 occupied; its
  weights there are still at initialisation. The `(d,G,C)` axis is finer-grained
  than the depth-only axis that killed the earlier prototype, but it does not
  help: the jump that matters is still depth, and it is a cliff, not a slope.
  Seeding on `d<=2` (18 buckets) just moves the cliff to `d=3` and *degrades*
  `d=1` (G5C4 fell to 10.4%) because capacity is spread too thin.

- Next step: These need different fixes, so I am treating them separately.
  Cause 2 first, since Cause 1 cannot even be measured properly without a graded
  frontier to measure it on. Plan: replace the flat MLP with a **step-wise
  Solver** that applies one shared, op-conditioned block per program step,
  feeding its own soft prediction forward as the next step's input. Depth then
  becomes a *chain* whose errors compound, which is both the natural analogue of
  a reasoning chain and the thing that produces a graded frontier instead of a
  cliff. If that does not also fix Cause 1, I will add an independently
  initialised committee as the source of genuinely different functions.

## Open questions / risks

- **M0 is a real risk, not a formality.** The issue documents a previous
  prototype dying exactly there. A 36-bucket `(d, G, C)` axis is finer-grained
  than depth-only, but "finer-grained" is not the same as "has a bucket sitting
  near `p̂ ≈ 0.5`". I will not know until the seed phase runs.
- **MC-dropout may not give genuine functional diversity** at ~0.5M params on a
  domain this deterministic. If dropout samples collapse to the same grid, `p̂`
  is 1.0 everywhere, the uncertainty reward is flat, and the Challenger has no
  signal. Fallback would be weight noise; if neither works, that is itself a
  finding worth reporting rather than papering over.
- **Exact-match on a whole grid is a brutal metric** — with `G=5, C=4` a random
  answer is right with probability `4^-25`. Chance-level is effectively zero, so
  "better than chance" (M0) is a weak bar; I should compare pseudo-label
  accuracy against the *single-sample* accuracy instead, which the issue also
  asks for.
- **The 30-minute CPU budget is shared** across seeds and modes. If the full
  matrix (4 modes × 3 seeds + 3 ablations + a 15-iteration run) doesn't fit, I
  will scope the headline `--mode rzero --seeds 3` command to the budget and let
  the wider matrix take longer, flagging that split in the README rather than
  quietly shrinking the experiment.
- Whether the paper's collapse behaviour can appear at all in a domain with a
  finite, enumerable task space is unclear — the toy may run out of frontier
  before it runs out of pseudo-label quality.

## Summary (fill in at the end)

<pending>
