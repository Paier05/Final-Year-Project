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

### 2026-08-24 — M0 PASSES after two fixes; both dead ends kept on the record

- What I did: Fixed the two causes separately, re-ran the gate, and added
  `test_experiment.py` (43 checks, including a finite-difference check of the
  hand-written BPTT).
- Why: The two failures had different causes and fixing them together would have
  made it impossible to say which fix did what.

**Fix for Cause 2 (no graded frontier) — step-wise Solver.** Replaced the flat
MLP with one shared op-conditioned block applied once per program step, feeding
its own soft prediction forward:

    state_0 = input grid;  state_t = softmax(block(state_{t-1}, op_t));  answer = argmax(state_d)

Depth-1 competence now transfers to depth 4 because the weights are shared, but
imperfectly, because each step consumes the previous step's *predicted* grid.
Errors compound with depth, which is exactly the slope the method needs — and it
is a closer analogue of a reasoning chain than the flat MLP was, since an early
mistake corrupts everything downstream. This is a deviation from the issue's
stated architecture and it is flagged in the README.

Two bugs found on the way, both worth recording:

1. *Left-padding deadlocked training.* My first version ran a fixed 4 steps with
   pad tokens first, so even a depth-1 task had to chain through 4 blocks. Loss
   sat at exactly `ln(2) = 0.6931` for 2000 steps — the model could not
   bootstrap, because there was no gradient path to "pad = identity". Fixed by
   right-padding with an explicit *activity mask*: steps past a program's depth
   carry the state through untouched and never run the block. A depth-1 task is
   now exactly one block application on a clean input.
2. *The gradient check was wrong, not the gradient.* The finite-difference check
   reported 3-13% error and I spent a while hunting a BPTT bug that did not
   exist. `_to_state` hard-coded `dtype=np.float32`, so the "float64" check was
   silently running the chain in float32 and comparing analytic gradients
   against pure rounding noise. With the dtype following its input, worst
   relative error is **1.1e-8 at depth 1 and 2.8e-7 at depth 4**. Lesson kept in
   the test file as a comment: verify the instrument before believing it about
   the thing being measured.

**Fix for Cause 1 (vote never beats greedy) — committee instead of MC-dropout.**
MC-dropout at rate 0.15 was actively catastrophic in a chained model: noise
compounds across steps, all 10 samples land somewhere different, `p_hat` pins to
0.10, and the vote scored *0-19%* where greedy scored *72-94%*. Lowering the rate
only trades one degeneracy for the other (all samples identical, `p_hat = 1`, no
signal). Replaced with a **committee of 10 independently initialised Solvers**,
each contributing its own greedy answer, which is the strongest reading of the
issue's own phrase "m genuinely different functions". MC-dropout is kept as an
optional top-up but defaults to off.

**M0 gate result** (seed = all 9 depth-1 buckets, 1200 steps, committee of 10,
1.27M params total):

| gate | result |
|---|---|
| seed bucket >= 90% | **PASS** — (1,3,2) at 99.0% |
| frontier >= 25% on a harder bucket | **PASS** — 14 unseeded buckets in the 5-95% band |
| hardest bucket near 0% | **PASS** — (4,5,4) at 0.0% |
| vote beats a single sample | **PASS** |
| vote beats greedy *(my addition)* | **PASS** |

Frontier pseudo-label quality, the numbers that matter:

| bucket | vote | single sample | greedy | mean p_hat |
|---|---|---|---|---|
| (2,3,4) | **58.3%** | 26.7% | 6.2% | 0.33 |
| (2,4,3) | **56.2%** | 24.8% | 25.0% | 0.30 |
| (3,3,3) | **75.0%** | 52.3% | 35.4% | 0.57 |
| (4,3,3) | **83.3%** | 52.9% | 33.3% | 0.55 |

- Result / what I found: I added `gate_vote_beats_greedy` as a fifth gate. The
  issue only asks that the vote beat a *single sample*, but that check passed
  even in the completely broken MC-dropout configuration where the vote was four
  times worse than greedy. Beating greedy is the condition that actually
  determines whether information enters the loop, so it is the one I gated on.
- Next step: The seed phase is now cached to disk (it depends only on
  `(seed, steps, committee)`, not on the mode), which both saves most of the wall
  clock and makes every mode start from byte-identical weights — so mode
  comparisons are paired. Run M1 baselines and M2.

### 2026-08-24 — The loop initially made the Solver *worse*; cause was the step size

- What I did: Wired up `loop.py` / `run.py` and ran `rzero` for the first time.
  Accuracy went **down**, 39.0% -> 34.3% over 6 iterations. Swept the Solver's
  co-evolution learning rate and epoch count to find out why.
- Why: A drop is the expected symptom of *two* very different problems — junk
  pseudo-labels, or catastrophic forgetting — and they need opposite fixes, so
  guessing would have been a coin flip. The logged `pseudo_label_accuracy` was
  75-80%, which already argued against junk labels, so forgetting was the
  hypothesis to test.
- Result / what I found: It was forgetting, and the sweep is unambiguous:

  | Solver LR | epochs | accuracy over 6 iters | seeded buckets | unseeded |
  |---|---|---|---|---|
  | 2e-3 (= seed LR) | 4 | 39.0 -> 36.7 | **-4.1pp** | -1.6pp |
  | 5e-4 | 2 | 39.0 -> 44.0 | +3.5pp | +5.5pp |
  | 2e-4 | 2 | 39.0 -> 45.3 | +5.4pp | +6.6pp |
  | 1e-4 | 4 | 39.0 -> **46.3** | +6.3pp | +7.6pp |

  The mechanism is a direct consequence of the difficulty filter. Keeping only
  `|p_hat - 1/2| <= 0.25` means the training set is *entirely* frontier tasks —
  nothing in it rehearses the easy buckets. At the seed learning rate the Solver
  overwrites what it already knew faster than it learns anything new, and the
  loss on the seeded buckets shows it (-4.1pp). At 1e-4 both seeded and unseeded
  buckets improve. This also matches the paper structurally: R-Zero's phase 3 is
  a light RL touch on a pretrained model, not a retrain, and I had been running
  the equivalent of a retrain.

  With `solver_lr=1e-4`, a 15-iteration `rzero` run gives 39.0% -> 47.0% peak at
  iteration 12, then flattens to 46.6%. Pseudo-label accuracy decays 75.6% ->
  59.8% across those iterations and kept-fraction climbs 25% -> 46%, both of
  which are the paper's qualitative findings.

- Next step: Run the full matrix (4 modes + 3 ablations, 3 seeds, 15 iterations)
  and write the plots.

### 2026-08-24 — The a-priori difficulty axis is a bad ruler; escalation needed a second one

- What I did: Ran the first full `rzero` matrix and found the "mean sampled
  difficulty rises monotonically" check sitting flat at ~0.50 — exactly the
  uniform-policy reference. Before concluding "no escalation", I checked whether
  the *ruler* was right, and it was not.
- Why: The same instinct that saved the gradient check earlier. A flat curve on a
  measured axis has two explanations — the thing didn't move, or the axis doesn't
  measure the thing — and they have opposite implications for the whole issue.
- Result / what I found: `difficulty_score` averages the three normalised axes
  `(d, G, C)` with equal weight, which is not how hard this domain actually is.
  The seeded Solver scores **0.8% on `(1,5,4)` but 95.2% on `(4,3,2)`** — the
  a-priori axis orders those two backwards, so a Challenger climbing real
  difficulty can leave the a-priori mean untouched.

  I added an **empirical difficulty axis**: `1 - (seeded Solver's per-bucket
  accuracy)`, computed once at iteration 0 from the post-seed evaluation and then
  frozen. It matters that it is frozen — a difficulty measure that tracked the
  live Solver would make "the Challenger moved to harder tasks" unfalsifiable,
  because the target would move with it. Both axes are logged, and `plots.py`
  shows both.

  | axis | iter 1 -> 15 | uniform reference |
  |---|---|---|
  | a-priori `(d,G,C)` | 0.496 -> 0.525 | 0.500 |
  | empirical | **0.609 -> 0.781**, strictly monotone | 0.610 |

  On the empirical axis the escalation is unambiguous and monotone across all 15
  iterations, and the policy concentrates to 1.47 nats of entropy (uniform: 3.58)
  on `(3,3,4)` and `(2,3,4)` — mid-depth, small-grid, many-colour. That is the
  frontier, and the Challenger found it without ever being told where it was.

  Also raised the Challenger step size to `lr=2.0` (from the policy default 0.5)
  after a sweep; at 0.5 the policy barely moved off uniform within 15 iterations.
- Next step: Run the full matrix and write it up.

### 2026-08-24 — Full matrix: the loop works, but the Challenger is not why

- What I did: Ran 4 modes + 3 ablations x 3 seeds x 15 iterations (23 min total),
  regenerated the three figures, and wrote `experiments/mini_r_zero/README.md`.
- Why: M1/M2/M3 in one pass, since the cached seed phase makes every mode start
  from byte-identical weights and the comparisons are therefore paired.
- Result / what I found: **The headline reproduces: 38.7% -> 46.5%, +7.8pp with
  no labels after the seed phase**, std 0.1pp across seeds. The `oracle` ceiling
  is 48.9%, so pseudo-label noise costs only 2.4pp of a 10.2pp achievable gain.

  Three things I did not expect, all of which changed what the README claims:

  1. **`uniform` ties `rzero` (46.4% vs 46.5%).** Paper finding 1 does not
     reproduce. There is a real early advantage (+0.7pp at iterations 1 and 4) —
     the trained Challenger arrives sooner but not higher. My reading: with 36
     buckets over 13,986 enumerable tasks, uniform sampling hits the frontier
     often by accident and the difficulty filter discards the rest, so **the
     filter, not the Challenger, is doing the curriculum work here.** That is a
     property of a small task space, and worth saying plainly rather than
     burying.

  2. **`hardest` never trains at all.** Its curve is flat to four significant
     figures, and I nearly wrote it up as "trains and fails". It does not train:
     every task in `(4,5,4)` gets `p_hat = 0.100` *exactly* — all 10 committee
     members disagree — so `|p_hat - 0.5| = 0.4` fails the filter and **zero
     tasks are kept in all 15 iterations**. A cleaner result than a degraded
     curve would have been: the filter refuses to manufacture labels past the
     frontier.

  3. **`--single-model` is a no-op by construction, not a null result.** Phases 1
     and 2 both finish before phase 3 trains the Solver, so `sol.clone()` and the
     live `sol` hold identical weights the whole time the Challenger probes. The
     +/-0.1pp spread is `clone()` shifting the RNG stream, nothing more. Reported
     as an implementation fact, because a 0.0pp ablation delta otherwise invites
     the conclusion that freezing does not matter.

  The ablation that *did* bite is invisible in accuracy: `--no-rep-penalty`
  collapses the Challenger to **98.7% of its mass on one bucket** (entropy 0.10
  vs 1.47 nats) while costing only 0.1pp of peak accuracy — because one bucket
  still holds hundreds of programs, so a collapsed bucket distribution is not a
  collapsed task distribution. `--no-filter` costs 26pp of pseudo-label accuracy
  at iteration 1 (80.0% -> 53.5%) for 0.3pp of peak accuracy.

  Pseudo-label decay reproduces clearly: **80.0% -> 36.3%** over 15 iterations,
  kept fraction 30% -> 65%. Collapse only partially: peak at iteration 9, then a
  sag to 46.1%. The Solver losing 0.4pp while its labels lose 44pp suggests the
  wrong labels concentrate on tasks it cannot do anyway, so they act as noise
  rather than poison.
- Next step: Commit, push, open the PR.

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

## Summary

Built a numpy-only, CPU-only demo of the R-Zero Challenger/Solver co-evolution
loop on `MiniGrid-Exec`, a 36-bucket toy domain of grid-transformation programs.
**The central claim reproduces: held-out accuracy rises 38.7% -> 46.5% (+7.8pp,
n=3, std 0.1pp) with no ground-truth label read anywhere outside the seed phase
and evaluation** — a constraint enforced at runtime by a guard on every
ground-truth call site, and by a test that instruments a real iteration and
asserts no other purpose is ever requested.

Getting there took two deviations from the issue's stated architecture, both
forced by measured failures rather than by preference. A flat MLP gave a
difficulty *cliff* instead of a slope (depth-2 accuracy 0-4% everywhere), so the
Solver became a shared op-conditioned block applied once per program step,
feeding its own prediction forward — which makes errors compound with depth and
produces the graded frontier the method needs. MC-dropout then gave votes four
times *worse* than greedy in that chained model, so the `m` samples became a
committee of 10 independently initialised Solvers. M0 failed before both fixes
and passed after; both are flagged in the README.

The honest accounting of the paper's four findings: pseudo-label decay reproduces
clearly (80.0% -> 36.3%), collapse partially (peak at iteration 9, then a sag,
not a collapse), the ablations partially (their *mechanisms* behave exactly as
predicted — the repetition penalty is the only thing preventing a 98.7%
single-bucket collapse — but each costs under 0.3pp of accuracy), and **the
trained Challenger does not beat a uniform curriculum** (46.5% vs 46.4%). The
Challenger is nonetheless demonstrably doing its job: on an empirical difficulty
axis it escalates monotonically, 0.609 -> 0.781 against a uniform reference of
0.610, concentrating on exactly the frontier buckets. What this toy shows is that
**in a small, enumerable task space the difficulty filter carries the curriculum
and the trained Challenger is redundant.** A domain where the frontier is a
vanishing fraction of the task space is where the Challenger should start to pay,
and that is the natural follow-up.

Two debugging lessons worth keeping. A finite-difference check that disagreed
with the analytic gradient turned out to have a `float32` hard-code in the
*checker*, not a bug in the BPTT — verify the instrument before believing it
about the thing being measured. And a flat curriculum-difficulty curve turned out
to be a bad ruler rather than a static Challenger — the same mistake in a
different costume.
