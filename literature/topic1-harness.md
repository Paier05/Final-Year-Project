# Topic 1 — Harness engineering and self-modifying agent scaffolds

**Scope.** Work where the thing that improves is the *scaffold* around the model — the agent loop,
prompts, tool definitions, memory, control flow, or the agent's own source code — rather than the
weights. Excluded: prompt-engineering how-tos with no evaluation, and single-shot chain-of-thought
papers with no improvement loop.

**Corpus size:** 31 entries (30 archival + 1 `[non-archival]`), all verified against the live record.
Records cached under `refs/`. Cross-topic duplicates are written up once here and cross-referenced
from `topic2-teacher-student.md` / `topic3-frozen-weights.md`.

**Reading order.** §1 is the lineage that runs from provably-optimal self-rewriting to empirical
self-modifying agents; §2 is scaffold/prompt optimisation as a first-class optimisation problem;
§3 is accumulation — tools, skills, workflows, experience; §4 is the empirical harness-vs-model
question; §5 is the failure modes, which is where this topic is currently most active.

---

## §1 Self-modifying agents: from proof to empirical validation

### [GodelMachine] — Gödel Machines: Self-Referential Universal Problem Solvers Making Provably Optimal Self-Improvements
- **Authors / Year / Venue:** Jürgen Schmidhuber / 2003 (v5 2006) / arXiv preprint; variants published in *Adaptive Agents and Multi-Agent Systems II* (LNCS 3394, Springer 2005), Proc. ICANN 2005, and *Artificial General Intelligence* (Springer 2006).
- **Link:** arXiv:cs/0309048
- **Verified:** yes — arXiv record retrieved and cached (`refs/arxiv/cs_0309048.json`); the journal-reference field on the record lists the three published variants.
- **Type:** position / theory
- **Problem:** Whether a problem solver can rewrite arbitrary parts of its own code in a way that is guaranteed, not merely hoped, to be an improvement.
- **Method:** The system's entire initial code — including a proof searcher, the hardware axioms, and a problem-dependent utility function — is written as axioms the system can reason about. A proof searcher systematically enumerates computable proof techniques (programs whose outputs are proofs) looking for a proof that some self-rewrite raises expected utility. A rewrite is executed only once such a proof is found. Because the system must first prove that continuing to search for a *better* rewrite is not worthwhile, the accepted rewrite is globally optimal rather than a local optimum. Nothing is learned statistically; the update rule is deductive.
- **Verification signal:** formal proof against an axiomatised utility function — the strongest verifier in this corpus, and the one that does not scale.
- **What changes:** scaffold code (in fact, *all* code, including the searcher that changes the code).
- **Results that matter:** No empirical results; the contribution is the optimality argument ("no local maxima") and the construction showing that global self-reference is consistent. The paper's own framing is that this is the first mathematically rigorous class of such solvers.
- **Limitations / criticisms:** The proof requirement is the whole difficulty: for essentially any interesting rewrite in a realistic environment, no proof of net benefit exists or can be found in reasonable time. The [DGM] authors state this directly as their motivation for replacing proof with empirical benchmark validation.
- **Relevance to this FYP (1–5) and why:** **3.** No mechanism transfers directly — ARC-AGI-3 offers no axiomatisation to prove things about. It matters as the origin of the topic's central design question: *what evidence licenses a self-modification?* This project must answer that question with an empirical criterion, and the Gödel machine is the reference point that makes the answer non-arbitrary.
- **Reusable structure:** The framing "self-modification is only admissible against an explicit utility function and an explicit acceptance rule" — reusable directly as the design contract for the FYP's accept/reject step, with `min(1, human_baseline/agent_actions)^2` playing the role of the utility function.
- **BibTeX:** 

```bibtex
@misc{schmidhuber2003goedel,
  title         = {{Goedel Machines: Self-Referential Universal Problem Solvers Making Provably Optimal Self-Improvements}},
  author        = {Schmidhuber, Juergen},
  year          = {2003},
  eprint        = {cs/0309048},
  archivePrefix = {arXiv},
  primaryClass  = {cs.LO},
  url           = {https://arxiv.org/abs/cs/0309048},
  note          = {Variants published in 'Adaptive Agents and Multi-Agent Systems II', LNCS 3394, p. 1-23, Springer, 2005: ISBN 978-3-540-25260-3; as well as in Proc. ICANN 2005, LNCS 3697, p. 223-233, Springer, 2005 ...}
}
```

### [DGM] — Darwin Gödel Machine: Open-Ended Evolution of Self-Improving Agents
- **Authors / Year / Venue:** Jenny Zhang, Shengran Hu, Cong Lu, Robert Lange, Jeff Clune / 2025 (v3 2026-03) / arXiv preprint (Sakana AI / UBC).
- **Link:** arXiv:2505.22954
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2505.22954.json`).
- **Type:** method
- **Problem:** Making self-modifying agents practical by dropping the Gödel machine's proof requirement without dropping its acceptance discipline.
- **Method:** DGM maintains an *archive* of coding agents. Each iteration samples a parent agent from the archive, uses a foundation model to write a modified version of that agent's own code, and then runs the child on coding benchmarks; children that validate are added to the archive. Because the agent being modified is also the agent that performs modifications, improvements to editing ability compound. The archive (rather than a single lineage) is what makes the search open-ended: many branches are kept alive, so a locally worse variant can still be a stepping stone. Model weights are never touched.
- **Verification signal:** executable check — held-out coding benchmark scores (SWE-bench, Polyglot) act as the empirical stand-in for the Gödel machine's proof.
- **What changes:** scaffold code, plus the archive (a population-level memory).
- **Results that matter:** SWE-bench 20.0% → 50.0% and Polyglot 14.2% → 30.7% through self-modification alone; the paper reports that DGM beats ablations without self-improvement and without open-ended archive exploration, which is the comparison that isolates the mechanism.
- **Limitations / criticisms:** Improvement is measured on the same benchmark family that supplies the selection signal, so "capability" and "benchmark fit" are hard to separate; [LiveSWE] argues the offline training is costly and transfers poorly across models and benchmarks. The discovered edits reported (better editing tools, context management, peer review) are harness engineering a human could also do — which is the point, but it also caps the novelty claim.
- **Relevance to this FYP (1–5) and why:** **5.** This is the closest existing template for the FYP's loop: an archive-based, empirically-validated, weight-frozen self-modification cycle. The transferable mechanism is *archive + validate-before-admit*, with the ARC-AGI-3 efficiency score replacing SWE-bench as the fitness function.
- **Reusable structure:** The archive-with-parent-sampling algorithm; the ablation design (no-self-improvement and no-open-ended-exploration arms) is exactly the pair of baselines the FYP's results chapter needs.
- **BibTeX:** 

```bibtex
@misc{zhang2025darwin,
  title         = {{Darwin Godel Machine: Open-Ended Evolution of Self-Improving Agents}},
  author        = {Zhang, Jenny and Hu, Shengran and Lu, Cong and Lange, Robert and Clune, Jeff},
  year          = {2025},
  eprint        = {2505.22954},
  archivePrefix = {arXiv},
  primaryClass  = {cs.AI},
  url           = {https://arxiv.org/abs/2505.22954}
}
```

### [ADAS] — Automated Design of Agentic Systems
- **Authors / Year / Venue:** Shengran Hu, Cong Lu, Jeff Clune / 2024 (v2 2025-03) / ICLR 2025 (venue confirmed via Semantic Scholar record: "International Conference on Learning Representations"; 303 citations at time of retrieval).
- **Link:** arXiv:2408.08435
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2408.08435.json`).
- **Type:** method
- **Problem:** Agentic building blocks (chain-of-thought, self-reflection, tool use) are hand-designed; the paper argues they should be learned instead.
- **Method:** ADAS is framed as a research area — automatically inventing agentic system designs — and instantiated by *Meta Agent Search*. Because agents are defined in code and code is Turing-complete, the search space in principle contains any agentic system. A meta agent programs new agents, evaluates them, appends them to a growing archive of discoveries, and conditions the next proposal on that archive. Only the meta agent's prompt sees the archive; no weights change anywhere.
- **Verification signal:** environment/benchmark score across coding, science and maths domains.
- **What changes:** scaffold code (the discovered agent programs), plus the archive of discoveries.
- **Results that matter:** Discovered agents outperform state-of-the-art hand-designed agents across the tested domains, and — the result the authors flag as surprising — retain their advantage when transferred to different domains and different underlying models, i.e. the discovered scaffold is not model-specific.
- **Limitations / criticisms:** Search is expensive and the meta agent's proposals are bounded by what the foundation model already knows about agent design; the transfer claim is demonstrated on a small set of domains. Later harness work ([HarnessEvo], [Agentless]) suggests measured scaffold gains are sensitive to evaluation details that ADAS does not control for.
- **Relevance to this FYP (1–5) and why:** **4.** Establishes the core claim the FYP depends on — that scaffold search yields *transferable* gains on a frozen model. The cross-domain transfer result is the strongest published argument that a harness improved on training environments can carry to unseen ARC-AGI-3 games.
- **Reusable structure:** The meta-agent-writes-agent-code formulation, and the transfer protocol (optimise on domain A, evaluate unchanged on domain B and on a different base model) — directly copyable as the FYP's generalisation test across public/private ARC-AGI-3 splits.
- **BibTeX:** 

```bibtex
@misc{hu2024automated,
  title         = {{Automated Design of Agentic Systems}},
  author        = {Hu, Shengran and Lu, Cong and Clune, Jeff},
  year          = {2024},
  eprint        = {2408.08435},
  archivePrefix = {arXiv},
  primaryClass  = {cs.AI},
  url           = {https://arxiv.org/abs/2408.08435}
}
```

### [GodelAgent] — Gödel Agent: A Self-Referential Agent Framework for Recursive Self-Improvement
- **Authors / Year / Venue:** Xunjian Yin, Xinyi Wang, Liangming Pan, Li Lin, Xiaojun Wan, William Yang Wang / 2024 (v4 2025-05) / **ACL 2025 (main conference)** — stated on the arXiv record.
- **Link:** arXiv:2410.04444
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2410.04444.json`); the comment field states "ACL 2025 main". Found via OpenReview search rather than by arXiv keyword search (see `search-log.md`).
- **Type:** method
- **Problem:** Both fixed pipelines and meta-learning frameworks like [ADAS] restrict the search to human-designed components, so the globally optimal agent design may lie outside the space either can reach.
- **Method:** Gödel Agent is a self-evolving framework in which the agent **dynamically modifies its own logic and behaviour at runtime**, guided only by a high-level objective expressed in a prompt — no predefined routines, and no fixed optimisation algorithm wrapping the search. The contrast with [ADAS] is deliberate: ADAS has a meta agent that writes a *separate* target agent within a defined harness, whereas here the improving agent and the improved agent are the same running process.
- **Verification signal:** environment/benchmark score on mathematical reasoning and agent tasks.
- **What changes:** scaffold code (its own logic and behaviour), at runtime.
- **Results that matter:** Continuous self-improvement is demonstrated, surpassing manually crafted agents in **performance, efficiency and generalisability**. The abstract reports no single headline number, so none is quoted.
- **Limitations / criticisms:** Unconstrained self-modification is exactly the property [FrozenControl] argues is unauditable, and open-sourcing requirements make auditability a practical concern for ARC Prize eligibility; the reported evaluation is on maths and agent benchmarks rather than long-horizon interactive tasks.
- **Relevance to this FYP (1–5) and why:** **4.** It is the missing link in the §1 lineage — the first peer-reviewed LLM-era system to take the Gödel machine's self-reference literally, sitting between [ADAS] (meta agent writes agent) and [DGM] (archive plus validation). It is also the one entry that reports **efficiency** as an improvement axis alongside performance, which is the axis ARC-AGI-3 scores.
- **Reusable structure:** Runtime self-modification driven only by a high-level objective — the minimal-specification end of the design space, useful to the FYP as the *upper bound on freedom* against which a constrained, auditable variant ([FrozenControl]) can be compared.
- **BibTeX:** 

```bibtex
@misc{yin2024del,
  title         = {{Gödel Agent: A Self-Referential Agent Framework for Recursive Self-Improvement}},
  author        = {Yin, Xunjian and Wang, Xinyi and Pan, Liangming and Lin, Li and Wan, Xiaojun and Wang, William Yang},
  year          = {2024},
  eprint        = {2410.04444},
  archivePrefix = {arXiv},
  primaryClass  = {cs.AI},
  url           = {https://arxiv.org/abs/2410.04444}
}
```

### [SICA] — A Self-Improving Coding Agent
- **Authors / Year / Venue:** Maxime Robeyns, Martin Szummer, Laurence Aitchison / 2025 / arXiv preprint (submitted to NeurIPS 2025 per the record's comment field).
- **Link:** arXiv:2504.15228
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2504.15228.json`).
- **Type:** method
- **Problem:** Whether a single agent system, with nothing but ordinary coding tools, can edit its own orchestration code and thereby improve its own benchmark performance.
- **Method:** The agent system is the code that orchestrates LLM calls and exposes tools. SICA is given those same tools pointed at its own source, and runs a loop: benchmark itself, reflect on failures, edit its own implementation, re-benchmark. There is no separate meta agent and no population — it is a single self-editing lineage, which makes it the minimal instance of the [DGM] idea. Learning is non-gradient: the "update" is a code diff produced by reflection.
- **Verification signal:** executable check — SWE-bench Verified subset, LiveCodeBench, and synthetically generated agent benchmarks.
- **What changes:** scaffold code.
- **Results that matter:** 17% → 53% on a random subset of SWE-bench Verified, with further gains on LiveCodeBench. The authors characterise the mechanism as a "data-efficient, non gradient-based learning mechanism".
- **Limitations / criticisms:** Single-lineage search is path-dependent — the failure mode [DarwinX] names explicitly; a random SWE-bench Verified subset is a small and noisy evaluation; no cross-model transfer study.
- **Relevance to this FYP (1–5) and why:** **4.** The most economical version of the mechanism, and therefore the most realistic to reproduce on an FYP compute budget. It is also the natural *ablation baseline* for any archive-based method: single lineage vs archive.
- **Reusable structure:** The minimal self-edit loop (benchmark → reflect → patch own code → re-benchmark) as the FYP's simplest self-improvement arm.
- **BibTeX:** 

```bibtex
@misc{robeyns2025selfimproving,
  title         = {{A Self-Improving Coding Agent}},
  author        = {Robeyns, Maxime and Szummer, Martin and Aitchison, Laurence},
  year          = {2025},
  eprint        = {2504.15228},
  archivePrefix = {arXiv},
  primaryClass  = {cs.AI},
  url           = {https://arxiv.org/abs/2504.15228}
}
```

### [LiveSWE] — Live-SWE-agent: Can Software Engineering Agents Self-Evolve on the Fly?
- **Authors / Year / Venue:** Chunqiu Steven Xia, Zhe Wang, Yan Yang, Yuxiang Wei, Lingming Zhang / 2025 / arXiv preprint.
- **Link:** arXiv:2511.13646
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2511.13646.json`).
- **Type:** method
- **Problem:** Offline self-improvement ([DGM]-style) needs a costly training phase against a specific benchmark and may not transfer; can scaffold evolution instead happen *during* deployment?
- **Method:** Live-SWE-agent starts from the most basic possible scaffold — bash tools only, in the style of mini-SWE-agent — and evolves its own scaffold implementation on the fly while solving real problems, with no offline training run and no benchmark-specific tuning phase. The distinction from [DGM]/[SICA] is temporal: improvement is amortised into the deployment trajectory rather than paid for up front.
- **Verification signal:** executable check — SWE-bench Verified and SWE-Bench Pro solve rates.
- **What changes:** scaffold code, continuously, at runtime.
- **Results that matter:** 77.4% on SWE-bench Verified without test-time scaling, reported as better than all existing software agents including the best proprietary solution at the time; 45.8% on SWE-Bench Pro, reported as best known.
- **Limitations / criticisms:** Headline numbers depend on a strong frontier backbone, so the harness contribution is not cleanly separated from model capability; "on-the-fly" evolution means the artefact evaluated is not fixed, which complicates reproducibility — the exact concern [HarnessEvo] raises about harness churn.
- **Relevance to this FYP (1–5) and why:** **4.** ARC-AGI-3 scoring is per-level and efficiency-weighted, so an agent that improves its scaffold *within* an evaluation run converts learning into score directly. Live evolution is also the only variant compatible with a no-internet, single-submission Kaggle sandbox.
- **Reusable structure:** The "start from the most basic scaffold and let it grow" experimental design — a clean way to show that measured gains come from the loop rather than from a hand-tuned starting harness.
- **BibTeX:** 

```bibtex
@misc{xia2025livesweagent,
  title         = {{Live-SWE-agent: Can Software Engineering Agents Self-Evolve on the Fly?}},
  author        = {Xia, Chunqiu Steven and Wang, Zhe and Yang, Yan and Wei, Yuxiang and Zhang, Lingming},
  year          = {2025},
  eprint        = {2511.13646},
  archivePrefix = {arXiv},
  primaryClass  = {cs.SE},
  url           = {https://arxiv.org/abs/2511.13646}
}
```

### [DarwinX] — DarwinX: Evolving Agent Harnesses Through Natural Selection
- **Authors / Year / Venue:** Yifan Zhang, Yutong Dai, Juntao Tan, Luyu Yang, Rishi Mullur, Thai Hoang, Zhiyuan Hu, James Zhu, et al. (12 authors) / 2026 / arXiv preprint.
- **Link:** arXiv:2608.07545
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2608.07545.json`).
- **Type:** method
- **Problem:** Single-lineage self-improvement is path-dependent, and a local win often regresses other tasks; the paper treats harness improvement as population-level selection instead.
- **Method:** DarwinX evolves a *population* of harnesses with the model frozen. Three components carry the design: a **preserve-and-extend contract** that admits a variant only if it extends coverage without regressing existing coverage; an **archive** that keeps alternative lineages available for recombination; and a single edit interface through which failure-derived, teacher-derived and self-derived evidence all flow. Fitness is taken from each benchmark's own verifier, with no gold solutions and no hand-picked winners.
- **Verification signal:** executable check — each benchmark's native verifier.
- **What changes:** scaffold code (prompts, tools, skills, control flow), selected over a population; weights frozen.
- **Results that matter:** ~17 points average gain from one loop across four benchmarks; Terminal-Bench 2.1 +7.7 to 83.2% on a matched base and 84.7% on a stronger one; WebArena-Infinity real-task pass@1 43.5% → 93.0%; a Terminal-Bench harness transfers unchanged to SWE-bench Verified.
- **Limitations / criticisms:** A 2026 preprint with no visible peer-review record on the arXiv metadata; the WebArena-Infinity jump is very large and rests on the authors' own "audit-clean" protocol; the benchmarks that "progressively separate the evolution signal from the test" are the authors' own construction.
- **Relevance to this FYP (1–5) and why:** **5.** This is the strongest published statement of exactly the FYP's thesis — the paper's own framing is that a frozen model need not be a fixed agent. The preserve-and-extend contract is the direct answer to the regression problem an ARC-AGI-3 harness will hit when a fix for one game breaks another.
- **Reusable structure:** The preserve-and-extend admission rule (accept only non-regressing coverage extensions) and the benchmark-suite design that separates the evolution signal from the test set — both should be copied into the FYP's evaluation protocol.
- **BibTeX:** 

```bibtex
@misc{zhang2026darwinx,
  title         = {{DarwinX: Evolving Agent Harnesses Through Natural Selection}},
  author        = {Zhang, Yifan and Dai, Yutong and Tan, Juntao and Yang, Luyu and Mullur, Rishi and Hoang, Thai and Hu, Zhiyuan and Zhu, James and Mui, Phil and Savarese, Silvio and Xu, Ran and Chen, Zeyuan},
  year          = {2026},
  eprint        = {2608.07545},
  archivePrefix = {arXiv},
  primaryClass  = {cs.NE},
  url           = {https://arxiv.org/abs/2608.07545}
}
```

### [AlphaEvolve] — AlphaEvolve: A coding agent for scientific and algorithmic discovery
- **Authors / Year / Venue:** Alexander Novikov, Ngân Vũ, Marvin Eisenberger, Emilien Dupont, Po-Sen Huang, Adam Zsolt Wagner, Sergey Shirobokov, Borislav Kozlovskii, et al. (18 authors) / 2025 / arXiv white paper (Google DeepMind).
- **Link:** arXiv:2506.13131
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2506.13131.json`); the record self-describes as a white paper.
- **Type:** method / empirical study
- **Problem:** Using an LLM inside an evolutionary loop to discover algorithms that beat the best known human solutions.
- **Method:** An autonomous pipeline of LLMs proposes direct edits to a program; one or more evaluators score each candidate; the evolutionary loop keeps improving the program. What is optimised is the *artefact* (the algorithm's code), not the agent's own harness — which is why it sits at the boundary of this topic. It is included because the loop structure (LLM mutation + programmatic evaluator + population) is identical to the harness-evolution loop and because it is the strongest demonstration that this loop can produce genuinely novel output.
- **Verification signal:** executable check — programmatic evaluators, including provable correctness for the mathematical results.
- **What changes:** the target program's code (an artefact), via an evolutionary population.
- **Results that matter:** A search procedure found by AlphaEvolve multiplies two 4×4 complex matrices in 48 scalar multiplications — the first improvement over Strassen's algorithm in that setting in 56 years; deployed results include a more efficient data-centre scheduling algorithm and a speed-up of the training of the LLM underpinning AlphaEvolve itself.
- **Limitations / criticisms:** White paper, not peer-reviewed; results come from very large compute budgets unavailable to an FYP; the recursive claim (accelerating its own training) is a compute-efficiency gain, not a demonstration of recursive capability gain.
- **Relevance to this FYP (1–5) and why:** **3.** The mechanism transfers (evolve code against a mechanical evaluator) but the scale does not. Its main use is as the existence proof that verifier-driven evolutionary search over code can exceed its own proposer's prior knowledge — the claim Topic 3's elicitation-vs-acquisition argument has to engage with.
- **Reusable structure:** The evaluator-cascade design (cheap filters before expensive evaluation) is directly applicable to an ARC-AGI-3 loop, where full-game rollouts are the expensive step.
- **BibTeX:** 

```bibtex
@misc{novikov2025alphaevolve,
  title         = {{AlphaEvolve: A coding agent for scientific and algorithmic discovery}},
  author        = {Novikov, Alexander and Vũ, Ngân and Eisenberger, Marvin and Dupont, Emilien and Huang, Po-Sen and Wagner, Adam Zsolt and Shirobokov, Sergey and Kozlovskii, Borislav and Ruiz, Francisco J. R. and Mehrabian, Abbas and Kumar, M. Pawan and See, Abigail and Chaudhuri, Swarat and Holland, George and Davies, Alex and Nowozin, Sebastian and Kohli, Pushmeet and Balog, Matej},
  year          = {2025},
  eprint        = {2506.13131},
  archivePrefix = {arXiv},
  primaryClass  = {cs.AI},
  url           = {https://arxiv.org/abs/2506.13131}
}
```

### [AFlow] — AFlow: Automating Agentic Workflow Generation
- **Authors / Year / Venue:** Jiayi Zhang, Jinyu Xiang, Zhaoyang Yu, Fengwei Teng, Xionghui Chen, Jiaqi Chen, Mingchen Zhuge, Xin Cheng, et al. (14 authors) / 2024 (v4 2025-04) / ICLR 2025 (venue confirmed via Semantic Scholar record: "International Conference on Learning Representations"; 351 citations at time of retrieval).
- **Link:** arXiv:2410.10762
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2410.10762.json`).
- **Type:** method
- **Problem:** Agentic workflows are hand-built; prior automation still needed manual setup.
- **Method:** Workflow optimisation is reformulated as search over *code-represented* workflows — a graph whose nodes are LLM invocations and whose edges are control flow. AFlow explores this space with Monte Carlo Tree Search, refining workflows by code modification and using execution feedback plus a tree-structured record of previous attempts to guide expansion. The model is fixed; only the workflow graph changes.
- **Verification signal:** executable check — task-level execution feedback on six benchmark datasets.
- **What changes:** scaffold code (the workflow graph).
- **Results that matter:** 5.7% average improvement over state-of-the-art baselines across six datasets; workflows found for smaller models let them outperform GPT-4o on specific tasks at 4.55% of GPT-4o's dollar inference cost.
- **Limitations / criticisms:** Gains are modest compared with the self-modifying-agent line; MCTS over workflows needs many evaluations, which is expensive when each evaluation is a full agent rollout; the cost-parity claim is task-specific.
- **Relevance to this FYP (1–5) and why:** **4.** The cost result is the important one for this project: scaffold search is a way to buy capability for a *small* model, which is the FYP's stated regime. MCTS over a discrete scaffold space is also directly implementable at FYP scale.
- **Reusable structure:** MCTS-over-scaffold-graph as a search algorithm, and the cost-normalised comparison (score per dollar / per rollout) as a reporting format — the closest analogue in the literature to ARC-AGI-3's efficiency-normalised scoring.
- **BibTeX:** 

```bibtex
@misc{zhang2024aflow,
  title         = {{AFlow: Automating Agentic Workflow Generation}},
  author        = {Zhang, Jiayi and Xiang, Jinyu and Yu, Zhaoyang and Teng, Fengwei and Chen, Xionghui and Chen, Jiaqi and Zhuge, Mingchen and Cheng, Xin and Hong, Sirui and Wang, Jinlin and Zheng, Bingnan and Liu, Bang and Luo, Yuyu and Wu, Chenglin},
  year          = {2024},
  eprint        = {2410.10762},
  archivePrefix = {arXiv},
  primaryClass  = {cs.AI},
  url           = {https://arxiv.org/abs/2410.10762}
}
```
---

## §2 The scaffold as an optimisation problem: prompts, contexts, pipelines

### [Promptbreeder] — Promptbreeder: Self-Referential Self-Improvement Via Prompt Evolution
- **Authors / Year / Venue:** Chrisantha Fernando, Dylan Banarse, Henryk Michalewski, Simon Osindero, Tim Rocktäschel / 2023 / ICML (venue confirmed via Semantic Scholar record; 589 citations at time of retrieval).
- **Link:** arXiv:2309.16797
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2309.16797.json`).
- **Type:** method
- **Problem:** Hand-crafted prompting strategies such as chain-of-thought are fixed and therefore sub-optimal for any specific domain.
- **Method:** An LLM mutates a population of task-prompts, which are then scored for fitness on a training set. The self-referential twist is the second level: the *mutation-prompts* that govern how task-prompts are mutated are themselves generated and evolved by the same LLM. So the system improves both the solutions and its own operator for producing solutions — a text-space analogue of the Gödel machine's self-reference, with fitness replacing proof.
- **Verification signal:** environment/benchmark score on a training set (no executable verifier).
- **What changes:** context/prompt, at two levels (task-prompts and the mutation-prompts that edit them).
- **Results that matter:** Reported to outperform chain-of-thought and Plan-and-Solve prompting on standard arithmetic and commonsense reasoning benchmarks, and to evolve usable task-prompts for hate-speech classification. The abstract gives no single headline number, so no specific figure is quoted here.
- **Limitations / criticisms:** Fitness is measured on a training split, so gains partly reflect fitting the evaluation prompt to that split; the search is expensive in LLM calls; later work ([GEPA]) argues that reflective, feedback-carrying mutation is far more sample-efficient than blind evolutionary mutation.
- **Relevance to this FYP (1–5) and why:** **4.** Two-level self-reference (improve the thing, and improve the improver) is exactly the structure the FYP's teacher needs if the teacher itself is to get better rather than merely produce more environments. It is also the cheapest possible instantiation of self-improvement — no weights, no code, only text.
- **Reusable structure:** The two-level population design (artefacts + operators evolved together), directly transplantable to "evolve the ARC-AGI-3 agent's strategy prompt, and evolve the prompt that proposes strategy edits".
- **BibTeX:** 

```bibtex
@misc{fernando2023promptbreeder,
  title         = {{Promptbreeder: Self-Referential Self-Improvement Via Prompt Evolution}},
  author        = {Fernando, Chrisantha and Banarse, Dylan and Michalewski, Henryk and Osindero, Simon and Rocktäschel, Tim},
  year          = {2023},
  eprint        = {2309.16797},
  archivePrefix = {arXiv},
  primaryClass  = {cs.CL},
  url           = {https://arxiv.org/abs/2309.16797}
}
```

### [EvoPrompt] — EvoPrompt: Connecting LLMs with Evolutionary Algorithms Yields Powerful Prompt Optimizers
- **Authors / Year / Venue:** Qingyan Guo, Rui Wang, Junliang Guo, Bei Li, Kaitao Song, Xu Tan, Guoqing Liu, Jiang Bian, et al. (9 authors) / 2023 (v3 2025) / ICLR 2024 (venue stated on the arXiv record).
- **Link:** arXiv:2309.08532
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2309.08532.json`); the comment field states ICLR 2024.
- **Type:** method
- **Problem:** Discrete prompt optimisation without gradients or parameter access.
- **Method:** EvoPrompt runs a standard evolutionary algorithm — population, crossover, mutation, selection on a development set — but delegates the genetic operators to an LLM, so that offspring remain coherent natural language rather than token soup. No gradients and no parameters are touched anywhere in the loop; the only state is the prompt population and its dev-set scores.
- **Verification signal:** environment/benchmark score on a development set.
- **What changes:** context/prompt.
- **Results that matter:** Evaluated on 31 datasets across understanding, generation and BIG-Bench Hard; reported to beat human-engineered prompts and prior automatic prompt generation methods by up to 25% on BBH.
- **Limitations / criticisms:** Requires a labelled dev set, which an unlabelled interactive benchmark does not provide; dev-set overfitting is a live risk at 31-dataset scale; gains are prompt-level only and do not compound into new capabilities.
- **Relevance to this FYP (1–5) and why:** **3.** The mechanism transfers only if a dev-set analogue exists. For ARC-AGI-3 the closest analogue is the public game set, which is small (the public/private ratio is roughly 1:5), so this method's main lesson for the FYP is a *warning* about how easily a scaffold overfits a small public split.
- **Reusable structure:** The LLM-as-genetic-operator trick (keeps candidates well-formed), and the dev/test separation discipline that the FYP needs in order to claim generalisation to private games.
- **BibTeX:** 

```bibtex
@misc{guo2023evoprompt,
  title         = {{EvoPrompt: Connecting LLMs with Evolutionary Algorithms Yields Powerful Prompt Optimizers}},
  author        = {Guo, Qingyan and Wang, Rui and Guo, Junliang and Li, Bei and Song, Kaitao and Tan, Xu and Liu, Guoqing and Bian, Jiang and Yang, Yujiu},
  year          = {2023},
  eprint        = {2309.08532},
  archivePrefix = {arXiv},
  primaryClass  = {cs.CL},
  url           = {https://arxiv.org/abs/2309.08532}
}
```

### [OPRO] — Large Language Models as Optimizers
- **Authors / Year / Venue:** Chengrun Yang, Xuezhi Wang, Yifeng Lu, Hanxiao Liu, Quoc V. Le, Denny Zhou, Xinyun Chen / 2023 (v3 2024) / ICLR 2024 (venue stated on the arXiv record).
- **Link:** arXiv:2309.03409
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2309.03409.json`); the comment field states ICLR 2024.
- **Type:** method
- **Problem:** Optimisation where no gradient is available and the objective is described in natural language.
- **Method:** The optimisation trajectory is kept *in the prompt*: at each step, the LLM is shown previously generated solutions together with their measured scores, and asked to propose new ones; the new solutions are evaluated and appended. The paper demonstrates the idea on linear regression and TSP before applying it to prompt optimisation. The "optimiser state" is literally context, which makes this the purest example of learning that lives entirely in the context window.
- **Verification signal:** environment/benchmark score (task accuracy).
- **What changes:** context/prompt (the solution trajectory in context is the optimiser's memory).
- **Results that matter:** Optimised instructions beat human-designed prompts by up to 8% on GSM8K and by up to 50% on Big-Bench Hard tasks.
- **Limitations / criticisms:** Needs many scored evaluations per step; performance is sensitive to how the trajectory is formatted; the BBH figure is a best case over tasks, not an average.
- **Relevance to this FYP (1–5) and why:** **4.** "Show the model its own past attempts with their scores and ask for a better one" is a general recipe that maps onto ARC-AGI-3 directly, where each attempt has a scalar efficiency score. [MetaEvolve] (Topic 2) trains this same behaviour into the weights; OPRO shows it works without training at all, which makes it the cheap baseline.
- **Reusable structure:** The score-annotated trajectory-in-context format — this is the exact prompt structure the FYP should use for its inference-time refinement baseline.
- **BibTeX:** 

```bibtex
@misc{yang2023large,
  title         = {{Large Language Models as Optimizers}},
  author        = {Yang, Chengrun and Wang, Xuezhi and Lu, Yifeng and Liu, Hanxiao and Le, Quoc V. and Zhou, Denny and Chen, Xinyun},
  year          = {2023},
  eprint        = {2309.03409},
  archivePrefix = {arXiv},
  primaryClass  = {cs.LG},
  url           = {https://arxiv.org/abs/2309.03409}
}
```

### [DSPy] — DSPy: Compiling Declarative Language Model Calls into Self-Improving Pipelines
- **Authors / Year / Venue:** Omar Khattab, Arnav Singhvi, Paridhi Maheshwari, Zhiyuan Zhang, Keshav Santhanam, Sri Vardhamanan, Saiful Haq, Ashutosh Sharma, et al. (13 authors) / 2023 / arXiv preprint (no venue on the record).
- **Link:** arXiv:2310.03714
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2310.03714.json`).
- **Type:** method
- **Problem:** LM pipelines are built from hard-coded prompt strings found by trial and error; there is no systematic way to optimise them.
- **Method:** DSPy models a pipeline as a text-transformation graph in which LMs are called through declarative *modules* with typed signatures. Modules are parameterised — they can learn which demonstrations to include and which prompting/finetuning strategy to apply — and a compiler optimises the whole pipeline against a user-supplied metric, typically by bootstrapping demonstrations from the pipeline's own successful runs. The prompt strings become compiler output rather than source code.
- **Verification signal:** a user-supplied metric (task accuracy); for the bootstrapping step, the pipeline's own successful traces.
- **What changes:** context/prompt (demonstrations and instructions) and, optionally, weights via finetuning — the paper covers both, so it straddles the taxonomy.
- **Results that matter:** Compiled programs beat standard few-shot prompting by over 25% (GPT-3.5) and 65% (llama2-13b-chat), and beat expert-written demonstration pipelines by up to 5–46% and 16–40% respectively; compiled small models (770M T5, llama2-13b) are reported competitive with expert-written prompt chains on proprietary GPT-3.5.
- **Limitations / criticisms:** Needs a metric and a training set; the "self-improving" label refers to compile-time bootstrapping, not to runtime adaptation; comparisons are against prompting baselines rather than against trained agents.
- **Relevance to this FYP (1–5) and why:** **3.** The small-model result matters — it is direct evidence that scaffold compilation buys capability specifically where the model is weak, which is the FYP's regime. The mechanism itself (bootstrap demonstrations from successful traces) needs an ARC-AGI-3-shaped notion of "demonstration", which is a non-trivial design step.
- **Reusable structure:** Bootstrapped demonstration selection from the agent's own successful rollouts — the natural way to turn solved ARC-AGI-3 levels into in-context exemplars for unsolved ones.
- **BibTeX:** 

```bibtex
@misc{khattab2023dspy,
  title         = {{DSPy: Compiling Declarative Language Model Calls into Self-Improving Pipelines}},
  author        = {Khattab, Omar and Singhvi, Arnav and Maheshwari, Paridhi and Zhang, Zhiyuan and Santhanam, Keshav and Vardhamanan, Sri and Haq, Saiful and Sharma, Ashutosh and Joshi, Thomas T. and Moazam, Hanna and Miller, Heather and Zaharia, Matei and Potts, Christopher},
  year          = {2023},
  eprint        = {2310.03714},
  archivePrefix = {arXiv},
  primaryClass  = {cs.CL},
  url           = {https://arxiv.org/abs/2310.03714}
}
```

### [TextGrad] — TextGrad: Automatic "Differentiation" via Text
- **Authors / Year / Venue:** Mert Yuksekgonul, Federico Bianchi, Joseph Boen, Sheng Liu, Zhi Huang, Carlos Guestrin, James Zou / 2024 / arXiv preprint (no venue on the record).
- **Link:** arXiv:2406.07496
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2406.07496.json`).
- **Type:** method
- **Problem:** Compound AI systems have many text-valued components and no general way to optimise them jointly.
- **Method:** TextGrad treats natural-language feedback as a gradient. A computation graph is built over text variables (prompts, code, molecules, plans); an LLM criticises the output; the criticism is back-propagated through the graph as textual "gradients", and each variable is updated by an LLM that reads its incoming feedback. The API deliberately mirrors PyTorch, so the same optimiser abstraction covers very different variable types.
- **Verification signal:** varies by task — learned/LLM feedback for open-ended tasks, executable or simulation checks for code and molecules.
- **What changes:** context/prompt and other text artefacts (code, plans), never weights.
- **Results that matter:** GPT-4o zero-shot GPQA accuracy 51% → 55%; 20% relative gain on LeetCode-Hard solutions; further demonstrations in molecule design and radiotherapy plan optimisation.
- **Limitations / criticisms:** Where feedback comes from an LLM rather than an executable check, the "gradient" can be confidently wrong; [TextPolicies] shows the approach degrades sharply in the agent setting, where feedback arrives only after a whole action sequence and credit assignment becomes the bottleneck.
- **Relevance to this FYP (1–5) and why:** **4.** ARC-AGI-3 is exactly the hard case: reward arrives at the end of a long action sequence. TextGrad is the method the FYP would reach for, and [TextPolicies] is the evidence that it will not work out of the box — together they define a concrete open problem the project can attack.
- **Reusable structure:** The textual-gradient abstraction, and (more usefully) its documented failure boundary as a baseline to beat.
- **BibTeX:** 

```bibtex
@misc{yuksekgonul2024textgrad,
  title         = {{TextGrad: Automatic "Differentiation" via Text}},
  author        = {Yuksekgonul, Mert and Bianchi, Federico and Boen, Joseph and Liu, Sheng and Huang, Zhi and Guestrin, Carlos and Zou, James},
  year          = {2024},
  eprint        = {2406.07496},
  archivePrefix = {arXiv},
  primaryClass  = {cs.CL},
  url           = {https://arxiv.org/abs/2406.07496}
}
```

### [GEPA] — GEPA: Reflective Prompt Evolution Can Outperform Reinforcement Learning
- **Authors / Year / Venue:** Lakshya A Agrawal, Shangyin Tan, Dilara Soylu, Noah Ziems, Rishi Khare, Krista Opsahl-Ong, Arnav Singhvi, Herumb Shandilya, et al. (17 authors) / 2025 (v2 2026-02) / ICLR 2026 (Oral) — stated on the arXiv record.
- **Link:** arXiv:2507.19457
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2507.19457.json`); the comment field states "Accepted to ICLR 2026 (Oral)".
- **Type:** method
- **Problem:** RL post-training (e.g. GRPO) needs thousands of rollouts because a scalar reward is a very thin learning signal.
- **Method:** GEPA samples full trajectories — reasoning, tool calls, tool outputs — and reflects on them *in natural language* to diagnose what went wrong, then proposes and tests prompt edits. It keeps a Pareto frontier of its own attempts and recombines complementary lessons from different frontier members rather than following a single best-so-far. The argument is that language is a richer learning medium than a scalar, so each rollout carries far more usable information.
- **Verification signal:** environment/benchmark score, with the trajectory text as the diagnostic channel.
- **What changes:** context/prompt.
- **Results that matter:** Outperforms GRPO by 6% on average and up to 20% across six tasks while using **up to 35× fewer rollouts**; beats MIPROv2 by over 10% (e.g. +12% accuracy on AIME-2025).
- **Limitations / criticisms:** Compares against one RL algorithm at a fixed budget; reflection quality depends on a strong backbone model; [TextPolicies] reports that iterative GEPA search failed to reliably produce useful *agent* policies from trajectories, so the sample-efficiency claim may not carry to long-horizon control.
- **Relevance to this FYP (1–5) and why:** **5.** The rollout-efficiency argument is decisive for this project: ARC-AGI-3 rollouts are expensive and the score punishes wasted actions, so a method that extracts 35× more value per rollout than RL is the right default. This is the single strongest "scaffold beats weights, at small budget" result in the corpus.
- **Reusable structure:** Pareto-frontier candidate selection (instead of greedy best-so-far), and rollout-count as the x-axis of the comparison — the FYP should report score-vs-rollouts curves in exactly this form.
- **BibTeX:** 

```bibtex
@misc{agrawal2025gepa,
  title         = {{GEPA: Reflective Prompt Evolution Can Outperform Reinforcement Learning}},
  author        = {Agrawal, Lakshya A and Tan, Shangyin and Soylu, Dilara and Ziems, Noah and Khare, Rishi and Opsahl-Ong, Krista and Singhvi, Arnav and Shandilya, Herumb and Ryan, Michael J and Jiang, Meng and Potts, Christopher and Sen, Koushik and Dimakis, Alexandros G. and Stoica, Ion and Klein, Dan and Zaharia, Matei and Khattab, Omar},
  year          = {2025},
  eprint        = {2507.19457},
  archivePrefix = {arXiv},
  primaryClass  = {cs.CL},
  url           = {https://arxiv.org/abs/2507.19457},
  note          = {Accepted to ICLR 2026 (Oral)}
}
```

### [MCE] — Meta Context Engineering via Agentic Skill Evolution
- **Authors / Year / Venue:** Haoran Ye, Xuning He, Vincent Arak, Haonan Dong, Guojie Song / 2026 / arXiv preprint (record comment: 46 pages, 4 figures).
- **Link:** arXiv:2601.21557
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2601.21557.json`).
- **Type:** method
- **Problem:** Context-engineering methods rely on hand-built harnesses — fixed generation–reflection workflows and predefined context schemas — which restrict the search to a narrow, intuition-bound design space.
- **Method:** MCE is a bi-level loop. A meta-level agent refines *context-engineering skills* through "agentic crossover", a deliberative search over the history of skills, their executions and their evaluations. A base-level agent executes those skills, learns from training rollouts, and optimises the context itself as flexible files and code. So the object being evolved is not a prompt but the *procedure that writes prompts and context artefacts*.
- **Verification signal:** environment/benchmark score, in both offline and online settings.
- **What changes:** scaffold code (the skills) and context/prompt (the artefacts they produce).
- **Results that matter:** 5.6–53.8% relative improvement over state-of-the-art agentic context-engineering methods across five domains, mean 16.9%, with reported gains in context-usage efficiency and transferability.
- **Limitations / criticisms:** Wide result range suggests strong domain dependence; the baselines are themselves recent and unstandardised; no peer-review record on the arXiv metadata.
- **Relevance to this FYP (1–5) and why:** **4.** Bi-level structure — a meta agent improving the improver — is the same shape as the FYP's teacher/student split, but applied to harness artefacts instead of tasks. It is the clearest demonstration that the *skill of engineering context* can itself be the object of search.
- **Reusable structure:** The bi-level meta/base decomposition with an explicit history of (skill, execution, evaluation) triples as the meta agent's search substrate.
- **BibTeX:** 

```bibtex
@misc{ye2026meta,
  title         = {{Meta Context Engineering via Agentic Skill Evolution}},
  author        = {Ye, Haoran and He, Xuning and Arak, Vincent and Dong, Haonan and Song, Guojie},
  year          = {2026},
  eprint        = {2601.21557},
  archivePrefix = {arXiv},
  primaryClass  = {cs.AI},
  url           = {https://arxiv.org/abs/2601.21557}
}
```

---

## §3 Accumulation: tools, skills, workflows and experience as the substrate

### [Voyager] — Voyager: An Open-Ended Embodied Agent with Large Language Models
- **Authors / Year / Venue:** Guanzhi Wang, Yuqi Xie, Yunfan Jiang, Ajay Mandlekar, Chaowei Xiao, Yuke Zhu, Linxi Fan, Anima Anandkumar / 2023 / arXiv preprint (no venue on the record).
- **Link:** arXiv:2305.16291
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2305.16291.json`).
- **Type:** method
- **Problem:** Lifelong learning in an open-ended environment (Minecraft) without fine-tuning the model.
- **Method:** Three components: an automatic curriculum that proposes what to attempt next in order to maximise exploration; an ever-growing **skill library** of executable code, where each skill is a verified program stored for retrieval and composition; and an iterative prompting loop that feeds environment feedback, execution errors and self-verification back into program generation until the skill runs. GPT-4 is queried as a black box — explicitly no parameter updates — so everything learned lives in the skill library.
- **Verification signal:** executable check (the skill program must run in the environment) plus environment feedback and an LLM self-verification module.
- **What changes:** memory / skill library (executable code artefacts), and the task distribution via the automatic curriculum.
- **Results that matter:** 3.3× more unique items, 2.3× longer distances travelled, and tech-tree milestones unlocked up to 15.3× faster than the prior state of the art; the learned library transfers to a fresh Minecraft world where baselines fail to generalise.
- **Limitations / criticisms:** Minecraft has a rich text prior in the pretraining data — the agent's "exploration" is partly recall of documented game mechanics, which is precisely the confound ARC-AGI-3 is designed to remove; self-verification is an LLM judge, with the bias problems [BlindCurator] later formalises.
- **Relevance to this FYP (1–5) and why:** **5.** Voyager is the archetype of the FYP's target system: curriculum + skill library + frozen weights in an interactive environment. The essential question this project inherits is whether the mechanism survives when the environment has *no* language prior — Voyager's own results cannot answer that, which is exactly why ARC-AGI-3 is the interesting test.
- **Reusable structure:** The skill-library design (executable, retrievable, compositional, admitted only after passing an execution check) and the cross-world transfer protocol.
- **BibTeX:** 

```bibtex
@misc{wang2023voyager,
  title         = {{Voyager: An Open-Ended Embodied Agent with Large Language Models}},
  author        = {Wang, Guanzhi and Xie, Yuqi and Jiang, Yunfan and Mandlekar, Ajay and Xiao, Chaowei and Zhu, Yuke and Fan, Linxi and Anandkumar, Anima},
  year          = {2023},
  eprint        = {2305.16291},
  archivePrefix = {arXiv},
  primaryClass  = {cs.AI},
  url           = {https://arxiv.org/abs/2305.16291}
}
```

### [LATM] — Large Language Models as Tool Makers
- **Authors / Year / Venue:** Tianle Cai, Xuezhi Wang, Tengyu Ma, Xinyun Chen, Denny Zhou / 2023 (v2 2024) / arXiv preprint (no venue on the record).
- **Link:** arXiv:2305.17126
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2305.17126.json`).
- **Type:** method
- **Problem:** Agents are usually given a fixed tool set; the paper asks whether they can manufacture their own reusable tools.
- **Method:** A closed loop with two roles. A powerful, expensive **tool maker** writes a reusable tool (a Python function with an API) for a class of tasks; a cheap **tool user** then applies that cached tool to individual instances. Because the tool is cached and reused, the one-off cost of tool making amortises across many uses — the paper frames this as a *functional* cache, storing the capability rather than the answer.
- **Verification signal:** executable check (the tool is run) plus task accuracy on the class of problems.
- **What changes:** scaffold code / tools, and memory (the tool cache).
- **Results that matter:** With GPT-4 as tool maker and GPT-3.5 as tool user, LATM matches GPT-4-for-both-roles performance on complex reasoning tasks including Big-Bench, at significantly reduced average inference cost.
- **Limitations / criticisms:** Tools are only reusable when tasks come in recognisable classes; the maker/user asymmetry presumes access to a stronger model, which a no-internet evaluation sandbox may not allow; no study of what happens as the tool cache grows large — the gap [LibraryDrift] later fills.
- **Relevance to this FYP (1–5) and why:** **4.** The maker/user split maps cleanly onto ARC-AGI-3's structure: expensive analysis on early levels of a game produces tools that cheap execution reuses on later levels of the same game — and because the score is action-efficiency, reuse is worth more here than in a pass/fail benchmark.
- **Reusable structure:** The functional-cache framing and the strong-maker/cheap-user cost decomposition; a natural ablation axis (tool reuse on vs off) for the results chapter.
- **BibTeX:** 

```bibtex
@misc{cai2023large,
  title         = {{Large Language Models as Tool Makers}},
  author        = {Cai, Tianle and Wang, Xuezhi and Ma, Tengyu and Chen, Xinyun and Zhou, Denny},
  year          = {2023},
  eprint        = {2305.17126},
  archivePrefix = {arXiv},
  primaryClass  = {cs.LG},
  url           = {https://arxiv.org/abs/2305.17126}
}
```

### [ExpeL] — ExpeL: LLM Agents Are Experiential Learners
- **Authors / Year / Venue:** Andrew Zhao, Daniel Huang, Quentin Xu, Matthieu Lin, Yong-Jin Liu, Gao Huang / 2023 (v3 2024) / AAAI-24 (venue stated on the arXiv record).
- **Link:** arXiv:2308.10144
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2308.10144.json`); the comment field states acceptance at AAAI-24.
- **Type:** method
- **Problem:** Frontier models are API-only and fine-tuning is expensive, so agents need a way to learn from experience with no parametric update.
- **Method:** ExpeL runs over a set of training tasks, gathering trajectories; it then *extracts natural-language insights* from comparisons across those trajectories (successes vs failures) and stores them alongside the raw experiences. At inference it recalls both the distilled insights and relevant past trajectories to condition its decisions. The distinction from [Reflexion] is that insights are cross-task and persist, rather than being per-episode.
- **Verification signal:** environment reward on the training tasks (used to label trajectories as success/failure).
- **What changes:** memory (an experience pool plus a distilled insight set) and, at inference, the context.
- **Results that matter:** Performance rises consistently as experience accumulates; the paper reports transfer of extracted insights to related tasks. The abstract states no single headline figure, so none is quoted.
- **Limitations / criticisms:** Insight extraction is LLM-judged and unverified; the abstract's claims are qualitative, and later work ([TextPolicies]) finds that generating useful policy text from trajectories is precisely the step that fails to be reliable.
- **Relevance to this FYP (1–5) and why:** **4.** The FYP needs a persistent, weight-free store that carries lessons *across* ARC-AGI-3 games; ExpeL is the canonical design for that store, and its cross-task insight abstraction is the mechanism most likely to transfer between structurally similar games.
- **Reusable structure:** Cross-trajectory insight extraction (compare success and failure pairs, write the difference as a rule) plus retrieval at inference — with the caveat that the FYP should verify insights against replays rather than trusting the judge.
- **BibTeX:** 

```bibtex
@misc{zhao2023expel,
  title         = {{ExpeL: LLM Agents Are Experiential Learners}},
  author        = {Zhao, Andrew and Huang, Daniel and Xu, Quentin and Lin, Matthieu and Liu, Yong-Jin and Huang, Gao},
  year          = {2023},
  eprint        = {2308.10144},
  archivePrefix = {arXiv},
  primaryClass  = {cs.LG},
  url           = {https://arxiv.org/abs/2308.10144},
  note          = {Accepted by the 38th Annual AAAI Conference on Artificial Intelligence (AAAI-24)}
}
```

### [Reflexion] — Reflexion: Language Agents with Verbal Reinforcement Learning
- **Authors / Year / Venue:** Noah Shinn, Federico Cassano, Edward Berman, Ashwin Gopinath, Karthik Narasimhan, Shunyu Yao / 2023 / arXiv preprint (no venue on the record).
- **Link:** arXiv:2303.11366
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2303.11366.json`).
- **Type:** method
- **Problem:** Trial-and-error learning for language agents without the sample cost and fine-tuning of conventional RL.
- **Method:** After a failed attempt, the agent verbally reflects on the feedback signal and writes the reflection into an episodic memory buffer; subsequent trials are conditioned on that buffer. The feedback may be scalar or free-form, external or internally simulated. The authors frame the reflection text as the policy update — reinforcement carried in language rather than in parameters.
- **Verification signal:** whatever the task provides — unit tests for coding, environment reward for decision-making, self-evaluation for reasoning.
- **What changes:** memory (episodic reflection buffer) → context at the next trial.
- **Results that matter:** 91% pass@1 on HumanEval, against 80% for the then-state-of-the-art GPT-4 baseline; gains reported across sequential decision-making, coding and reasoning.
- **Limitations / criticisms:** Depends on a reliable failure signal — where the agent must judge its own correctness, [SelfCorrect] (Topic 3) shows intrinsic self-correction can make results worse; the memory is per-task and does not accumulate across tasks.
- **Relevance to this FYP (1–5) and why:** **4.** ARC-AGI-3 provides exactly the kind of feedback Reflexion needs (score changes, level transitions) without providing goals, so verbal reflection over replays is a natural fit — and reflection is cheap in actions, which matters when actions are the scoring denominator.
- **Reusable structure:** The reflect-and-retry loop as the FYP's minimum viable "learning" baseline, plus the ablation over feedback type (scalar vs free-form, external vs internal), which directly probes whether the environment signal or the model's own judgement is doing the work.
- **BibTeX:** 

```bibtex
@misc{shinn2023reflexion,
  title         = {{Reflexion: Language Agents with Verbal Reinforcement Learning}},
  author        = {Shinn, Noah and Cassano, Federico and Berman, Edward and Gopinath, Ashwin and Narasimhan, Karthik and Yao, Shunyu},
  year          = {2023},
  eprint        = {2303.11366},
  archivePrefix = {arXiv},
  primaryClass  = {cs.AI},
  url           = {https://arxiv.org/abs/2303.11366}
}
```

### [AWM] — Agent Workflow Memory
- **Authors / Year / Venue:** Zora Zhiruo Wang, Jiayuan Mao, Daniel Fried, Graham Neubig / 2024 / arXiv preprint (no venue on the record).
- **Link:** arXiv:2409.07429
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2409.07429.json`).
- **Type:** method
- **Problem:** Long-horizon agents fail on complex action trajectories; humans instead reuse routines learned from past experience.
- **Method:** AWM induces reusable *workflows* — commonly recurring action routines — from past trajectories, and selectively injects relevant workflows into the context to guide future generations. It works offline (induce from training examples) or online (induce from test queries on the fly), the latter requiring no training set at all. The unit of memory is a procedure, sitting between Reflexion's episodic text and Voyager's executable skills.
- **Verification signal:** environment reward (web-navigation task success).
- **What changes:** memory (workflow store) → context.
- **Results that matter:** +24.6% and +51.1% relative success rate on Mind2Web and WebArena respectively, with fewer steps taken on successful WebArena tasks; online AWM gains 8.9–14.0 absolute points over baselines as the train/test distribution gap widens.
- **Limitations / criticisms:** Web tasks are highly repetitive, which flatters routine induction; workflow retrieval quality degrades as the store grows, the failure mode [LibraryDrift] isolates.
- **Relevance to this FYP (1–5) and why:** **5.** Two things matter here. First, *online* induction with no training set is the only variant compatible with ARC-AGI-3's unseen private games. Second, AWM reduces the number of steps taken — under a squared action-efficiency metric, step reduction is worth more than success-rate gain, and this is one of the few papers that reports it.
- **Reusable structure:** Online workflow induction, and the widening-distribution-gap evaluation (report gains as a function of train/test similarity) — a good template for reporting public-vs-private ARC-AGI-3 transfer.
- **BibTeX:** 

```bibtex
@misc{wang2024agent,
  title         = {{Agent Workflow Memory}},
  author        = {Wang, Zora Zhiruo and Mao, Jiayuan and Fried, Daniel and Neubig, Graham},
  year          = {2024},
  eprint        = {2409.07429},
  archivePrefix = {arXiv},
  primaryClass  = {cs.CL},
  url           = {https://arxiv.org/abs/2409.07429}
}
```
---

## §4 How much of measured progress is the harness? — empirical studies

### [HarnessEvo] — Don't Blame the Large Language Model: How Agent Harness Evolution Shapes Coding Agent Quality
- **Authors / Year / Venue:** Oussama Ben Sghaier, Hao Li, Bram Adams, Ahmed E. Hassan / 2026 / arXiv preprint (no venue on the record).
- **Link:** arXiv:2607.03691
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2607.03691.json`).
- **Type:** empirical study
- **Problem:** Practitioners blame quality regressions on the model, but the harness changes far more often than the model does. Nobody had measured the harness's own contribution over time.
- **Method:** The study inverts the usual protocol: instead of fixing the harness and varying the model, it **fixes the model and varies only the harness**. Two parts: a release-history study of five major open-source harnesses (Codex, Qwen Code, Gemini, OpenCode, OpenHands), and a controlled longitudinal deep dive in which 35 sequential releases of the Qwen Code CLI are each evaluated on 50 stratified SWE-bench Verified tasks with the LLM held constant. Quality fluctuations are then traced back to specific pull requests and architectural components.
- **Verification signal:** executable check (SWE-bench Verified task resolution).
- **What changes:** nothing is optimised — this is a measurement study; the independent variable is the harness version.
- **Results that matter:** Release velocity exceeding two releases per day across the studied harnesses, with thousands of issues within months; the controlled 35-release sweep shows quality moving up *and down* with harness version at a fixed model, with individual pull requests linked to measured shifts.
- **Limitations / criticisms:** One CLI, 50 tasks and one model family; SWE-bench Verified is a narrow proxy for agent quality; no causal intervention beyond version ordering.
- **Relevance to this FYP (1–5) and why:** **5.** This is the empirical warrant for the whole project. If harness churn alone moves benchmark scores at a fixed model, then (a) harness improvement is a real capability lever, and (b) any ARC-AGI-3 result that does not pin the harness version is uninterpretable. It also supplies the confound the FYP must control: harness gains can be *negative*.
- **Reusable structure:** The fix-the-model-vary-the-harness protocol — the FYP should report ARC-AGI-3 scores this way, and should version-pin the harness for every reported number.
- **BibTeX:** 

```bibtex
@misc{sghaier2026don,
  title         = {{Don't Blame the Large Language Model: How Agent Harness Evolution Shapes Coding Agent Quality}},
  author        = {Sghaier, Oussama Ben and Li, Hao and Adams, Bram and Hassan, Ahmed E.},
  year          = {2026},
  eprint        = {2607.03691},
  archivePrefix = {arXiv},
  primaryClass  = {cs.SE},
  url           = {https://arxiv.org/abs/2607.03691}
}
```

### [Agentless] — Agentless: Demystifying LLM-based Software Engineering Agents
- **Authors / Year / Venue:** Chunqiu Steven Xia, Yinlin Deng, Soren Dunn, Lingming Zhang / 2024 (v2 2024-10) / arXiv preprint (Semantic Scholar records the venue as arXiv.org; 479 citations at time of retrieval).
- **Link:** arXiv:2407.01489
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2407.01489.json`); Semantic Scholar record also cached.
- **Type:** empirical study
- **Problem:** Whether the complexity of autonomous agent scaffolds is actually earning its keep.
- **Method:** Agentless deliberately removes the agentic parts: no tool choice, no self-directed planning, no autonomous control flow. It runs a fixed three-phase pipeline — localise, repair, validate patch — and nothing else. The comparison is therefore "elaborate scaffold vs almost no scaffold", holding the model constant. The authors additionally hand-classify SWE-bench Lite problems and build SWE-bench Lite-S by removing tasks whose issue text leaks the ground-truth patch or is misleading.
- **Verification signal:** executable check (test-suite validation of patches).
- **What changes:** nothing is learned — it is a fixed pipeline; the paper's contribution is the negative control.
- **Results that matter:** 32.00% on SWE-bench Lite (96 correct fixes) at $0.70 per issue — reported as the highest performance *and* lowest cost among open-source software agents at the time.
- **Limitations / criticisms:** A three-phase pipeline is itself a harness, carefully designed for this task type, so the result is better read as "simple, well-fitted scaffold beats complex scaffold" than as "scaffolds do not matter"; results are on SWE-bench Lite only.
- **Relevance to this FYP (1–5) and why:** **4.** It is the discipline check on Topic 1: the corpus's headline gains come from adding scaffold machinery, and Agentless shows that a simple pipeline plus honest benchmark hygiene can beat that machinery. For ARC-AGI-3, where each extra scaffold step costs actions and the score is squared in action count, this warning is sharper than in software engineering.
- **Reusable structure:** The "simplest reasonable pipeline" baseline (mandatory in the FYP's results chapter), and the benchmark-hygiene audit that removes tasks whose statement leaks the answer.
- **BibTeX:** 

```bibtex
@misc{xia2024agentless,
  title         = {{Agentless: Demystifying LLM-based Software Engineering Agents}},
  author        = {Xia, Chunqiu Steven and Deng, Yinlin and Dunn, Soren and Zhang, Lingming},
  year          = {2024},
  eprint        = {2407.01489},
  archivePrefix = {arXiv},
  primaryClass  = {cs.SE},
  url           = {https://arxiv.org/abs/2407.01489}
}
```

### [StateM] — StateM: Reaching 95.3% Raw Accuracy, or a $15 Frontier Run, on Terminal-Bench 2.1 via Harness Scaling
- **Authors / Year / Venue:** Ziheng Qin, Yaxin Lu, Zhangyang Atlas Wang, Kai Wang / 2026 / arXiv preprint (record comment: "Harness Scaling, Semi-Self-Evolving Agent").
- **Link:** arXiv:2608.15089
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2608.15089.json`).
- **Type:** method / empirical study
- **Problem:** Long-horizon agents fail even when the model can solve every constituent step — they lose track of mutable state, fail to reactivate earlier lessons, skip known procedures, or stop early.
- **Method:** StateM is a runtime, not a model change: execution is organised around durable states, phase-local context, checked transitions, recoverable runbooks, and versioned procedural practices that both agents and users can inspect. Postmortem findings are converted into persistent, executable preconditions rather than advice in a prompt. The authors call this **harness scaling** — buying capability by scaling the execution system while the weights stay fixed.
- **Verification signal:** executable check (Terminal-Bench 2.1 and BusinessBench task success).
- **What changes:** scaffold code and persistent procedural memory (runbooks, "golden rules"); weights frozen.
- **Results that matter:** Terminal-Bench 2.1 raised to 92.1% on one backbone versus an 83.1% reference; 95.3% raw accuracy across 445 trials on a stronger backbone; a runbook transfers unchanged across model versions; final-score API usage ≈ $15 against $574.68 for the GPT reference — roughly a 38× cost reduction at higher accuracy.
- **Limitations / criticisms:** No peer-review record; numbers are entangled with very recent proprietary backbones whose baselines are not independently reproducible; "held-out" BusinessBench gains are small (0.55 macro / 1.34 micro points) except for two mechanism-matched families, which suggests the transferable part is narrower than the headline.
- **Relevance to this FYP (1–5) and why:** **5.** The cost-per-score result is the closest analogue in the literature to ARC-AGI-3's efficiency metric: it demonstrates that harness structure buys *efficiency*, not just success. Durable state and checked transitions are also the right primitives for an environment where the agent must build a world model from scratch.
- **Reusable structure:** Runbooks as versioned, transferable procedural memory; reporting accuracy **and** cost per run; the "frozen profile" transfer test (apply an unchanged harness to a different model).
- **BibTeX:** 

```bibtex
@misc{qin2026statem,
  title         = {{StateM: Reaching 95.3\% Raw Accuracy, or a \$15 Frontier Run, on Terminal-Bench 2.1 via Harness Scaling}},
  author        = {Qin, Ziheng and Lu, Yaxin and Wang, Zhangyang Atlas and Wang, Kai},
  year          = {2026},
  eprint        = {2608.15089},
  archivePrefix = {arXiv},
  primaryClass  = {cs.AI},
  url           = {https://arxiv.org/abs/2608.15089}
}
```

### [WorkspaceOpt] — Workspace Optimization: How to Train Your Agent
- **Authors / Year / Venue:** Elad Sarafian, Gal Kaplun, Ron Banner, Daniel Soudry, Boris Ginsburg / 2026 / arXiv preprint (no venue on the record).
- **Link:** arXiv:2605.09650
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2605.09650.json`).
- **Type:** method
- **Problem:** If a frontier model's weights cannot be adapted, what remains trainable? The paper's answer: the agent's *workspace* — the structured external substrate it reads, writes and tests.
- **Method:** Workspace optimisation is proposed as a deliberate mirror of weight-space training, with a stated four-way correspondence: artefacts in place of parameters, evidence in place of data, counterexamples in place of losses, and textual feedback in place of gradients. It is instantiated as **DreamTeam**, a multi-agent harness for ARC-AGI-3 whose roles build an executable world model, plan, hypothesise, probe, strategise, and route failures.
- **Verification signal:** environment reward — the official ARC-AGI-3 scoring protocol.
- **What changes:** memory/artefacts and scaffold structure (the workspace); weights frozen.
- **Results that matter:** On the 25-game ARC-AGI-3 public set under the official protocol, averaged over two runs, DreamTeam improves the protocol-matched state of the art from **36% to 38.4% while using 31% fewer environment actions per game**.
- **Limitations / criticisms:** Two runs on 25 public games is a thin sample for a benchmark whose whole design anticipates public-set overfitting; no private-set result; the SOTA baseline is "protocol-matched", which is not the same as the headline leaderboard number.
- **Relevance to this FYP (1–5) and why:** **5.** This is the single most directly comparable paper in the corpus — same benchmark, same frozen-weights premise, same locus of change — and it reports the action-efficiency gain that ARC-AGI-3's squared metric rewards. It is simultaneously the FYP's closest prior art and its most important baseline to beat.
- **Reusable structure:** The parameters/data/loss/gradient ↔ artefacts/evidence/counterexamples/feedback correspondence as a framing device; and the practice of reporting **score and actions-per-game together**, which is the correct reporting format for this benchmark.
- **BibTeX:** 

```bibtex
@misc{sarafian2026workspace,
  title         = {{Workspace Optimization: How to Train Your Agent}},
  author        = {Sarafian, Elad and Kaplun, Gal and Banner, Ron and Soudry, Daniel and Ginsburg, Boris},
  year          = {2026},
  eprint        = {2605.09650},
  archivePrefix = {arXiv},
  primaryClass  = {cs.AI},
  url           = {https://arxiv.org/abs/2605.09650}
}
```

### [Weng2026] — Harness Engineering for Self-Improvement `[non-archival]`
- **Authors / Year / Venue:** Lilian Weng / 2026-07-04 / Lil'Log (personal research blog) — `[non-archival]`.
- **Link:** https://lilianweng.github.io/posts/2026-07-04-harness/
- **Verified:** yes — page fetched and cached as text (`refs/web/weng-harness.txt`, ~47k characters, retrieved 2026-09-04); date and authorship read from the page itself.
- **Type:** position / survey
- **Problem:** Organising the recursive-self-improvement literature around the harness — "the system surrounding a base model that orchestrates execution" — rather than around the weights.
- **Method:** A survey-style essay. It traces RSI from I. J. Good (1965) and Yudkowsky (2008), defines the harness as the layer that decides how the model thinks, calls tools, manages context, stores artefacts and evaluates results, and then organises harness design patterns (workflow automation, file system as persistent memory, sub-agents and backend jobs), harness optimisation (context engineering, workflow design), and self-improving harnesses (evolutionary search, joint optimisation with weights).
- **Verification signal:** none — it is a synthesis of other people's results, not an experiment.
- **What changes:** n/a (position piece); its subject matter is scaffold code, context and workflow.
- **Results that matter:** No new numbers. The load-bearing contribution is the claimed progression of optimisation targets: "instruction prompts → structured context → workflow → harness code → optimizer code", and the prediction that near-term RSI runs through the harness rather than through weight self-modification.
- **Limitations / criticisms:** Non-archival and not peer-reviewed; predictive rather than evidential; must be cited as an organising framework, never as a source for a number.
- **Relevance to this FYP (1–5) and why:** **4.** The optimisation-target progression is the most useful single organising axis found in this survey and is adopted (with attribution) as the ordering principle of `taxonomy.md`'s first axis. It also names the FYP's position precisely: the project sits at "workflow → harness code" on a frozen model.
- **Reusable structure:** The five-stage progression of optimisation targets, as a way of positioning the project's contribution against prior work in the literature-review chapter.
- **BibTeX:**

```bibtex
@misc{weng2026harness,
  title         = {{Harness Engineering for Self-Improvement}},
  author        = {Weng, Lilian},
  year          = {2026},
  month         = {7},
  howpublished  = {Lil'Log (blog post)},
  url           = {https://lilianweng.github.io/posts/2026-07-04-harness/},
  note          = {Non-archival; accessed 2026-09-04}
}
```

---

## §5 Failure modes of self-improving scaffolds

### [LibraryDrift] — Library Drift: Diagnosing and Fixing a Silent Failure Mode in Self-Evolving LLM Skill Libraries
- **Authors / Year / Venue:** Xing Zhang, Yanwei Cui, Guanghui Wang, Ziyuan Li, Wei Qiu, Bing Zhu, Peiyang He / 2026 (v3 2026-07) / ICML 2026 Workshop on Failure Modes in Agentic AI (FAGEN@ICML 2026) — stated on the arXiv record.
- **Link:** arXiv:2605.19576
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2605.19576.json`); the comment field states the workshop acceptance.
- **Type:** empirical study
- **Problem:** Self-evolving skill libraries accumulate skills without lifecycle management, which silently degrades retrieval and stalls performance — the failure mode the [Voyager] line never examined at scale.
- **Method:** Three contributions. (1) A reproducible trigger: ablations that isolate drift — one disables skill injection, one imposes premature retirement. (2) Trace-level diagnostics: an append-only evidence log with per-skill contribution scores, attribution verdicts and router engagement metrics, so the failure is visible before it reaches end-task scores. (3) A minimal governance recipe: outcome-driven retirement, a bounded active cap, and a meta-skill authoring prior.
- **Verification signal:** executable check (MBPP+ pass@1) with per-skill outcome attribution.
- **What changes:** memory (the skill library) and its governance policy.
- **Results that matter:** The cited SkillsBench comparison — LLM-authored skills deliver +0.0pp while human-curated skills deliver +16.2pp — is the motivating symptom; the governance recipe lifts held-out pass@1 from a 0.258 baseline to a 0.584 late-window mean (rolling gain +0.328) on MBPP+ hard-100 over 100 rounds; premature retirement is actively harmful (−0.019).
- **Limitations / criticisms:** Workshop paper; a single code benchmark; the +16.2pp figure is quoted from SkillsBench rather than measured here, so it inherits that benchmark's assumptions.
- **Relevance to this FYP (1–5) and why:** **5.** Any ARC-AGI-3 agent that accumulates skills or workflows over 135 environments will hit this. The paper supplies the diagnostics *and* the fix, and — crucially — evidence that unmanaged accumulation is worth approximately zero, which is the null hypothesis the FYP must beat.
- **Reusable structure:** The append-only evidence log with per-skill contribution attribution (adopt directly), the bounded-active-cap plus outcome-driven-retirement governance recipe, and the ablation set that isolates drift.
- **BibTeX:** 

```bibtex
@misc{zhang2026library,
  title         = {{Library Drift: Diagnosing and Fixing a Silent Failure Mode in Self-Evolving LLM Skill Libraries}},
  author        = {Zhang, Xing and Cui, Yanwei and Wang, Guanghui and Li, Ziyuan and Qiu, Wei and Zhu, Bing and He, Peiyang},
  year          = {2026},
  eprint        = {2605.19576},
  archivePrefix = {arXiv},
  primaryClass  = {cs.AI},
  url           = {https://arxiv.org/abs/2605.19576},
  note          = {Accepted to the ICML 2026 Workshop on Failure Modes in Agentic AI (FAGEN@ICML 2026), Seoul, South}
}
```

### [BlindCurator] — The Blind Curator: How a Biased Judge Silently Disables Skill Retirement in Self-Evolving Agents
- **Authors / Year / Venue:** Xing Zhang, Yanwei Cui, Guanghui Wang, Ziyuan Li, Wei Qiu, Bing Zhu, Peiyang He / 2026 (v2 2026-08) / COLM 2026 Workshop on Agent Behavior — stated on the arXiv record.
- **Link:** arXiv:2607.07436
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2607.07436.json`); the comment field states the workshop publication.
- **Type:** empirical study
- **Problem:** Skill retirement is what keeps a growing library from dropping below the no-skill baseline, but its guarantee assumes an unbiased reward — false whenever an LLM judge is the grader.
- **Method:** A corrupted-reward analysis followed by a behavioural study on a reference-free report-writing testbed with a code-generation cross-check. Corruption is injected on top of a deterministic reward so the causal channel is isolated, and genuine retirement is separated from cap-eviction churn.
- **Verification signal:** the object of study *is* the verification signal — a deliberately corrupted LLM judge versus a deterministic reward.
- **What changes:** memory (skill library) under a corrupted acceptance rule.
- **Results that matter:** Symmetric noise leaves retirement intact, but **false-pass bias disables contribution-based retirement past a sharp threshold (false-pass rate 0.45) that no amount of data can cross**; the mechanism failure is universal across domains and failure rates, sparing only near-zero-false-pass, verifier-like graders. The downstream effect is regime-dependent and can be invisible in aggregate metrics.
- **Limitations / criticisms:** Workshop paper; the 0.45 threshold is specific to this testbed and should not be quoted as a general constant; corruption is synthetic rather than observed in the wild.
- **Relevance to this FYP (1–5) and why:** **5.** It is the sharpest statement of the *verifier gap* in the corpus, and it converts an abstract worry into a design rule: only near-verifier-quality graders keep a self-evolving library safe. ARC-AGI-3 supplies exactly such a grader (the environment), which is a concrete argument that this benchmark is a *better* substrate for self-evolution research than reference-free text tasks.
- **Reusable structure:** The defect-injection audit — deliberately corrupt your acceptance signal at known rates and measure where the mechanism breaks — is a cheap, high-value experiment for the FYP's evaluation chapter.
- **BibTeX:** 

```bibtex
@misc{zhang2026blind,
  title         = {{The Blind Curator: How a Biased Judge Silently Disables Skill Retirement in Self-Evolving Agents}},
  author        = {Zhang, Xing and Cui, Yanwei and Wang, Guanghui and Li, Ziyuan and Qiu, Wei and Zhu, Bing and He, Peiyang},
  year          = {2026},
  eprint        = {2607.07436},
  archivePrefix = {arXiv},
  primaryClass  = {cs.AI},
  url           = {https://arxiv.org/abs/2607.07436},
  note          = {Published at COLM 2026 Workshop on Agent Behavior}
}
```

### [PhantomGuardrails] — Phantom Guardrails: When Self-Improving Agent Harnesses Fix Failures That Never Happened
- **Authors / Year / Venue:** Su Wang, Pin Qian, Yifan Lin, Jingzhou Xu, Yihang Chen, Xiaochong Jiang, Lifei Liu, Haoran Yu (8 authors) / 2026 / arXiv preprint (no venue on the record).
- **Link:** arXiv:2607.13083
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2607.13083.json`).
- **Type:** empirical study
- **Problem:** Harness self-improvement loops ask "how do I fix this failure?" but rarely ask "was there a failure?" — so they can hallucinate problems and then hard-code guardrails against them.
- **Method:** A deterministic micro-lab (the "Counterfactual Fabrication Lab") in which the correct action is provably *do nothing*: a candidate guardrail is planted for a failure class that never occurs, only legal episodes are shown, and a byte-exact oracle checks every cited violation. Conditions are varied one at a time to find what triggers fabrication.
- **Verification signal:** byte-exact oracle — the strongest possible check, which is what makes the negative result airtight.
- **What changes:** scaffold code (prompts, parsers, filters, validators, guardrails) proposed by an LLM.
- **Results that matter:** With a rule-shaped but harmless pattern in legal input, the proposer invented a failure and enabled a guardrail for a non-existent rule in **15/60 runs, versus 0/60 on featureless input**. Fabrication in single-shot proposals requires three conditions together — a rule-shaped pattern, an open-ended rule set, and an instruction presupposing failures — and removing any one eliminates it. Inside an add-only accept loop it recurs even without the presupposing instruction, and persists once admitted.
- **Limitations / criticisms:** A deliberately minimal synthetic lab; one proposer configuration; the phenomenon's prevalence in real harness-optimisation systems is not measured.
- **Relevance to this FYP (1–5) and why:** **4.** ARC-AGI-3 is *made of* rule-shaped patterns with no stated rule set — precisely the two of three trigger conditions the paper identifies — and a self-improving harness will be prompted to find failures. The paper's practical rule (never run an add-only accept loop; require evidence that a failure occurred) should be a design constraint from day one.
- **Reusable structure:** The "correct action is do nothing" control condition — an ablation that most self-improvement papers omit and that would strengthen the FYP's claims considerably.
- **BibTeX:** 

```bibtex
@misc{wang2026phantom,
  title         = {{Phantom Guardrails: When Self-Improving Agent Harnesses Fix Failures That Never Happened}},
  author        = {Wang, Su and Qian, Pin and Lin, Yifan and Xu, Jingzhou and Chen, Yihang and Jiang, Xiaochong and Liu, Lifei and Yu, Haoran},
  year          = {2026},
  eprint        = {2607.13083},
  archivePrefix = {arXiv},
  primaryClass  = {cs.CR},
  url           = {https://arxiv.org/abs/2607.13083}
}
```

### [TextPolicies] — From Agent Failures to Text Policies: What Works and What Breaks
- **Authors / Year / Venue:** Jaideep Ray, Ankit Goyal / 2026 / arXiv preprint (no venue on the record).
- **Link:** arXiv:2607.20668
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2607.20668.json`).
- **Type:** empirical study
- **Problem:** [TextGrad]'s thesis is that natural-language feedback can act as a gradient on text components. In the agent setting feedback arrives only after a whole action sequence, so which decision caused the failure is unclear.
- **Method:** The study deliberately separates two abilities: *following* a useful textual policy, and *learning* that policy from experience. Human-written policies test the first; policies generated from the agent's own trajectories — with richer traces, counterfactual evidence, and iterative [GEPA] search — test the second. Two frozen 7B agents on TextWorldExpress.
- **Verification signal:** environment reward (TextWorldExpress success).
- **What changes:** context/prompt (a textual policy), with the weights frozen.
- **Results that matter:** Human-written policies improve the two frozen 7B agents by **5.0 success points** — so useful policy text demonstrably exists — but policies generated from agent trajectories **do not reliably beat fixed prompting**, even with richer traces, counterfactual evidence or GEPA search.
- **Limitations / criticisms:** Small models (7B) and one environment family; a stronger proposer might close the gap; absence of evidence at this scale is not proof of impossibility.
- **Relevance to this FYP (1–5) and why:** **5.** This is the most important negative result for the FYP's design. It localises the bottleneck precisely: not executing textual updates, but *generating and selecting* them from long-horizon experience. ARC-AGI-3 is a harder instance of the same setting, so the project must treat policy *generation and selection* as the research problem rather than assuming a TextGrad/GEPA loop will work.
- **Reusable structure:** The follow-vs-learn decomposition — an oracle arm with human-written policy text that upper-bounds what any self-generated policy could achieve. This is a cheap, decisive experiment the FYP should run early.
- **BibTeX:** 

```bibtex
@misc{ray2026agent,
  title         = {{From Agent Failures to Text Policies: What Works and What Breaks}},
  author        = {Ray, Jaideep and Goyal, Ankit},
  year          = {2026},
  eprint        = {2607.20668},
  archivePrefix = {arXiv},
  primaryClass  = {cs.CL},
  url           = {https://arxiv.org/abs/2607.20668}
}
```

### [SelfImprovSurvey] — Self-Improvements in Modern Agentic Systems: A Survey
- **Authors / Year / Venue:** Zhe Ren, Yimeng Chen, Dandan Guo, Guowei Rong, Tonghui Li, R. B. Xiong, Qingfeng Lan, Wenyi Wang, et al. (12 authors) / 2026 / arXiv preprint (record comment: 97 pages, 12 figures).
- **Link:** arXiv:2607.13104
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2607.13104.json`).
- **Type:** survey
- **Problem:** The self-improving-agent literature is fragmented across prompt optimisation, memory, tool learning and weight updates, with no shared formalism.
- **Method:** The survey represents a modern agent as a configuration coupling a foundation model with an operational scaffold of prompts, memory, tools and control logic, then formalises self-improvement as a **self-induced update operator** that obtains and commits updates to either model parameters or scaffold components. Prior work is organised by *update target* and by the *signals that drive change*.
- **Verification signal:** n/a (survey).
- **What changes:** n/a — but its two organising axes are update target and driving signal.
- **Results that matter:** No new experimental numbers. Its contribution is the two-axis organisation, which independently matches the taxonomy this issue specifies (what is optimised × where the signal comes from) — useful corroboration that the taxonomy is the field's natural cut rather than this project's invention.
- **Limitations / criticisms:** No peer-review record; 97 pages of coverage with limited critical synthesis; being a 2026 survey it fixes a fast-moving snapshot.
- **Relevance to this FYP (1–5) and why:** **3.** No mechanism to borrow, but it is the citation that lets the literature-review chapter claim its taxonomy is grounded in an existing framing rather than asserted, and it is a snowballing source for anything this corpus missed.
- **Reusable structure:** The "self-induced update operator" formalism — a compact way to state precisely what the FYP's loop does and does not update.
- **BibTeX:** 

```bibtex
@misc{ren2026selfimprovements,
  title         = {{Self-Improvements in Modern Agentic Systems: A Survey}},
  author        = {Ren, Zhe and Chen, Yimeng and Guo, Dandan and Rong, Guowei and Li, Tonghui and Xiong, R. B. and Lan, Qingfeng and Wang, Wenyi and Nanbo, Li and Yang, Yibo and Zhuge, Mingchen and Schmidhuber, Jürgen},
  year          = {2026},
  eprint        = {2607.13104},
  archivePrefix = {arXiv},
  primaryClass  = {cs.AI},
  url           = {https://arxiv.org/abs/2607.13104}
}
```
