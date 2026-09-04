# Adjacent work — relevant but out of scope for the three topics

Everything here was found by the searches in `search-log.md` and **verified against the live record**
(cached under `refs/`), but does not earn a full entry in a topic file. Each line says why. Nothing
here is padding for the per-topic counts; the counts in the topic files exclude these entirely.

Four reasons for exclusion recur, and are marked:
`[criteria]` fails an explicit inclusion rule from the issue ·
`[survey]` a survey/roadmap rather than a result ·
`[narrow]` a real result in a domain too far from an interactive grid agent ·
`[subsumed]` says something a full entry already says better.

---

## Excluded by the issue's own inclusion criteria

- **Self-Instruct: Aligning Language Models with Self-Generated Instructions** — arXiv:2212.10560 (ACL 2023). `[criteria]` The canonical self-generated-instruction pipeline (+33% absolute over vanilla GPT-3 on Super-NaturalInstructions), but the generator never adapts to the learner: it is one-shot synthetic data, which Topic 2 explicitly excludes as static.
- **WizardLM / Evol-Instruct** — arXiv:2304.12244 (ICLR 2024). `[criteria]` Instructions are *evolved* into more complex forms by an LLM, which looks like a curriculum, but the evolution is blind to the student's ability. Same exclusion as Self-Instruct. Worth citing in the FYP only as "task evolution without a student signal".
- **Asymmetric self-play for automatic goal discovery in robotic manipulation** — arXiv:2101.04882 (OpenAI et al., 2021). `[narrow]` A faithful large-scale Alice/Bob implementation with goal relabelling, but the transferable ideas are already covered by [AsymSelfPlay] and [GoalGAN]; the robotics specifics (object poses, sparse manipulation rewards) do not carry to grid environments.
- **Multi-Agent Evolve: LLM Self-Improve through Co-evolution** — arXiv:2510.23595. `[subsumed]` Proposer/Solver/Judge triplet from a single LLM, +4.54% average on Qwen2.5-3B. The triadic structure is better stated by [LearnableInfoGain] and the empirical lessons by [R-Zero] + [R-Diverse].
- **Transferability for General Reasoning: An Automated Curriculum for Multi-Domain RLVR (TAC)** — arXiv:2606.25178. `[narrow]` Bandit curriculum using projected gradients to estimate cross-domain transfer at <1% overhead, +2.8 points over a learnability-only bandit. Genuinely interesting, but it needs gradient access, which a frozen-weights project does not have. Revisit if the FYP ever fine-tunes.

## Self-play and curriculum variants that add little beyond the full entries

- **Search Self-play: Pushing the Frontier of Agent Capability without Supervision** — arXiv:2510.18821. `[subsumed]` Self-play for search agents; the proposer/solver/verifier lesson is covered.
- **Evolving Alignment via Asymmetric Self-Play** — arXiv:2411.00062. `[narrow]` Asymmetric self-play applied to alignment/preference prompts rather than to verifiable tasks; the verifier story, which is what this FYP needs, is absent.
- **G-Zero: Self-Play for Open-Ended Generation from Zero Data** — arXiv:2605.09959. `[narrow]` Open-ended *generation* rather than task solving; no mechanical verifier.
- **Bootstrapping Post-training Signals for Open-ended Tasks via Rubric-based Self-play** — arXiv:2604.20051. `[criteria]` The verification signal is a rubric judged by an LLM, i.e. exactly the biased-judge regime [BlindCurator] shows is unsafe for a self-evolving loop.
- **Grounding Aleatoric Uncertainty for Unsupervised Environment Design** — arXiv:2207.05219. `[narrow]` Fixes regret estimation under environment stochasticity. ARC-AGI-3 environments are deterministic (see [Tycho]'s Moore-machine formalisation), so the problem it solves does not arise — but cite it if any stochastic variant is ever introduced.

## Harness work covered better elsewhere, or definitional

- **Recursive Agent Harnesses** — arXiv:2606.13643. `[subsumed]` A parent agent spawning full sub-agent harnesses; reports Oolong-Synthetic 71.75% → 81.36% at a fixed GPT-5 backbone, which is a clean harness-not-model result. Excluded only because [HarnessEvo] makes the same point with a controlled longitudinal design and [StateM] makes it with a stronger efficiency argument. Promote to a full entry if the FYP uses sub-agents.
- **Natural-Language Agent Harnesses** — arXiv:2603.25723. `[subsumed]` Represents a harness as an editable natural-language document executed by a shared runtime, achieving comparable outcomes to code realisations with much shorter policies. Useful if the FYP wants its harness to be human-auditable for prize eligibility.
- **What makes a harness a harness: necessary and sufficient conditions for an agent harness** — arXiv:2606.10106. `[survey]` A conceptual/definitional analysis with an inclusion–exclusion test applied to six real harnesses. Cite in §2.1 when defining terms; it contains no results.
- **Code as Agent Harness** — arXiv:2605.18747. `[survey]` A 42-author survey framing code as the operational substrate for agent reasoning, action and execution-based verification. A good snowballing source; superseded for this project's purposes by [SelfImprovSurvey].
- **A Comprehensive Survey of Self-Evolving AI Agents** — arXiv:2508.07407. `[survey]` Earlier and broader than [SelfImprovSurvey]; useful for pre-2026 coverage.
- **A Survey of Agent Memory in the Second Half: Towards Self-Evolving and Long-Horizon Agents** — arXiv:2602.06052. `[survey]` The memory-specific companion survey; the natural entry point if the FYP's memory design needs broader grounding.
- **PYTHALAB-MERA: Validation-Grounded Memory, Retrieval, and Acceptance Control for Frozen-LLM Coding Agents** — arXiv:2605.08468. `[narrow]` A frozen-model external controller with TD(λ)-style delayed credit assignment; passed 8/9 strict validations against 0/9 for a self-refinement baseline, but on three tasks with three repetitions — the author is explicit that the claim is bounded to that recorded setting. The delayed-credit mechanism is worth borrowing; the evidence is too thin to lean on.
- **Your Agent May Misevolve: Emergent Risks in Self-evolving LLM Agents** — arXiv:2509.26354. `[narrow]` Safety-oriented analysis of self-evolution risk. The issue puts AI-safety arguments about RSI risk out of scope; listed because its failure taxonomy overlaps usefully with [LibraryDrift] and [PhantomGuardrails].

## Test-time and ARC-adjacent work

- **More Agents Is All You Need** — arXiv:2402.05120. `[subsumed]` Sampling-and-voting scales with agent count; the same phenomenon is measured more carefully by [Monkeys] and bounded by [LimitsResampling].
- **Many-Shot In-Context Learning** — arXiv:2404.11018. `[subsumed]` Scaling in-context examples into the hundreds/thousands. ARC-AGI-3 has no demonstration examples to scale, so the mechanism has nothing to consume.
- **Tiny Recursive Models on ARC-AGI-1: Inductive Biases, Identity Conditioning, and Test-Time Compute** — arXiv:2512.11847. `[subsumed]` The follow-up analysis of [TRM]; cited inside that entry. Read it before quoting TRM's 45% as evidence of anything architectural.
- **PRO-LONG: Programmatic Memory Enables Long-Horizon Reasoning** — arXiv:2607.20064. `[narrow]` Programmatic memory for long-horizon reasoning; overlaps [DynamicCheatsheet] and [AWM] without adding a distinct mechanism.
- **Graph-Based Exploration for ARC-AGI-3 Interactive Reasoning Tasks** — arXiv:2512.24156. `[subsumed]` An early ARC-AGI-3 exploration agent, predating the 2026 world-model line; kept for the lineage in §2.2 but superseded by [Twin]/[Tycho]/[ExecWM].
- **OPINE-World: Programmatic World Modeling with Ontology-error-Prioritized Interactive Exploration** — arXiv:2607.01531. `[subsumed]` Another programmatic-world-model ARC-AGI-3 agent from the same 2026 wave; its error-prioritised exploration is a variant of [Twin]'s counterexample repair. Promote to a full entry if the FYP works specifically on exploration policy.
- **WAM-TTT: Steering World-Action Models by Watching Human Play at Test Time** — arXiv:2607.06988. `[narrow]` Test-time steering from human play; ARC-AGI-3 evaluation provides no human demonstrations, so the input it needs is unavailable.
