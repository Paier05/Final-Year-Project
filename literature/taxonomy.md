# Taxonomy — what is optimised × where the learning signal comes from

Every one of the 89 full entries in `topic1-harness.md`, `topic2-teacher-student.md` and
`topic3-frozen-weights.md` is placed below. Entries appear in more than one cell when they change
more than one thing (e.g. most teacher–student systems change both the task distribution and the
student's weights) — the cell counts are therefore larger than 89 and are not a partition.

## Axis definitions

**Rows — what is optimised (the locus of change).** The five categories named in the issue, plus one
the corpus forced open:

| Row | Meaning |
|---|---|
| `weights` | Model parameters are updated, at training time or at test time. |
| `context/prompt` | The text conditioning the model changes: instructions, demonstrations, policy text, trajectory history. |
| `scaffold code` | The executable structure around the model changes: agent loop, tools, control flow, world-model programs, the agent's own source. |
| `task distribution` | What the learner practises on changes: generated, edited, selected or re-ordered tasks and environments. |
| `memory` | A persistent store the system reads and writes: skills, workflows, experiences, insights, runbooks. |
| **`nothing persistent`** | **Added.** Extra inference compute only; the system is identical before and after. The issue's five categories have no home for most of Topic 3 §1, and pretending best-of-N "optimises the context" would hide exactly the distinction the elicitation argument depends on. |

**Columns — where the learning signal comes from.** Precise readings, since several papers would
otherwise be placed by vibes:

| Column | Meaning |
|---|---|
| `executable verifier` | Correctness is established mechanically and deterministically: running code, running tests, replaying transitions, checking an answer against a formal rule. |
| `environment reward` | A score returned by an interactive environment or benchmark harness (task success, return, RHAE), not obtained by executing a candidate artefact. |
| `learned reward model` | A trained reward model or an LLM acting as judge/critic — including a model judging its own output. |
| `human labels` | Human annotation inside the loop, including gold answers supplied by a labelled dataset. |
| `self-consistency` | Agreement among samples or among model instances. No external ground truth. |
| `none` | No correctness signal at all: likelihood, compression length, or an unconditioned intervention. |

Two placement conventions, stated so the table can be audited: **(i)** a mechanical answer check
against a rule (rather than against a human-written gold answer) counts as `executable verifier`;
**(ii)** [GodelMachine]'s deductive proof search is filed under `executable verifier` as its
degenerate limiting case — mechanical, deterministic, and unattainable at scale.

---

## The table

Handles are those used in the topic files. **Bold** = ARC-AGI or ARC-AGI-3 work.

| ↓ optimised \ signal → | executable verifier | environment reward | learned reward model | human labels | self-consistency | none |
|---|---|---|---|---|---|---|
| **weights** | AbsoluteZero, SOAR-Teacher, SOAR-ProgSynth, MetaEvolve, Learnability, GASP, SkillSP, VHG(hard) | AlphaZero, AsymSelfPlay, TSCL, GoalGAN, POET, EnhancedPOET, PAIRED, PLR, RobustPLR, ACCEL, TRACED, AdA | VHG(soft) | STaR, LetsVerify, **TTT-FewShot**, **TRM** | R-Zero, SQLM, R-Diverse, VocabDropout | **CompressARC**, s1(SFT stage) |
| **context/prompt** | TextGrad(code tasks) | Promptbreeder, EvoPrompt, OPRO, GEPA, DSPy, TextPolicies, AlgorithmDistillation, AdA(test time) | TextGrad(open tasks) | — *(empty)* | — *(empty)* | ICLasGD, s1(budget forcing) |
| **scaffold code** | GodelMachine, DGM, SICA, LiveSWE, DarwinX, AlphaEvolve, AFlow, LATM, StateM, PhantomGuardrails, FrozenControl, **Twin**, **Tycho**, **ExecWM** | ADAS, GodelAgent, MCE, **WorkspaceOpt** | — *(empty)* | — *(empty)* | — *(empty)* | Weng2026 *(position)* |
| **task distribution** | AbsoluteZero, GASP, Learnability, VHG, LearnableInfoGain, SkillSP, Voyager | AsymSelfPlay, TSCL, GoalGAN, POET, EnhancedPOET, PAIRED, PLR, RobustPLR, ACCEL, TRACED, AdA | OMNI, OMNI-EPIC | — *(empty)* | R-Zero, SQLM, R-Diverse, VocabDropout | — *(empty)* |
| **memory** | Voyager, LATM, LibraryDrift, StateM, SkillSP | ExpeL, Reflexion, AWM, AdaMEM, **WorkspaceOpt** | BlindCurator *(as object of study)* | — *(empty)* | — *(empty)* | DynamicCheatsheet |
| **nothing persistent** | Monkeys, LimitsResampling, InverseScaling | **BenchmarkValidity** | ToT, Snell, Self-Refine | — *(empty)* | SelfConsistency, Debate | ReasoningWithSampling, SelfCorrect |

### Measurement and framing entries (no locus of change)

These are studies, surveys, benchmarks and reports; they are classified by the signal they *measure
against*, not by anything they optimise.

| Entry | Signal it measures against | What it measures |
|---|---|---|
| HarnessEvo | executable verifier | Harness version, model held constant |
| Agentless | executable verifier | Elaborate scaffold vs minimal pipeline |
| **WMAblation** | executable verifier | Scaffold mechanism vs backbone capability |
| RLVR-Elicitation | executable verifier | Whether RL exceeds the base model's support |
| MATH-Beyond | executable verifier | A task set base models fail at high k |
| GSM-Symbolic | executable verifier | Fragility under surface perturbation |
| IllusionOfThinking | executable verifier | Accuracy and effort vs problem complexity |
| **ARCPrize2025** | environment reward (private set) | Competition methods and contamination |
| SelfImprovSurvey | n/a | Update target × driving signal (a taxonomy matching this one) |

---

## Crowded cells

Three cells hold most of the corpus, and each concentration says something.

1. **`scaffold code` × `executable verifier` (14 entries).** Self-modifying scaffolds are attempted
   *only* where a mechanical check exists. This is not a coincidence — it is the field's implicit
   admission that scaffold self-modification is unsafe without one, which [BlindCurator] and
   [PhantomGuardrails] then demonstrate directly.
2. **`weights` × `environment reward` (12 entries).** The entire classical curriculum/UED line. Every
   one of these systems trains the student's parameters; the curriculum exists to make gradient
   descent efficient.
3. **`task distribution` × `environment reward` (11 entries).** The same block seen from the teacher's
   side — the two cells are the same papers, which is the point: in the pre-LLM literature,
   generating tasks and updating weights are inseparable.

## Empty cells — the gap statement falls out of these

**E1. `scaffold code` is never driven by a soft signal.** Its two occupied columns are `executable
verifier` (14 entries) and `environment reward` (4); the other three are empty. No paper in this corpus
evolves an agent's scaffold using a learned judge, human labels, or self-consistency as the
acceptance signal. Read one way this is a limitation of the field; read another it is a *result*,
and [BlindCurator]'s threshold (contribution-based retirement dies past a 0.45 false-pass rate)
explains why. **Consequence for the FYP:** ARC-AGI-3 supplies a near-perfect external verifier for
free, which is precisely the condition under which the crowded cell's methods are known to work.

**E2. `task distribution` × `human labels` and × `none` are empty; `task distribution` ×
`executable verifier` contains only code and maths.** Every entry that generates tasks against a
mechanical verifier generates *programs or maths problems*. Nobody generates **interactive
environments** verified by execution. [OMNI-EPIC] comes closest — it writes environment code — but
its interestingness filter is an LLM judge and it writes its own reward function, so the verifier is
inside the loop it is supposed to police.

**E3. `context/prompt` × `human labels` and × `self-consistency` are empty**, and `context` ×
`executable verifier` holds one partial entry. Context optimisation is almost always driven by
aggregate benchmark score. Nobody optimises context against a *step-level mechanical* signal — which
an interactive environment provides at every transition, for free.

**E4. The intersection of Topic 1 and Topic 2 is empty.** [DarwinX] and [DGM] evolve a harness against
a **fixed** task distribution. [R-Zero], [SOAR-Teacher] and [AbsoluteZero] evolve a task distribution
against a **fixed** harness (and update weights). **No entry in this corpus co-evolves the harness and
the task distribution together.** This is the single clearest structural hole in the table.

**E5. The intersection of Topic 2 and Topic 3 has exactly one occupant.** Cross-referencing the
`task distribution` row against the frozen-weights requirement: every teacher–student system here
updates the student's parameters, **except [Voyager]**, whose automatic curriculum drives a skill
library on a frozen GPT-4. And Voyager is a weak occupant — its curriculum is *prompted*, never
optimised against the student's measured progress; its environment (Minecraft) is saturated with the
language priors ARC-AGI-3 exists to exclude; and it is scored on items collected, not on efficiency.

**E6. Efficiency as the optimisation target is absent almost everywhere.** Exactly one entry trains
on a fitness that combines correctness *and* efficiency ([MetaEvolve], on code runtime), and a
handful report action or cost efficiency as a secondary outcome ([AWM], [StateM], [WorkspaceOpt],
[Tycho]). The rest optimise success rate. ARC-AGI-3 scores
`min(1, human_baseline_actions / agent_actions)^2` — a metric essentially no method in this corpus
was designed for.

---

## How the empty cells combine into one sentence

E4 + E5 + E6 name a single unoccupied position:

> **A loop that co-evolves the task distribution and the harness, for a learner whose weights never
> change, verified by an interactive environment, and optimised for action efficiency rather than
> success rate.**

Each clause is empty in the table above, and their conjunction is the FYP's position. `synthesis.md`
§5 argues that this is a genuine gap rather than an artefact of how the axes were drawn, and states
what would falsify that claim.
