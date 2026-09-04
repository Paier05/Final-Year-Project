# Synthesis

Cross-topic analysis over the 89 verified entries in `topic1-harness.md` (31),
`topic2-teacher-student.md` (27) and `topic3-frozen-weights.md` (31), plus the 24 one-line entries in
`adjacent.md`. Handles in `[brackets]` refer to entries in those files.

**Read §3 and §4 first if you read nothing else.** The corpus does not say what the internal briefing
notes assume it says, and two of the three topics have to be re-aimed as a result.

---

## 1. Taxonomy

The full two-axis table — *what is optimised* (weights / context / scaffold code / task distribution /
memory / nothing persistent) × *where the learning signal comes from* (executable verifier /
environment reward / learned reward model / human labels / self-consistency / none) — is in
`taxonomy.md`, with every entry placed and every placement convention stated.

Summary of what the table shows:

- **Three cells hold most of the corpus.** `scaffold code × executable verifier` (14),
  `weights × environment reward` (12), and `task distribution × environment reward` (11). The
  second and third are the same papers seen from the student's and the teacher's side.
- **Scaffold self-modification only ever happens against a mechanical verifier.** Every other column
  in that row is empty.
- **Task generation against a mechanical verifier only ever produces code or maths.** Nobody
  generates interactive environments checked by execution.
- **Topic 1 ∩ Topic 2 is empty.** Nothing co-evolves the harness and the task distribution.
- **Topic 2 ∩ Topic 3 has one weak occupant**, [Voyager], whose curriculum is prompted rather than
  optimised, in a language-saturated environment, scored on items rather than efficiency.
- **Efficiency is almost never the optimisation target.** One entry ([MetaEvolve]) trains on a
  correctness-plus-efficiency fitness; four more report efficiency as a secondary outcome.

One deviation from the issue's specification, stated for the record: a sixth row,
**`nothing persistent`**, was added. Most of Topic 3 §1 changes nothing at all between one problem
and the next, and filing best-of-N under "optimises the context" would erase precisely the
distinction that §3.1 below turns on.

---

## 2. Lineages

Five threads, each ending at a 2026 paper that the FYP has to engage with.

### L1 — Provable self-rewriting → empirical self-modification → population selection

```
Gödel machine (2003)  ── proof as the acceptance rule; does not scale
   ├─ ADAS / Meta Agent Search (2024)  ── a meta agent writes agents; archive of discoveries
   └─ Gödel Agent (ACL 2025)  ── the agent rewrites its own running logic, objective-only guidance
       ├─ SICA (2025)  ── single lineage, minimal: agent edits its own source
       ├─ DGM (2025)   ── archive + benchmark validation replaces proof     SWE-bench 20.0 → 50.0
       │    └─ Live-SWE-agent (2025)  ── evolve at runtime, no offline training phase   77.4 SWE-bench Verified
       └─ DarwinX (2026)  ── population selection, frozen model, preserve-and-extend admission
```
The whole thread is one long answer to the Gödel machine's unanswerable question: *what evidence
licenses a self-modification?* The answers get progressively cheaper — proof, then benchmark
validation, then non-regression on covered tasks — and every step keeps an explicit acceptance rule.

### L2 — Asymmetric self-play → unsupervised environment design → learnability rewards

```
Asymmetric self-play (2017)   Teacher-Student Curriculum Learning (2017)   GoalGAN (2017)
        │                                    │                                 │
        └──────────────┬─────────────────────┴─────────────────────────────────┘
                       ↓
   POET (2019) → Enhanced POET (2020)          PAIRED (2020) ── regret as the objective
        environments as a population                 │
                       │                             ├─ PLR (2020) ── curate, don't generate
                       │                             ├─ PLR⊥ (2021) ── PLR and PAIRED unified as DCD
                       │                             ├─ ACCEL (2022) ── edit high-regret levels
                       │                             └─ TRACED (2026) ── + transition-prediction error
                       └─ OMNI (2023) → OMNI-EPIC (2024) ── FM judges "interesting"; environments as code
```
Two branches with different failure modes: the POET/OMNI branch generates richly but cannot say when
it is stalling; the PAIRED branch has a principled objective (regret) but struggles to *find* levels.
[ACCEL] is the reconciliation, and it is the branch point most relevant here.

### L3 — Self-generated data → zero-data self-play → grounded teachers

```
STaR (2022)  ── keep self-generated rationales that verify
   └─ Absolute Zero (2025)  ── one model proposes and solves; code executor verifies both
        ├─ R-Zero (2025)  ── separate Challenger and Solver; majority vote as verifier
        │    ├─ R-Diverse (2026)     ── gains are non-sustained: Diversity Illusion
        │    └─ VocabDropout (2026)  ── proposer collapse; constrain the action space
        ├─ SQLM (2025)  ── topic-only input; proposer writes unit tests
        ├─ GASP (2026)  ── anchor the curriculum to real goalpost problems
        └─ SOAR-Teacher (2026)  ── teacher rewarded by the student's *measured* improvement
             └─ finding: grounded rewards beat intrinsic learnability, and avoid collapse
```
Note the shape: 2025 proposes intrinsic learnability rewards; 2026 reports that they collapse and
replaces them with grounded ones. The internal briefing note stops at the 2025 layer.

### L4 — Self-consistency → verifier-guided search → the elicitation ceiling

```
Self-consistency (2022) ── vote over sampled paths
   ├─ Tree of Thoughts (2023) ── search, self-evaluate, backtrack        Game of 24: 4% → 74%
   ├─ Let's Verify (2023) ── process > outcome supervision                MATH subset 78%
   ├─ Large Language Monkeys (2024) ── coverage scales log-linearly with samples...
   │     └─ ...but selection plateaus, and Limits of Resampling (2024) proves an accuracy ceiling
   │        whenever the verifier has a non-zero false-positive rate
   └─ Snell et al. (2024) ── compute-optimal allocation; 14x larger model beaten
         └─ conditioned on non-trivial base success rates — a boundary, not a general claim
              └─ RLVR-Elicitation (NeurIPS 2025) ── base model is the upper bound at large k
                   └─ Reasoning with Sampling (2025) ── a training-free sampler matches RL
```
This thread is what turns "test-time compute improves capability" into a question with a measurable
answer, and the answer is mostly *no*: it improves selection.

### L5 — ARC-AGI: static solvers → interactive world-model agents (the newest and fastest-moving)

```
On the Measure of Intelligence (2019) → ARC-AGI-2 (2025) → ARC-AGI-3 (2026)
   static solvers:  CompressARC (76K params, 20%)   TRM (7M params, 45% ARC-AGI-1)
                    TTT-FewShot (53.0% / 61.9% ensembled)   SOAR-ProgSynth (52% public test)
                    ARC Prize 2025 report: refinement loops; 24% private ARC-AGI-2
   interactive (all frozen weights, all 2026):
        Graph-based exploration → ExecWM (RHAE 58.12, 15/25 games)
                                   └─ WMAblation ── "public-set saturation only"
        WorkspaceOpt / DreamTeam (36% → 38.4%, 31% fewer actions)
        Twin (7.8% bare → 61.1% generic harness → 93.3% world model)
        Tycho (100.00 RHAE, all 183 levels, 61% fewer actions than human baselines)
   running alongside: BenchmarkValidity ── all 25 public games reachable by non-intelligent
                      strategies; a library-level null-coordinate bug bypasses 18 in one step
```

---

## 3. Disagreements

### 3.1 Does test-time compute create capability, or only elicit it?

**The elicitation case is currently much stronger, and it is the better-evidenced side.**
[RLVR-Elicitation] (NeurIPS 2025 Oral) probes RLVR-trained models with pass@k at large k and finds
base models score *higher* at large k; coverage and perplexity analyses put the trained model's
reasoning inside the base model's support. [ReasoningWithSampling] closes the argument from the other
direction: a training-free MCMC-style sampler using only the base model's likelihoods nearly matches
RL post-training on MATH500, HumanEval and GPQA. [MATH-Beyond] supplies the instrument, showing base
models already solve most of MATH-500 and AIME-2024 at pass@1024, so those benchmarks cannot
distinguish the hypotheses at all.

**The acquisition case has three genuine exhibits, and they are not symmetrical replies.**
[AlgorithmDistillation] deploys a network that improves in-context on unseen tasks *faster than the
algorithm that generated its training data* — improvement the static weights do not exhibit.
[AlphaEvolve] found a 48-multiplication algorithm for 4×4 complex matrix multiplication, the first
improvement over Strassen in that setting in 56 years, which is hard to describe as eliciting
something the proposer already knew. And [Twin] takes one frozen model from 7.8% to 93.3% on
ARC-AGI-3.

**The disagreement is partly definitional, and the corpus contains the resolution.** [ICLasGD] shows
in-context adaptation is literally gradient-descent-like optimisation running in the forward pass, so
"no weight update" does not mean "no learning" — it means the optimiser moved. Once that is granted,
the honest formulation is a **model/system distinction**: [Twin]'s *model* gained nothing (b), while
[Twin]'s *system* does things no sampling budget over the bare model achieves (a). This survey adopts
that distinction explicitly, which is why the gain-type line in `topic3-frozen-weights.md` marks
[Twin] and [Tycho] as "(a) new capability **at the system level**" and says plainly that the model is
unchanged.

**What would settle it for ARC-AGI-3:** run the bare agent for a very large action budget across many
episodes and check whether the harness ever clears a game the bare agent never clears at any budget.
That is [RLVR-Elicitation]'s pass@k test transposed, and **nobody in this corpus has run it on an
interactive benchmark.** It is cheap, decisive, and available to this project.

### 3.2 Do learnability rewards avoid diversity collapse, or merely delay it?

**The 2025 position** — [AbsoluteZero], [R-Zero], [SQLM] — is that rewarding the proposer for tasks of
intermediate difficulty keeps the curriculum informative, and their results support it over the
horizons they report.

**The 2026 position is that this is delay, not avoidance**, and it is argued by three independent
groups. [R-Diverse] identifies *Diversity Illusion* in R-Zero-style loops: early gains degrade as
self-play continues, because batch-local diversity enforcement produces cross-iteration mode cycling
and because questions vary on the surface while exercising identical skills. [VocabDropout],
independently, reports that the proposer "converges to a narrow distribution of problems that satisfy
the reward function" and that the collapsed curriculum stalls the loop. [LearnableInfoGain] (ICML
2026 position track) generalises both: a loop that synthesises more data without increasing
*learnable information* will plateau, whatever the reward is called.

**[SOAR-Teacher] is the sharpest disagreement, because it is a like-for-like comparison**: grounded
rewards (the student's measured improvement on held-out hard problems) outperform intrinsic
learnability rewards *and* "reliably avoid the typical instability and diversity collapse modes".
That is a direct empirical claim that intrinsic learnability is the cause, not merely the context.

**Consequence for the FYP:** the internal briefing's recipe — Absolute-Zero-style intrinsic
learnability — is the version the 2026 literature has moved away from. Two fixes are available and
compatible: ground the teacher's reward in measured student improvement ([SOAR-Teacher]), and factor
the proposer's reward into validity × difficulty with an *independent* verifier ([VHG]).
[VocabDropout] also offers an argument that this project is structurally safer than the LLM work it
borrows from: language self-play lacks the action-space constraint that game rules provide in
classical self-play, whereas an ARC-AGI-3 environment editor has a small, structured action space by
construction.

### 3.3 How much of reported agent progress is harness rather than model?

**Evidence that the harness is doing real work.** [HarnessEvo] fixes the model and varies 35
sequential releases of one CLI, tracing measured quality shifts — in both directions — to individual
pull requests. [Twin] reports the cleanest decomposition available: the same frozen model scores 7.8%
played directly, 61.1% under an off-the-shelf harness, 93.3% under its world-model harness.
[DarwinX] adds ~17 points on average across four benchmarks with the model frozen. [RAH — adjacent]
improves a coding-agent baseline from 71.75% to 81.36% on a fixed GPT-5 backbone.

**Evidence that the harness is smaller than it looks.** [WMAblation] is decisive and comes from the
author of the system being ablated: across four harness variants, two model versions and two
reasoning-effort levels on ARC-AGI-3, gains from **model capability and reasoning effort often exceed
the differences between harness variants** — and requiring an executable world model is *not*
universally beneficial, with a plain textual variant beating the flexible executable variant in both
conditions on one model. [Agentless] makes the same point in software engineering: a three-phase
non-agentic pipeline beat every open-source agent on SWE-bench Lite at $0.70 per issue.

**These are less contradictory than they appear.** [HarnessEvo] and [Twin] measure harness effects at
a *fixed* model; [WMAblation] measures whether those effects *survive* a model upgrade. Both can be
true: harness engineering produces large gains now and is progressively absorbed by stronger models —
which is exactly what [Weng2026] predicts, drawing the analogy to prompt engineering becoming less
central as instruction tuning improved.

**Consequence for the FYP:** no ARC-AGI-3 harness result is interpretable without a model-capability
sweep. This should be a design commitment, not a robustness check added later.

---

## 4. Transfer to ARC-AGI-3: what survives contact with the benchmark

The constraints, taken from the ARC-AGI-3 paper (arXiv:2603.24621) and the ARC Prize 2026 competition
page (cached at `refs/web/arcprize-competition-2026.txt`): no stated goals, rules or instructions; no
internet access during evaluation; efficiency-based scoring
`min(1, human_baseline_actions / agent_actions)^2` with later levels weighted more heavily; a
public:private split of roughly 1:5; and mandatory open-sourcing under a permissive licence for prize
eligibility.

> **A number that could not be reconciled.** The internal briefing states 135 environments at roughly
> 1:5 public:private. [BenchmarkValidity] describes 25 public games and a "full 55-game private
> evaluation"; [Twin] and [Tycho] report 183 levels across the 25 public games. 25 + 55 ≠ 135. This is
> recorded as `[unverified]` rather than resolved: the discrepancy may reflect the difference between
> environments, games and levels, or a change in the set between March and August 2026. **Confirm
> against `docs.arcprize.org` before quoting any of these figures in the dissertation.**

### 4.1 Topic 1 (harness) — transfers almost completely, and is already the state of the art

Frozen-weight scaffold improvement needs no internet, no training infrastructure and no labelled
data, and is trivially open-sourceable — it fits every constraint. It is also, as of August 2026, how
every leading ARC-AGI-3 result was obtained ([Twin], [Tycho], [ExecWM], [WorkspaceOpt]).

Three things do **not** transfer. (i) *Any scaffold step that costs environment actions is priced by
the metric*, and priced quadratically — so [Agentless]'s warning that elaborate scaffolds may lose to
simple pipelines bites harder here than in software engineering. (ii) *Skill and workflow
accumulation across 135 environments will hit [LibraryDrift]*, whose motivating measurement is that
LLM-authored skills delivered +0.0pp where human-curated ones delivered +16.2pp. (iii) *Harness
self-improvement will be prompted to find failures in rule-shaped environments with open-ended rule
sets* — two of the three conditions [PhantomGuardrails] identifies as jointly sufficient for the
proposer to invent failures that never happened.

### 4.2 Topic 2 (teacher–student) — the structure transfers; the weight updates do not

The benchmark supplies what a teacher needs: a task pool with difficulty-ordered levels ([TSCL],
[PLR] apply directly, with no generator at all), a mechanical validity check for generated
environments (does it run?), and — unusually — **a published human baseline per level, which can
stand in for [PAIRED]'s antagonist return, making regret computable without training a second agent.**
[ACCEL]'s edit-the-frontier operator is the most implementable generator, since grid environments
support small semantic edits.

What does not transfer: every teacher–student system in the corpus updates the student's weights.
Under the no-internet, frozen-model constraint the "student" is a scaffold plus a memory, so the
teacher's reward has to be defined against a *scaffold's* measured improvement rather than a policy
gradient. There is no precedent for this in the corpus — which is the gap, not an oversight.

Also: generated environments are for *practice only*. Evaluation happens on the real private set, so
the [OMNI-EPIC] hazard (the generator writing its own reward function) is avoidable by construction —
generated-task reward and evaluation reward must be kept strictly separate.

### 4.3 Topic 3 (frozen weights) — the premise is sound; the easy version is finished

The frozen-weights premise survives — [Twin] settles that a frozen model plus a harness can go from
7.8% to 93.3% — and the environment provides the near-perfect verifier that [LimitsResampling] shows
is the precondition for inference scaling to pay.

But three constraints cut hard. (i) **No internet at evaluation** means no frontier API, so every
public-set result in §L5 was obtained under conditions the competition does not allow; the FYP's
setting is closer to [BenchmarkValidity]'s Qwen2.5-0.5B (RHAE 0.2116) than to Opus 5. (ii) **The
efficiency metric penalises the sampling that all of Topic 3 §1 relies on** — coverage curves are
priced in actions, which is why search must happen inside a world model rather than in the
environment. (iii) **The public set is saturated and possibly invalid** ([WMAblation],
[BenchmarkValidity]), so public-set numbers cannot support a capability claim.

---

## 5. Gap statement

The taxonomy's empty cells (`taxonomy.md` E1–E6) intersect at one position that no entry in this
corpus occupies: **a loop that co-evolves the task distribution and the harness, for a learner whose
weights never change, verified by an interactive environment, and optimised for action efficiency
rather than success rate.**

Each clause is separately unoccupied. Harness evolution ([DGM], [DarwinX], [SICA], [Twin]) runs
against a *fixed* task distribution. Task generation ([AbsoluteZero], [R-Zero], [SOAR-Teacher],
[GASP]) runs against a *fixed* harness and updates the student's weights. The one system that pairs a
curriculum with a frozen learner, [Voyager], never optimises its curriculum against measured student
progress, operates in an environment saturated with the language priors ARC-AGI-3 exists to exclude,
and is scored on items collected rather than on efficiency. And exactly one entry in the entire
corpus — [MetaEvolve] — trains against a fitness that combines correctness with efficiency, the shape
ARC-AGI-3's metric actually has.

The 2026 ARC-AGI-3 results sharpen rather than close this. [Twin] and [Tycho] show a frozen frontier
model with a self-authored world model can approach or reach human action efficiency on the public
set; [WMAblation], from inside that same line, concludes those results "indicate public-set
saturation only", and [BenchmarkValidity] shows every public game is reachable by non-intelligent
strategies. So the answered question is *whether a strong frozen model plus a hand-designed harness
can clear the public set*. The unanswered ones are whether such gains hold on the private set, whether
they survive the no-internet constraint that rules out frontier APIs, and whether a **small** model
can reach them by *learning* its harness and its own practice curriculum instead of being handed one.

**Falsification.** This gap claim fails if a system is found that co-evolves scaffold and task
distribution for a frozen learner under an efficiency metric. The nearest candidates found were
[SkillSP] (co-evolves proposer, solver and skill library — but updates weights) and [MCE]
(co-evolves engineering skills and context artefacts — but against a fixed task distribution). The
search that would refute it is recorded as an open lead in `search-log.md`.

*(Word count of §5: ~290.)*

---

## 6. Evaluation-design notes — ablations and baselines to copy

Ordered by how much they would strengthen the eventual results chapter per unit of effort.

**Mandatory baselines**

1. **Non-intelligent floor** ([BenchmarkValidity]): blind single step, one probing action, single
   repeated action under a 50–200 step budget. Any claim must clear this floor, and reporting it is a
   credibility signal in itself.
2. **Bare model, no harness** ([Twin]): the 7.8% / 61.1% / 93.3% three-point decomposition — bare
   model, generic off-the-shelf harness, proposed mechanism — should be the standard reporting format.
3. **Simplest reasonable pipeline** ([Agentless]): a fixed, non-agentic controller, to show the
   agentic machinery earns its actions.
4. **Single-lineage vs archive** ([SICA] vs [DGM]): isolates whether the population is load-bearing.
5. **Verifier-free sharpened sampling** ([ReasoningWithSampling]): so "our loop helped" is not
   confused with "we sampled better".
6. **Test-time training arm** ([TTT-FewShot]): the strongest competing hypothesis, and the one the
   FYP's frozen-weights premise must be measured against rather than assumed past.

**Mandatory sweeps**

7. **Model-capability × reasoning-effort × harness-variant grid** ([WMAblation]): without it, harness
   effects and backbone effects are inseparable. This is the single most important design decision in
   the list.
8. **Reasoning-length sweep** ([InverseScaling]): more deliberation is not monotonically better, and
   two of the four categories where it hurts (distractors, constraint tracking) describe ARC-AGI-3.
9. **Coverage vs budget curves** ([Monkeys]), with the x-axis in **environment actions** rather than
   samples, since actions are what the metric prices.

**Ablations that probe the mechanism**

10. **Intrinsic vs extrinsic feedback** ([SelfCorrect]): run the loop once with environment
    verification and once with the agent's own judgement, and report the gap.
11. **Defect-injection audit** ([BlindCurator]): corrupt the acceptance signal at known false-pass
    rates and find where the mechanism breaks. Cheap; almost nobody does it.
12. **"Correct action is do nothing" control** ([PhantomGuardrails]): present the self-improvement
    loop with a run containing no real failure and measure how often it invents one.
13. **Grounded vs intrinsic teacher reward** ([SOAR-Teacher]), and **validity × difficulty factorised
    reward** ([VHG]): the two teacher-reward ablations the 2026 literature says matter most.
14. **Diversity over iterations, measured functionally not superficially** ([R-Diverse]): for
    ARC-AGI-3, diversity over the *rules* an environment exercises, not over its pixels.
15. **Skill-library governance** ([LibraryDrift]): outcome-driven retirement, bounded active cap, and
    an append-only evidence log with per-skill contribution attribution — plus the no-injection and
    premature-retirement ablations that bracket it.

**Reporting discipline**

16. **Score and actions-per-game together** ([WorkspaceOpt]), and **cost per run** ([StateM]).
17. **Public vs private stated bluntly** ([WMAblation], [ARCPrize2025]): the corpus's most recent
    ARC-AGI-3 papers all volunteer that their results are public-set only. Matching that candour
    costs nothing and is the difference between a defensible FYP and an overclaiming one.
18. **Pass@k-style capability-boundary test** ([RLVR-Elicitation]): the transposition described in
    §3.1. If the FYP runs one novel experiment beyond its main contribution, this is the one — it is
    the elicitation-vs-acquisition question asked on an interactive benchmark for the first time.

---

## 7. Note on the recommended chapter structure

The structure proposed in the issue (2.1 scope/method → 2.2 background → 2.3 taxonomy by locus of
change → 2.4 learning signals → 2.5 failure modes → 2.6 synthesis and gap) is sound and this corpus
is organised to serve it. Its rationale — that Topic 3 is a *property* cutting across Topics 1 and 2
rather than a parallel category — is confirmed by the taxonomy: the frozen-weights condition appears
as a constraint on rows, not as a row.

Two adjustments are recommended, both evidence-driven:

1. **§2.2 Background must be rewritten around the 2026 interactive results, not the launch figures.**
   The briefing's "frontier ~0.5%, best preview agent ~12.6%" was accurate for March 2026 and is
   obsolete: [Twin] reports 93.3% and [Tycho] 100.00 RHAE on the public set. The background section
   must then immediately present [BenchmarkValidity] and [WMAblation], or it will mislead the reader
   about what those numbers mean.
2. **§2.5 Failure modes deserves more room than a survey chapter usually gives it.** The 2026
   failure-mode literature ([LibraryDrift], [BlindCurator], [PhantomGuardrails], [R-Diverse],
   [VocabDropout], [TextPolicies]) is unusually strong for such a young field, and it constrains the
   FYP's design more tightly than the positive results do. Several of these papers supply ready-made
   ablations (§6, items 10–15), so the section pays for itself in the results chapter.
