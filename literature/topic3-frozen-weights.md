# Topic 3 — Capability gain without parameter updates

**Scope.** Evidence and mechanisms for a system becoming measurably stronger while the underlying
weights are frozen. This is the topic the FYP hinges on, so it is treated as the most important of
the three.

**Mandatory classification.** Every entry below carries a **Gain type** line classifying the reported
improvement as one of:

- **(a) new capability** — the system does something the frozen model could not do at any sampling
  budget, i.e. the improvement is outside the base model's support;
- **(b) elicitation** — the system surfaces behaviour the base model already had, typically by
  spending search, verification or context on finding it;
- **(c) unclear** — the paper does not report the evidence needed to distinguish (a) from (b), most
  often because it never measures pass@k at large k or never runs an unassisted-base-model control.

This distinction is the section's central argument, and §4 exists because several papers here
dispute each other's classification.

**Test-time training is separated.** TTT usually *does* update weights and therefore does not belong
in a frozen-weights section. It is kept in §3 as an explicitly labelled sub-bucket because the FYP
must compare against it, not because it qualifies.

**Corpus size:** 31 entries, all verified against the live record and cached under `refs/`.

**Quoting convention.** Double quotes mark one of three things, never anything else: at most
one short verbatim quotation per source; a metadata string copied exactly from the record
(venue, comment, title); or scare quotes on this survey's own phrasing. Everything else is
paraphrase.

---

## §1 Search and sampling over a frozen model

### [SelfConsistency] — Self-Consistency Improves Chain of Thought Reasoning in Language Models
- **Authors / Year / Venue:** Xuezhi Wang, Jason Wei, Dale Schuurmans, Quoc Le, Ed Chi, Sharan Narang, Aakanksha Chowdhery, Denny Zhou / 2022 (v4 2023) / ICLR 2023 (venue stated on the arXiv record).
- **Link:** arXiv:2203.11171
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2203.11171.json`); the comment field states publication at ICLR 2023.
- **Type:** method
- **Problem:** Greedy decoding commits to one reasoning path, which is fragile when a single step goes wrong.
- **Method:** Replace greedy decoding with sampling: draw a diverse set of reasoning paths for the same prompt, then marginalise over the paths and take the most consistent final answer. The intuition is that a hard problem admits many routes to its single correct answer, but errors are idiosyncratic and do not agree with each other. Nothing is trained; the entire gain comes from how the frozen model is sampled and aggregated.
- **Verification signal:** self-consistency — agreement among samples, with no external checker.
- **What changes:** nothing persists. Extra inference compute only.
- **Results that matter:** +17.9% on GSM8K, +11.0% SVAMP, +12.2% AQuA, +6.4% StrategyQA, +3.9% ARC-challenge over chain-of-thought prompting.
- **Limitations / criticisms:** Requires a well-defined answer to vote over — unavailable for an action sequence; agreement is not correctness, and [Monkeys] shows voting-based selection plateaus beyond a few hundred samples.
- **Gain type:** **(b) elicitation.** The correct answer was already in the model's sample distribution; voting only locates it. The paper makes no claim otherwise.
- **Relevance to this FYP (1–5) and why:** **3.** The mechanism does not transfer cleanly — ARC-AGI-3 has no discrete answer to marginalise over, and majority voting over action sequences is ill-defined. It matters as the baseline definition of "elicitation" that the rest of the section is measured against, and as the cheapest verifier-free aggregation to beat.
- **Reusable structure:** Marginalise-over-paths aggregation, applicable to the FYP only where a *decision* (e.g. an inferred goal predicate) can be voted on, rather than a trajectory.
- **BibTeX:** 

```bibtex
@misc{wang2022selfconsistency,
  title         = {{Self-Consistency Improves Chain of Thought Reasoning in Language Models}},
  author        = {Wang, Xuezhi and Wei, Jason and Schuurmans, Dale and Le, Quoc and Chi, Ed and Narang, Sharan and Chowdhery, Aakanksha and Zhou, Denny},
  year          = {2022},
  eprint        = {2203.11171},
  archivePrefix = {arXiv},
  primaryClass  = {cs.CL},
  url           = {https://arxiv.org/abs/2203.11171},
  note          = {Published at ICLR 2023}
}
```

### [ToT] — Tree of Thoughts: Deliberate Problem Solving with Large Language Models
- **Authors / Year / Venue:** Shunyu Yao, Dian Yu, Jeffrey Zhao, Izhak Shafran, Thomas L. Griffiths, Yuan Cao, Karthik Narasimhan / 2023 (v2 2023-12) / NeurIPS 2023 (venue stated on the arXiv record).
- **Link:** arXiv:2305.10601
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2305.10601.json`); the comment field states "NeurIPS 2023 camera ready version".
- **Type:** method
- **Problem:** Token-level, left-to-right decoding cannot explore, look ahead, or recover from a bad early decision.
- **Method:** ToT generalises chain-of-thought into a search tree whose nodes are coherent units of text ("thoughts") representing intermediate steps. The model both *generates* candidate next thoughts and *self-evaluates* them, so it can choose which branch to expand, look ahead, and backtrack. The search algorithm (BFS/DFS) is external scaffolding; the model supplies the successor function and the heuristic.
- **Verification signal:** self-evaluation by the same frozen model (a learned/LLM heuristic, not an external check).
- **What changes:** nothing persists; inference-time search only.
- **Results that matter:** Game of 24 solve rate rises from **4% (GPT-4 with chain-of-thought) to 74%** with ToT; gains also reported on Creative Writing and Mini Crosswords.
- **Limitations / criticisms:** The self-evaluation heuristic is unverified and can misrank branches; the 74% figure is on a small puzzle domain with a cheap correctness check; search cost per problem is high.
- **Gain type:** **(b) elicitation**, with a caveat. A 4%→74% jump looks like new capability, but the model's own step generator and evaluator are unchanged — search simply visits far more of the model's existing distribution. Whether search over a distribution can reach points that sampling never would at any budget is precisely the question [Monkeys] and [ReasoningWithSampling] address.
- **Relevance to this FYP (1–5) and why:** **4.** ARC-AGI-3 is a planning problem where early actions are pivotal and backtracking is impossible in the real environment — so the ToT pattern only works if search happens inside a *model* of the game rather than in the game itself. That is exactly the move [Twin] and [Tycho] make, which makes ToT the direct ancestor of the current ARC-AGI-3 state of the art.
- **Reusable structure:** Generate-and-self-evaluate branching with explicit backtracking, run against a learned world model so that exploration does not cost scored actions.
- **BibTeX:** 

```bibtex
@misc{yao2023tree,
  title         = {{Tree of Thoughts: Deliberate Problem Solving with Large Language Models}},
  author        = {Yao, Shunyu and Yu, Dian and Zhao, Jeffrey and Shafran, Izhak and Griffiths, Thomas L. and Cao, Yuan and Narasimhan, Karthik},
  year          = {2023},
  eprint        = {2305.10601},
  archivePrefix = {arXiv},
  primaryClass  = {cs.CL},
  url           = {https://arxiv.org/abs/2305.10601}
}
```

### [Monkeys] — Large Language Monkeys: Scaling Inference Compute with Repeated Sampling
- **Authors / Year / Venue:** Bradley Brown, Jordan Juravsky, Ryan Ehrlich, Ronald Clark, Quoc V. Le, Christopher Ré, Azalia Mirhoseini / 2024 (v3 2024-12) / arXiv preprint (no venue on the record).
- **Link:** arXiv:2407.21787
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2407.21787.json`).
- **Type:** empirical study
- **Problem:** Inference is usually one attempt per problem; what happens if you simply sample many times?
- **Method:** Repeatedly sample candidate solutions from a frozen model and measure **coverage** — the fraction of problems solved by *any* sample — as a function of sample count, across tasks and models spanning four orders of magnitude of samples. The study then separates two regimes: domains with automatic verifiers, where coverage converts directly into performance, and domains without, where a selection method must pick from the sample pool.
- **Verification signal:** executable check (unit tests, proof checkers) in the verifiable regime; majority voting and reward models in the non-verifiable regime.
- **What changes:** nothing persists; inference compute only.
- **Results that matter:** Coverage is often log-linear in sample count and fits an exponentiated power law — inference-time scaling laws. On SWE-bench Lite, DeepSeek-Coder-V2-Instruct goes from **15.9% with one sample to 56% with 250 samples**, beating the 43% single-sample state of the art. Critically, **majority voting and reward-model selection plateau beyond several hundred samples** and fail to scale with the budget.
- **Limitations / criticisms:** Coverage is an upper bound that is only realisable with a verifier; [LimitsResampling] shows imperfect verifiers cap the achievable accuracy regardless of budget, which sharply qualifies the headline.
- **Gain type:** **(b) elicitation**, and the paper is the clearest demonstration of why: the solutions were always in the distribution, and the entire question is whether you can *select* them. Coverage rises; unaided accuracy does not.
- **Relevance to this FYP (1–5) and why:** **5.** It states the FYP's core dependency in one sentence: frozen-model gains scale with sampling *only where a verifier exists*. ARC-AGI-3 has one (the environment), which is the strongest argument that this benchmark is the right place to study frozen-weight self-improvement — but each sample costs scored actions, so the FYP's real problem is coverage *per action*, not coverage per sample.
- **Reusable structure:** Coverage-versus-budget curves as the reporting format, and the explicit separation of coverage from selection — an ARC-AGI-3 version would plot solved-games versus total environment actions.
- **BibTeX:** 

```bibtex
@misc{brown2024large,
  title         = {{Large Language Monkeys: Scaling Inference Compute with Repeated Sampling}},
  author        = {Brown, Bradley and Juravsky, Jordan and Ehrlich, Ryan and Clark, Ronald and Le, Quoc V. and Ré, Christopher and Mirhoseini, Azalia},
  year          = {2024},
  eprint        = {2407.21787},
  archivePrefix = {arXiv},
  primaryClass  = {cs.LG},
  url           = {https://arxiv.org/abs/2407.21787}
}
```

### [Snell] — Scaling LLM Test-Time Compute Optimally can be More Effective than Scaling Model Parameters
- **Authors / Year / Venue:** Charlie Snell, Jaehoon Lee, Kelvin Xu, Aviral Kumar / 2024 / arXiv preprint (no venue on the record).
- **Link:** arXiv:2408.03314
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2408.03314.json`).
- **Type:** empirical study
- **Problem:** How much can a fixed inference budget buy, and how should it be spent?
- **Method:** Two mechanisms are analysed: searching against dense **process-based verifier reward models**, and adaptively updating the model's own proposal distribution at test time. The central finding is that which mechanism wins depends on prompt difficulty, which motivates a **compute-optimal** policy that allocates test-time compute per prompt according to estimated difficulty. The comparison is then made FLOPs-matched against pretraining more parameters.
- **Verification signal:** learned reward model (process reward model) guiding search.
- **What changes:** nothing persists in the base model; the paper does consider adaptive distribution updates at test time.
- **Results that matter:** Compute-optimal allocation improves test-time-compute efficiency by **more than 4×** over a best-of-N baseline; in a FLOPs-matched comparison, on problems where a smaller base model already attains non-trivial success rates, test-time compute lets it **outperform a 14× larger model**.
- **Limitations / criticisms:** The 14× result is explicitly conditioned on non-trivial base success rates — it does not hold where the base model fails outright, which is the ARC-AGI-3 regime; process reward models must be trained, so the method is not free of parameter updates somewhere in the system.
- **Gain type:** **(b) elicitation**, self-described: the paper is about allocating compute to *find* good outputs, and its own caveat (needs non-trivial base success) is an elicitation boundary.
- **Relevance to this FYP (1–5) and why:** **5.** It is the canonical "test-time compute substitutes for parameters" citation *and* it comes with the qualification that most citations of it omit. For a benchmark where frontier systems score under 1%, the paper's own condition is not met — which is a precise, citable reason why ARC-AGI-3 needs mechanisms beyond test-time search.
- **Reusable structure:** Difficulty-conditioned compute allocation (spend more actions on games where the agent is near the boundary), and FLOPs-matched or action-matched comparison as the fair way to report gains.
- **BibTeX:** 

```bibtex
@misc{snell2024scaling,
  title         = {{Scaling LLM Test-Time Compute Optimally can be More Effective than Scaling Model Parameters}},
  author        = {Snell, Charlie and Lee, Jaehoon and Xu, Kelvin and Kumar, Aviral},
  year          = {2024},
  eprint        = {2408.03314},
  archivePrefix = {arXiv},
  primaryClass  = {cs.LG},
  url           = {https://arxiv.org/abs/2408.03314}
}
```

### [LetsVerify] — Let's Verify Step by Step
- **Authors / Year / Venue:** Hunter Lightman, Vineet Kosaraju, Yura Burda, Harri Edwards, Bowen Baker, Teddy Lee, Jan Leike, John Schulman, et al. (10 authors) / 2023 / arXiv preprint (no venue on the record).
- **Link:** arXiv:2305.20050
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2305.20050.json`).
- **Type:** empirical study
- **Problem:** Should feedback be given on the final answer (outcome supervision) or on each reasoning step (process supervision)?
- **Method:** A controlled comparison of outcome- versus process-supervised reward models used to select among sampled solutions on MATH, plus an active-learning study of how to spend human labelling effort. The generator stays frozen during selection; what differs is the verifier that ranks its samples. The paper also releases PRM800K, 800,000 step-level human feedback labels.
- **Verification signal:** learned reward model trained on human step-level labels — a human-labelled verifier, the most expensive kind.
- **What changes:** the reward model's weights (the generator is used frozen at selection time).
- **Results that matter:** Process supervision significantly outperforms outcome supervision; the process-supervised model solves **78%** of a representative MATH test subset; active learning substantially improves process supervision's data efficiency.
- **Limitations / criticisms:** Requires 800k human labels — the opposite of a self-improving loop; process rewards are domain-specific; results are on MATH only.
- **Gain type:** **(b) elicitation** of the generator, since only the ranking changes; but the *system* improves by training a verifier, so the parameter update has been moved rather than removed.
- **Relevance to this FYP (1–5) and why:** **4.** It establishes the verifier-quality axis that dominates this whole section: better verification, not better generation, produced the gain. For ARC-AGI-3 the analogue is free — the environment supplies dense step-level feedback (state transitions) without any human labelling, which is a real structural advantage over the maths setting.
- **Reusable structure:** The dense-step-feedback versus sparse-outcome-feedback ablation, run with the environment's transitions as the free process signal.
- **BibTeX:** 

```bibtex
@misc{lightman2023let,
  title         = {{Let's Verify Step by Step}},
  author        = {Lightman, Hunter and Kosaraju, Vineet and Burda, Yura and Edwards, Harri and Baker, Bowen and Lee, Teddy and Leike, Jan and Schulman, John and Sutskever, Ilya and Cobbe, Karl},
  year          = {2023},
  eprint        = {2305.20050},
  archivePrefix = {arXiv},
  primaryClass  = {cs.LG},
  url           = {https://arxiv.org/abs/2305.20050}
}
```

### [s1] — s1: Simple test-time scaling
- **Authors / Year / Venue:** Niklas Muennighoff, Zitong Yang, Weijia Shi, Xiang Lisa Li, Li Fei-Fei, Hannaneh Hajishirzi, Luke Zettlemoyer, Percy Liang, et al. (10 authors) / 2025 (v3 2025-03) / arXiv preprint (no venue on the record).
- **Link:** arXiv:2501.19393
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2501.19393.json`).
- **Type:** method
- **Problem:** Finding the simplest recipe that reproduces o1-style test-time scaling.
- **Method:** Two ingredients. A curated 1,000-example dataset (s1K) selected for difficulty, diversity and quality, used for supervised fine-tuning; and **budget forcing**, a decoding-time control that either terminates the model's thinking or extends it by appending "Wait" when the model tries to stop — which often makes it double-check and repair its own reasoning. Only budget forcing is a frozen-weights mechanism; the SFT stage is not.
- **Verification signal:** none at test time — budget forcing is unconditioned; correctness is only measured afterwards.
- **What changes:** weights (SFT on s1K), then context length at inference (budget forcing).
- **Results that matter:** s1-32B exceeds o1-preview on competition maths by **up to 27%** (MATH, AIME24); budget forcing alone extrapolates performance **from 50% to 57% on AIME24** beyond what the model achieves without test-time intervention.
- **Limitations / criticisms:** The 50→57% extrapolation is the only genuinely frozen-weights part and is modest; [InverseScaling] shows longer reasoning can *hurt* on other task families; forcing more thinking is an unconditioned intervention with no stopping criterion.
- **Gain type:** **(c) unclear** for the frozen-weights component. Budget forcing raises accuracy without training, but the paper does not measure whether the same answers were reachable by sampling the un-forced model more times, which is the control that would separate (a) from (b).
- **Relevance to this FYP (1–5) and why:** **3.** The transferable idea is that a trivial decoding-time controller can extract measurable extra accuracy from a frozen model. But ARC-AGI-3 penalises extra *actions*, not extra *tokens*, so "think longer" is nearly free here in a way it is not elsewhere — a benchmark-specific asymmetry worth exploiting and worth stating explicitly in the write-up.
- **Reusable structure:** The distinction between token budget and action budget: in ARC-AGI-3 the FYP should scale deliberation aggressively while holding scored actions fixed, and report both axes separately.
- **BibTeX:** 

```bibtex
@misc{muennighoff2025simple,
  title         = {{s1: Simple test-time scaling}},
  author        = {Muennighoff, Niklas and Yang, Zitong and Shi, Weijia and Li, Xiang Lisa and Fei-Fei, Li and Hajishirzi, Hannaneh and Zettlemoyer, Luke and Liang, Percy and Candès, Emmanuel and Hashimoto, Tatsunori},
  year          = {2025},
  eprint        = {2501.19393},
  archivePrefix = {arXiv},
  primaryClass  = {cs.CL},
  url           = {https://arxiv.org/abs/2501.19393}
}
```

### [Debate] — Improving Factuality and Reasoning in Language Models through Multiagent Debate
- **Authors / Year / Venue:** Yilun Du, Shuang Li, Antonio Torralba, Joshua B. Tenenbaum, Igor Mordatch / 2023 / arXiv preprint (no venue on the record).
- **Link:** arXiv:2305.14325
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2305.14325.json`).
- **Type:** method
- **Problem:** Whether multiple instances of the same model, arguing, can reach better answers than one instance reasoning alone.
- **Method:** Several instances of a language model independently propose responses, then read each other's responses and reasoning across multiple rounds, converging on a common final answer. The procedure and prompts are identical across tasks and apply directly to black-box models — no access to weights or logits is needed.
- **Verification signal:** self-consistency / mutual critique among model instances; no external checker.
- **What changes:** nothing persists; inference compute only.
- **Results that matter:** Reported significant improvements on mathematical and strategic reasoning tasks, and improved factual validity with fewer hallucinated answers. No single headline number in the abstract.
- **Limitations / criticisms:** Cost scales with agents × rounds; debate among copies of one model shares that model's blind spots; [SelfCorrect] shows that critique without external feedback can degrade reasoning.
- **Gain type:** **(b) elicitation.** All participants are the same frozen model, so nothing outside its distribution can enter the debate; the gain comes from aggregating and filtering.
- **Relevance to this FYP (1–5) and why:** **3.** Ensembling is cheap in tokens and free in actions, so it is a natural component of an ARC-AGI-3 harness for *deciding* (what is the goal? which hypothesis explains the transitions?) rather than for acting. Its weakness — correlated blind spots — is exactly why the environment's own feedback has to remain the arbiter.
- **Reusable structure:** Multi-instance deliberation on hypothesis selection, gated by replay verification rather than by consensus.
- **BibTeX:** 

```bibtex
@misc{du2023improving,
  title         = {{Improving Factuality and Reasoning in Language Models through Multiagent Debate}},
  author        = {Du, Yilun and Li, Shuang and Torralba, Antonio and Tenenbaum, Joshua B. and Mordatch, Igor},
  year          = {2023},
  eprint        = {2305.14325},
  archivePrefix = {arXiv},
  primaryClass  = {cs.CL},
  url           = {https://arxiv.org/abs/2305.14325}
}
```

### [Self-Refine] — Self-Refine: Iterative Refinement with Self-Feedback
- **Authors / Year / Venue:** Aman Madaan, Niket Tandon, Prakhar Gupta, Skyler Hallinan, Luyu Gao, Sarah Wiegreffe, Uri Alon, Nouha Dziri, et al. (16 authors) / 2023 / arXiv preprint (no venue on the record).
- **Link:** arXiv:2303.17651
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2303.17651.json`).
- **Type:** method
- **Problem:** Models rarely produce their best output on the first attempt, and retraining to fix that is expensive.
- **Method:** One model plays three roles in a loop: generator, feedback provider, and refiner. It produces an initial output, criticises that output, and rewrites it using its own critique, repeating until satisfied. No supervised data, no additional training, and no reinforcement learning — the whole method is a prompting loop around a frozen model.
- **Verification signal:** self-evaluation only (no external checker), which is exactly the property [SelfCorrect] later attacks.
- **What changes:** nothing persists; inference-time iteration only.
- **Results that matter:** Across 7 tasks and GPT-3.5/ChatGPT/GPT-4, Self-Refine outputs are preferred by humans and automatic metrics over one-step generation from the same model, improving task performance by **~20% absolute on average**.
- **Limitations / criticisms:** [SelfCorrect] (ICLR 2024) directly disputes this class of result for *reasoning* tasks, finding that intrinsic self-correction without external feedback can leave performance unchanged or degrade it; Self-Refine's tasks include many generation tasks where "better" is judged by preference rather than correctness, which is a much softer criterion.
- **Gain type:** **(c) unclear**, and this is the honest classification: the paper reports preference-based improvement across mixed task types without measuring whether the refined answers were reachable by resampling the base model, and a peer-reviewed follow-up disputes the reasoning subset specifically.
- **Relevance to this FYP (1–5) and why:** **3.** It is the canonical "iterate on your own output" loop and therefore the baseline the FYP's environment-verified loop must beat. Its documented weakness is the project's opportunity: ARC-AGI-3 supplies the external feedback that Self-Refine lacks, so the comparison between self-judged and environment-judged refinement is a clean, cheap experiment.
- **Reusable structure:** The generator/critic/refiner decomposition within a single model — used in the FYP with the environment replacing the critic.
- **BibTeX:** 

```bibtex
@misc{madaan2023selfrefine,
  title         = {{Self-Refine: Iterative Refinement with Self-Feedback}},
  author        = {Madaan, Aman and Tandon, Niket and Gupta, Prakhar and Hallinan, Skyler and Gao, Luyu and Wiegreffe, Sarah and Alon, Uri and Dziri, Nouha and Prabhumoye, Shrimai and Yang, Yiming and Gupta, Shashank and Majumder, Bodhisattwa Prasad and Hermann, Katherine and Welleck, Sean and Yazdanbakhsh, Amir and Clark, Peter},
  year          = {2023},
  eprint        = {2303.17651},
  archivePrefix = {arXiv},
  primaryClass  = {cs.CL},
  url           = {https://arxiv.org/abs/2303.17651}
}
```
---

## §2 Learning that lives in the context, the memory, or an external world model

### [ICLasGD] — Transformers learn in-context by gradient descent
- **Authors / Year / Venue:** Johannes von Oswald, Eyvind Niklasson, Ettore Randazzo, João Sacramento, Alexander Mordvintsev, Andrey Zhmoginov, Max Vladymyrov / 2022 (v2 2023) / arXiv preprint (no venue on the record).
- **Link:** arXiv:2212.07677
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2212.07677.json`).
- **Type:** theory / empirical study
- **Problem:** In-context learning is treated as a black box; what is the mechanism?
- **Method:** The paper gives an explicit weight construction showing that a single linear self-attention layer induces the same data transformation as one step of gradient descent on a regression loss, then shows empirically that self-attention-only Transformers trained on regression either closely resemble the GD-learned model or literally recover the constructed weights. It goes further, identifying how Transformers *beat* plain GD by learning an iterative curvature correction and by fitting linear models on deep representations.
- **Verification signal:** none — mechanistic analysis against a known optimisation baseline.
- **What changes:** nothing at inference — the point is that the forward pass *is* an optimiser ("mesa-optimiser"), so learning happens in activations rather than parameters.
- **Results that matter:** The equivalence construction and the empirical weight match; and the finding that trained Transformers implement something strictly better than plain gradient descent on these problems.
- **Limitations / criticisms:** Restricted to linear self-attention and simple regression; extrapolating to large LLMs on symbolic tasks is an inference the paper does not license.
- **Gain type:** **(b) elicitation**, but in the deepest sense — it explains *why* context-only adaptation counts as real learning while leaving weights untouched, which makes the elicitation/acquisition boundary a matter of where the optimiser lives rather than a matter of principle.
- **Relevance to this FYP (1–5) and why:** **4.** It supplies the theoretical warrant for the FYP's central claim. Without it, "learning without weight updates" sounds like a contradiction; with it, the position is that the FYP moves the optimiser from the parameters into the context and the scaffold. Nothing operational transfers.
- **Reusable structure:** The framing "in-context adaptation is an optimiser in the forward pass" — the sentence the literature-review chapter needs to make its frozen-weights premise defensible.
- **BibTeX:** 

```bibtex
@misc{oswald2022transformers,
  title         = {{Transformers learn in-context by gradient descent}},
  author        = {Oswald, Johannes von and Niklasson, Eyvind and Randazzo, Ettore and Sacramento, João and Mordvintsev, Alexander and Zhmoginov, Andrey and Vladymyrov, Max},
  year          = {2022},
  eprint        = {2212.07677},
  archivePrefix = {arXiv},
  primaryClass  = {cs.LG},
  url           = {https://arxiv.org/abs/2212.07677}
}
```

### [AlgorithmDistillation] — In-context Reinforcement Learning with Algorithm Distillation
- **Authors / Year / Venue:** Michael Laskin, Luyu Wang, Junhyuk Oh, Emilio Parisotto, Stephen Spencer, Richie Steigerwald, DJ Strouse, Steven Hansen, et al. (14 authors) / 2022 / arXiv preprint (no venue on the record).
- **Link:** arXiv:2210.14215
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2210.14215.json`).
- **Type:** method
- **Problem:** Whether an RL *algorithm* — not just a policy — can be distilled into a network so that the network learns new tasks in-context.
- **Method:** Algorithm Distillation treats learning-to-reinforcement-learn as across-episode sequence prediction. A source RL algorithm generates *learning histories* (the whole trajectory of improvement, not just the final expert behaviour); a causal transformer is trained to predict actions given the preceding learning history. Because the training data contains improvement, the model reproduces improvement: at test time it gets better across episodes **entirely in-context, with no parameter updates**.
- **Verification signal:** environment reward (in the source histories, and implicitly at test time).
- **What changes:** at deployment, nothing but the context; the improvement is read off the growing history.
- **Results that matter:** In-context RL demonstrated in environments with sparse rewards, combinatorial task structure and pixel observations; AD learns a **more data-efficient RL algorithm than the source algorithm that generated its training data**.
- **Limitations / criticisms:** Needs a large corpus of learning histories from a source algorithm — expensive, and unavailable for a benchmark of 135 novel environments; context length bounds how much learning can be held.
- **Gain type:** **(a) new capability**, and one of the very few justified claims of it: the deployed network improves within an episode sequence on tasks it was not trained on, and does so faster than the algorithm that produced its data — a capability the underlying weights do not exhibit statically.
- **Relevance to this FYP (1–5) and why:** **4.** This is the strongest existence proof that improvement can be *purely* in-context, which is the FYP's thesis. The obstacle is the data requirement — but ARC-AGI-3 replays are exactly learning histories, and the benchmark logs them, so the ingredient AD needs is one the benchmark already produces.
- **Reusable structure:** Train (or prompt) on *learning histories* rather than on expert trajectories — the distinction that makes in-context improvement possible at all. For a frozen model this becomes: put the history of improvement, not the best attempt, in the context.
- **BibTeX:** 

```bibtex
@misc{laskin2022incontext,
  title         = {{In-context Reinforcement Learning with Algorithm Distillation}},
  author        = {Laskin, Michael and Wang, Luyu and Oh, Junhyuk and Parisotto, Emilio and Spencer, Stephen and Steigerwald, Richie and Strouse, DJ and Hansen, Steven and Filos, Angelos and Brooks, Ethan and Gazeau, Maxime and Sahni, Himanshu and Singh, Satinder and Mnih, Volodymyr},
  year          = {2022},
  eprint        = {2210.14215},
  archivePrefix = {arXiv},
  primaryClass  = {cs.LG},
  url           = {https://arxiv.org/abs/2210.14215}
}
```

### [AdA] — Human-Timescale Adaptation in an Open-Ended Task Space
- **Authors / Year / Venue:** Adaptive Agent Team, Jakob Bauer, Kate Baumli, Satinder Baveja, Feryal Behbahani, Avishkar Bhoopchand, Nathalie Bradley-Schmieg, Michael Chang, et al. (28 authors) / 2023 / arXiv preprint (no venue on the record).
- **Link:** arXiv:2301.07608
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2301.07608.json`).
- **Type:** method / empirical study
- **Problem:** RL agents do not adapt to genuinely novel tasks the way foundation models adapt to novel prompts.
- **Method:** Three ingredients produce a general in-context learning algorithm: (1) meta-RL across a vast, smooth and diverse task distribution; (2) a policy parameterised as a large attention-based memory architecture; and (3) **an automated curriculum prioritising tasks at the frontier of the agent's capabilities** — the same learnability principle as Topic 2, used here as a means to in-context adaptivity. At test time, on held-out environment dynamics, AdA does hypothesis-driven exploration and exploits what it discovers, with frozen weights.
- **Verification signal:** environment reward.
- **What changes:** during training, weights; at test time, nothing but the context/memory.
- **Results that matter:** Adaptation to open-ended novel 3D tasks **as quickly as humans**, on held-out dynamics; the agent can be prompted with first-person demonstrations; characteristic scaling laws in network size, memory length, and task-distribution richness.
- **Limitations / criticisms:** Enormous training cost and a hand-built task space (XLand); "human-timescale" is measured against human players on the same tasks, not against a general standard; nothing about the method is small-model-friendly.
- **Gain type:** **(a) new capability** at test time (the agent solves held-out dynamics it never trained on, with frozen weights) obtained by **weight training beforehand** — which is why it belongs here as the boundary case: frozen-weight adaptivity was *bought* with parameter updates.
- **Relevance to this FYP (1–5) and why:** **4.** AdA is the closest thing in the literature to "an agent that does what ARC-AGI-3 asks", and its three ingredients read as a specification: diverse task distribution, long memory, frontier curriculum. Two of the three are what Topic 2 supplies. Its lesson for a small-model FYP is sobering — the adaptivity came from scale — but its curriculum ingredient is exactly the part that is affordable.
- **Reusable structure:** The three-ingredient recipe as a design checklist, and the memory-length scaling study as an ablation the FYP can run cheaply (vary how much replay history the agent may condition on).
- **BibTeX:** 

```bibtex
@misc{team2023humantimescale,
  title         = {{Human-Timescale Adaptation in an Open-Ended Task Space}},
  author        = {Team, Adaptive Agent and Bauer, Jakob and Baumli, Kate and Baveja, Satinder and Behbahani, Feryal and Bhoopchand, Avishkar and Bradley-Schmieg, Nathalie and Chang, Michael and Clay, Natalie and Collister, Adrian and Dasagi, Vibhavari and Gonzalez, Lucy and Gregor, Karol and Hughes, Edward and Kashem, Sheleem and Loks-Thompson, Maria and Openshaw, Hannah and Parker-Holder, Jack and Pathak, Shreya and Perez-Nieves, Nicolas and Rakicevic, Nemanja and Rocktäschel, Tim and Schroecker, Yannick and Sygnowski, Jakub and Tuyls, Karl and York, Sarah and Zacherl, Alexander and Zhang, Lei},
  year          = {2023},
  eprint        = {2301.07608},
  archivePrefix = {arXiv},
  primaryClass  = {cs.LG},
  url           = {https://arxiv.org/abs/2301.07608}
}
```

### [DynamicCheatsheet] — Dynamic Cheatsheet: Test-Time Learning with Adaptive Memory
- **Authors / Year / Venue:** Mirac Suzgun, Mert Yuksekgonul, Federico Bianchi, Dan Jurafsky, James Zou / 2025 / arXiv preprint (no venue on the record).
- **Link:** arXiv:2504.07952
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2504.07952.json`).
- **Type:** method
- **Problem:** Language models process each query in a vacuum, rediscovering and re-committing the same solutions and mistakes.
- **Method:** Dynamic Cheatsheet gives a black-box model a persistent, evolving memory: strategies, code snippets and general insights are stored as the model works and are retrieved for later queries. The memory is **self-curated** — the model keeps concise, transferable snippets rather than whole transcripts — and requires no ground-truth labels or human feedback. Parameters are never modified.
- **Verification signal:** none required in general (the memory is self-curated); where the stored artefact is code, execution provides a de facto check.
- **What changes:** memory (a persistent cheatsheet) → context.
- **Results that matter:** Claude 3.5 Sonnet's AIME accuracy **more than doubled** once it retained algebraic insights across questions; GPT-4o on Game of 24 went from **10% to 99%** after discovering and reusing a Python solution; on arithmetic-error-prone tasks both models reached near-perfect accuracy against baselines stagnating near 50%; +9% GPQA-Diamond and +8% MMLU-Pro for Claude.
- **Limitations / criticisms:** Self-curated memory with no verifier is exactly the biased-curator setting [BlindCurator] (Topic 1) shows can silently fail; the Game of 24 result is really "the model wrote a solver once and reused it", which is tool creation rather than reasoning improvement; no study of memory growth over long horizons ([LibraryDrift]).
- **Gain type:** **(b) elicitation** for the reasoning gains, but the Game-of-24 case is worth stating carefully: reusing a *verified program* changes what the system reliably does, even though the model is unchanged. Under the "system vs model" reading this is a system-level capability gain — the distinction the FYP's argument turns on.
- **Relevance to this FYP (1–5) and why:** **5.** This is the cheapest, most directly implementable frozen-weights mechanism in the corpus, and the 10%→99% result is the corpus's clearest demonstration that *persisting a verified artefact* beats persisting advice. The ARC-AGI-3 analogue is obvious: store the executable world model, not the lesson learned.
- **Reusable structure:** Self-curated, concise, transferable memory entries with reuse at inference — plus the FYP's necessary addition of an acceptance check before an entry is admitted.
- **BibTeX:** 

```bibtex
@misc{suzgun2025dynamic,
  title         = {{Dynamic Cheatsheet: Test-Time Learning with Adaptive Memory}},
  author        = {Suzgun, Mirac and Yuksekgonul, Mert and Bianchi, Federico and Jurafsky, Dan and Zou, James},
  year          = {2025},
  eprint        = {2504.07952},
  archivePrefix = {arXiv},
  primaryClass  = {cs.LG},
  url           = {https://arxiv.org/abs/2504.07952}
}
```

### [AdaMEM] — AdaMEM: Test-Time Adaptive Memory for Language Agents
- **Authors / Year / Venue:** Yunxiang Zhang, Yiheng Li, Ali Payani, Lu Wang / 2026 / ICML 2026 (venue stated on the arXiv record).
- **Link:** arXiv:2606.05684
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2606.05684.json`); the comment field states "ICML 2026".
- **Type:** method
- **Problem:** Most agent memory systems retrieve only at episode start, so the guidance an agent carries becomes progressively misaligned as a long-horizon task unfolds.
- **Method:** A hybrid memory architecture. A **long-term trajectory memory** of raw experiences is collected offline; a **short-term strategy memory** is generated on the fly during the episode to guide the next decisions. Retrieval is therefore continuous rather than one-shot, and the balance between the two memories trades token efficiency against adaptability, giving an explicit inference-compute dial. No online parameter updates. A separate fine-tuning technique (STEP-MFT) trains the policy to synthesise strategies from retrieved experience — that part is not frozen-weights.
- **Verification signal:** environment reward (ALFWorld, WebShop, HotpotQA task outcomes).
- **What changes:** memory (long-term and short-term) → context; optionally weights via STEP-MFT.
- **Results that matter:** Relative gains of up to **13% on ALFWorld and 11% on WebShop** over static memory baselines, with consistent gains on agentic search over HotpotQA; STEP-MFT adds further improvement.
- **Limitations / criticisms:** The long-term memory is collected offline, so the fully frozen configuration still needs a prior data-collection phase; gains are relative and moderate; no long-horizon memory-growth study.
- **Gain type:** **(b) elicitation.** The base policy is unchanged; better-timed retrieval surfaces behaviour it already had.
- **Relevance to this FYP (1–5) and why:** **4.** The specific defect it fixes — guidance retrieved once at the start goes stale as the episode unfolds — is *the* long-horizon failure in ARC-AGI-3, where the agent's understanding of the game changes level by level. The short-term/long-term split is straightforward to implement over replay logs.
- **Reusable structure:** Mid-episode re-retrieval with an on-the-fly strategy memory, and the explicit token-efficiency/adaptability dial — which in ARC-AGI-3 becomes a deliberation-versus-actions trade-off that the scoring metric makes measurable.
- **BibTeX:** 

```bibtex
@misc{zhang2026adamem,
  title         = {{AdaMEM: Test-Time Adaptive Memory for Language Agents}},
  author        = {Zhang, Yunxiang and Li, Yiheng and Payani, Ali and Wang, Lu},
  year          = {2026},
  eprint        = {2606.05684},
  archivePrefix = {arXiv},
  primaryClass  = {cs.AI},
  url           = {https://arxiv.org/abs/2606.05684}
}
```

### [FrozenControl] — A Control System, a Dataset, and a Recipe for Making Frozen LLM Agents Learn a Domain
- **Authors / Year / Venue:** Debjyoti Paul / 2026 / arXiv preprint (record comment: 8 pages, 1 figure, 3 tables; code and dataset released).
- **Link:** arXiv:2607.25415
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2607.25415.json`).
- **Type:** method
- **Problem:** Harness self-optimisation approaches either need an expensive code-search loop or unconstrained self-modifying code, neither of which is auditable or usable behind a fully black-box model API.
- **Method:** A deliberately narrow alternative: treat the harness as a **small, fixed, human-legible action space** (prompt template, tool set, memory/retrieval layer, planning strategy, verification policy) and learn a *policy over that action space* online with classic sample-efficient RL — an ε-greedy contextual bandit and REINFORCE — scored against a multi-objective reward combining task success, verifier score, policy compliance, cost, latency, and an unsupported-claim penalty. DSPy provides the context assembler and the strongest non-adaptive baseline. Evaluated across tool-use, HumanEval and HotpotQA, on two model providers.
- **Verification signal:** executable check plus a composite multi-objective reward including verifier score and cost.
- **What changes:** a policy over harness configurations (scaffold selection); model weights frozen and black-box.
- **Results that matter:** The contribution is the released control-system code, cross-domain verifiable task suite, full trajectory/reward-decomposition logs, and a provider-agnostic deployment recipe. The abstract reports no headline accuracy number, so none is quoted here.
- **Limitations / criticisms:** Single-author preprint with no peer-review record; a bandit over a small fixed action space cannot invent new harness components, which is precisely what [DGM]/[DarwinX] do; the paper's cited motivating systems (Meta-Harness, HyperAgents) were **not independently verified in this survey** and should not be cited second-hand.
- **Gain type:** **(b) elicitation** — selecting among pre-existing harness configurations for a frozen model.
- **Relevance to this FYP (1–5) and why:** **4.** It is the most *auditable* point on the self-improvement spectrum, and auditability matters here: ARC Prize requires open-sourcing for prize eligibility, and a legible bandit over a small harness action space is far easier to defend in an FYP than unconstrained self-modifying code. The multi-objective reward including **cost** is also the right shape for an efficiency-scored benchmark.
- **Reusable structure:** Bandit/REINFORCE over a small enumerated harness action space, with a multi-objective reward that prices actions and latency alongside success — a low-risk first version of the FYP's loop.
- **BibTeX:** 

```bibtex
@misc{paul2026control,
  title         = {{A Control System, a Dataset, and a Recipe for Making Frozen LLM Agents Learn a Domain}},
  author        = {Paul, Debjyoti},
  year          = {2026},
  eprint        = {2607.25415},
  archivePrefix = {arXiv},
  primaryClass  = {cs.AI},
  url           = {https://arxiv.org/abs/2607.25415}
}
```

### [Twin] — Twin: Playing an Unknown Game with a Test-Time Digital Twin
- **Authors / Year / Venue:** Alexy Skoutnev, Kirill Acharya, Gaston Longhitano, Madeleine Udell, Kevin Ellis, Iddo Drori / 2026 / arXiv preprint (record comment lists a project site with action-by-action replays of all 25 runs, and code).
- **Link:** arXiv:2608.14490
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2608.14490.json`).
- **Type:** method
- **Problem:** Playing ARC-AGI-3 games whose rules and goals are hidden, without hand-engineering a model per game.
- **Method:** A frozen frontier coding agent **writes an executable world model** — a digital twin — for the game it is playing. The harness enforces a hard discipline: an action is not taken until the program reproduces *every* previously observed transition. Each mismatch between prediction and reality becomes a counterexample used to repair the model. Planning happens inside the twin, so search costs no scored actions. Goal inference is separate from dynamics inference and is done by search when it cannot be inferred directly.
- **Verification signal:** executable check — exact replay validation of the world model against the recorded transition history. This is the strongest verifier available in this benchmark and it is free.
- **What changes:** scaffold artefacts (the generated world-model program) and context; **weights frozen**.
- **Results that matter:** Clears **179/183 levels (97.8%)**, more efficiently than humans on 158/179 (88.3%), inferring the goal before any reward on 156 levels (87.2%). The decomposition is the headline: the base model played directly scores **7.8%**; an off-the-shelf harness raises the *same* model to **61.1%**; the twin world model raises it to **93.3%**, clearing 23/25 games. The authors' conclusion is that building a usable world model is easier than expected and **inferring the goal is the harder problem**.
- **Limitations / criticisms:** Public 25-game set only — no private-set result; relies on a frontier coding agent, so the harness contribution and the model's strength are not separable across model generations; [BenchmarkValidity] argues the public set is not discriminative, and [WMAblation] argues these results indicate public-set saturation rather than general capability.
- **Gain type:** **(a) new capability at the system level**, and the cleanest such demonstration in this corpus: the same frozen model goes 7.8% → 93.3% with no weight change, and the intermediate 61.1% figure separates generic harness from the specific world-model mechanism. Whether the *model* gained capability is a different question — it did not — which is exactly why the model/system distinction has to be stated explicitly.
- **Relevance to this FYP (1–5) and why:** **5.** This is the most important paper in the corpus for the FYP. It is the benchmark, frozen weights, and a decomposition (7.8 / 61.1 / 93.3) that quantifies the harness contribution directly. It also relocates the open problem: dynamics inference is close to solved on the public set; **goal inference is not**.
- **Reusable structure:** Replay-consistency gating (no action until the model reproduces all observed transitions) — adopt directly; counterexample-driven model repair; and the three-point decomposition (bare model / generic harness / proposed mechanism) as the mandatory reporting format for any ARC-AGI-3 claim.
- **BibTeX:** 

```bibtex
@misc{skoutnev2026twin,
  title         = {{Twin: Playing an Unknown Game with a Test-Time Digital Twin}},
  author        = {Skoutnev, Alexy and Acharya, Kirill and Longhitano, Gaston and Udell, Madeleine and Ellis, Kevin and Drori, Iddo},
  year          = {2026},
  eprint        = {2608.14490},
  archivePrefix = {arXiv},
  primaryClass  = {cs.AI},
  url           = {https://arxiv.org/abs/2608.14490}
}
```

### [Tycho] — Tycho: Active Abstraction with Programmatic World Models for ARC-AGI-3
- **Authors / Year / Venue:** Jens Lehmann, Andrei Aioanei, Sahar Vahdati / 2026 / arXiv preprint (record comment: 52 pages, 18 figures, 17 tables; open-source implementation).
- **Link:** arXiv:2607.28287
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2607.28287.json`).
- **Type:** method / empirical study
- **Problem:** When is it worth building or repairing a world model at all, given that every interaction costs scored actions?
- **Method:** ARC-AGI-3 environments are formalised as *parameterised rendered deterministic Moore machines*. Tycho separates actionable observations from animation, level-completion and game-over frames, and from that structured history an agent may model, test, plan with, repair, or **bypass** a free-form executable hypothesis. Four orchestration policies are compared under matched inference budgets on all 25 public games. The paper names the resulting joint problem **active abstraction**: generating a testable model from costly interaction *and* deciding when acquiring or using it is worth the cost.
- **Verification signal:** executable check (transition match against observed dynamics), with the explicit finding that transition match is *not* sufficient.
- **What changes:** scaffold artefacts (programmatic world models) and orchestration policy; weights frozen.
- **Results that matter:** Actor-requested delegation to a model builder gives the best observed mean RHAE, **88.49**; with that policy, GPT-5.6 Sol and Opus 5 both reach **100.00 RHAE**, completing all 183 levels, with Opus 5 using **61% fewer scored actions than the aggregate official human baselines**. Automatic repair after verification failures produces *more accurate* models yet reaches only 83.07 RHAE — a direct dissociation between model fidelity and performance.
- **Limitations / criticisms:** One matched run per policy — thin statistics for a four-way comparison; public set only; results depend on models released after the games, so contamination and saturation cannot be excluded.
- **Gain type:** **(a) new capability at the system level**, with the same model/system caveat as [Twin]; the paper's own dissociation result argues the gain comes from *orchestration*, not from better modelling.
- **Relevance to this FYP (1–5) and why:** **5.** Two contributions transfer. First, the formalisation of these environments as deterministic Moore machines gives the FYP a precise object to generate variants of — which is what a Topic-2 teacher needs. Second, "active abstraction" names the real research problem under an efficiency metric: not *can* you build a model, but *should* you, given what it costs in actions.
- **Reusable structure:** The cost-aware decision to model / test / plan / repair / bypass, and the finding that transition-match accuracy is the wrong objective — a warning that should shape the FYP's reward design.
- **BibTeX:** 

```bibtex
@misc{lehmann2026tycho,
  title         = {{Tycho: Active Abstraction with Programmatic World Models for ARC-AGI-3}},
  author        = {Lehmann, Jens and Aioanei, Andrei and Vahdati, Sahar},
  year          = {2026},
  eprint        = {2607.28287},
  archivePrefix = {arXiv},
  primaryClass  = {cs.AI},
  url           = {https://arxiv.org/abs/2607.28287}
}
```

### [ExecWM] — Executable World Models for ARC-AGI-3 in the Era of Coding Agents
- **Authors / Year / Venue:** Sergey Rodionov / 2026 / **AGI-2026** (acceptance stated on the arXiv record; DOI 10.1007/978-3-032-33195-3_15).
- **Link:** arXiv:2605.05138
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2605.05138.json`); the record carries both the DOI and the AGI-2026 acceptance note.
- **Type:** method / empirical study
- **Problem:** Building an ARC-AGI-3 agent that carries no game-specific information, and demonstrating that it carries none.
- **Method:** A coding agent maintains an executable Python world model, verifies it against previous observations, **refactors it toward simpler abstractions as a practical proxy for an MDL-like simplicity bias**, and plans through the model before acting. The controller, interfaces and verifier programs are scripted, but nothing game-specific appears in prompts, workspace or controller. Unusually, the paper audits **unintended information channels**, describes earlier vulnerable harnesses, and explains how the current harness closes observed leakage.
- **Verification signal:** executable check — verifier programs comparing the world model against observations.
- **What changes:** scaffold artefacts (the world-model program); weights frozen; each playthrough starts from a fresh agent instance and clean workspace.
- **Results that matter:** On the 25 public games, GPT-5.5 at high reasoning effort fully solved **15 games with mean per-game RHAE 58.12%**; GPT-5.4 solved 8 with RHAE 41.29%. Private-set performance is explicitly untested.
- **Limitations / criticisms:** Public set only, single-author, and the author is explicit that private results remain unknown; the strong dependence on backbone version (5.4 → 5.5 nearly doubles the score) means the harness contribution is entangled with model capability.
- **Gain type:** **(c) unclear** as stated — the paper does not isolate how much comes from the scaffold versus the backbone. Its own follow-up ([WMAblation]) is what resolves this, and the answer is uncomfortable.
- **Relevance to this FYP (1–5) and why:** **5.** The leakage audit is the methodological contribution the FYP should copy verbatim: an agent with broad system access on a benchmark whose value depends on novelty can trivially cheat, and most papers do not check. The MDL-style refactoring proxy also connects this line directly to [CompressARC].
- **Reusable structure:** The information-channel audit (enumerate what the agent could read, show it did not), fresh-instance/clean-workspace protocol, and simplicity-driven refactoring of the world model.
- **BibTeX:** 

```bibtex
@misc{rodionov2026executable,
  title         = {{Executable World Models for ARC-AGI-3 in the Era of Coding Agents}},
  author        = {Rodionov, Sergey},
  year          = {2026},
  eprint        = {2605.05138},
  archivePrefix = {arXiv},
  primaryClass  = {cs.AI},
  url           = {https://arxiv.org/abs/2605.05138},
  note          = {Accepted for publication at AGI-2026},
  doi           = {10.1007/978-3-032-33195-3\_15}
}
```

### [WMAblation] — Do Coding Agents Need Executable World Models, Simplification, and Verification to Solve ARC-AGI-3?
- **Authors / Year / Venue:** Sergey Rodionov / 2026 (v2 2026-08) / arXiv preprint (record comment: 45 pages, 3 figures).
- **Link:** arXiv:2607.15439
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2607.15439.json`).
- **Type:** empirical study (ablation)
- **Problem:** [ExecWM] bundled executable world modelling, prompted simplification and exact replay verification, leaving their individual contributions unknown.
- **Method:** Four Codex-based variants are compared — textual; flexible-interface executable; executable plus simplification prompts; and fixed-interface with simplification *and* exact replay verification — across two model versions and two reasoning-effort levels on the 25 public games, with exploratory follow-ups on a newer model.
- **Verification signal:** executable check (exact replay verification) in the strongest variant; the study measures what that verification is worth.
- **What changes:** scaffold configuration; weights frozen.
- **Results that matter:** Three findings that should discipline the whole topic. (1) **Every variant improves as model capability and reasoning effort increase, and these gains often exceed the differences between variants** — the harness mechanisms matter less than the backbone. (2) Requiring an executable deliverable is **not** universally beneficial: the plain textual variant beats the flexible-interface executable variant in both conditions on one model. (3) On the newest model, the verification variant completes every public level at ~99% human-relative action efficiency using fewer than half the human baseline's actions — but at maximum effort the *textual* variant also completes every level, with 41% fewer actions than the human baseline. The author's conclusion is explicit: because the newest model postdates the games and held-out performance is untested, the results indicate **public-set saturation only**.
- **Limitations / criticisms:** Single author, public set only, and one run per configuration in places; but the honesty of the negative framing is itself the contribution.
- **Gain type:** **(b) elicitation** — this paper's central result is that most of the apparent scaffold gain in this line is really backbone capability being elicited, and that the imposed mechanisms are not required once the model is strong enough.
- **Relevance to this FYP (1–5) and why:** **5.** This is the corpus's most important discipline check on Topic 1's optimism, delivered on the FYP's own benchmark by the author of the system being ablated. Any ARC-AGI-3 harness claim must now be accompanied by a model-capability sweep, or it is not interpretable.
- **Reusable structure:** The variant × model-version × reasoning-effort grid — the FYP should adopt this exact experimental design so that harness effects and backbone effects are separable, and should report the public/private distinction as bluntly as this paper does.
- **BibTeX:** 

```bibtex
@misc{rodionov2026coding,
  title         = {{Do Coding Agents Need Executable World Models, Simplification, and Verification to Solve ARC-AGI-3?}},
  author        = {Rodionov, Sergey},
  year          = {2026},
  eprint        = {2607.15439},
  archivePrefix = {arXiv},
  primaryClass  = {cs.AI},
  url           = {https://arxiv.org/abs/2607.15439}
}
```
---

## §3 Test-time training — a clearly separated sub-bucket (weights **do** change)

> These three entries are included because the FYP must compare against them and because the ARC
> literature routinely conflates them with frozen-weight methods. In all three, parameters are
> updated at inference time. They are **not** evidence for capability gain without parameter updates.

### [TTT-FewShot] — The Surprising Effectiveness of Test-Time Training for Few-Shot Learning
- **Authors / Year / Venue:** Ekin Akyürek, Mehul Damani, Adam Zweiger, Linlu Qiu, Han Guo, Jyothish Pari, Yoon Kim, Jacob Andreas / 2024 (v2 2025-03) / arXiv preprint (record comment: "Preprint").
- **Link:** arXiv:2411.07279
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2411.07279.json`). Note the title on the record is "...for Few-Shot Learning", not "...for Abstract Reasoning" as sometimes cited.
- **Type:** empirical study
- **Problem:** Whether in-context examples are enough for structurally novel tasks, or whether the model must actually be updated on them.
- **Method:** Test-time training temporarily updates model parameters during inference using a loss derived from the input data itself — here, the task's own in-context demonstration pairs, augmented. The comparison that matters is TTT against *fine-tuned* baselines and against standard in-context prompting on the same examples.
- **Verification signal:** the task's own input/output pairs act as the training signal; final correctness is checked against held-out outputs.
- **What changes:** **weights**, temporarily, per task.
- **Results that matter:** On ARC, TTT with in-context examples gives up to **6× higher accuracy than fine-tuned baselines**, reaching **53.0%** on the public validation set with an 8B model and **61.9%** when ensembled with program synthesis — described as matching average human performance. On BIG-Bench Hard, 10-shot TTT beats standard few-shot prompting by 7.3 points (50.5% → 57.8%).
- **Limitations / criticisms:** Weights change, so it is not a frozen-weights method; TTT is expensive per task; ARC-AGI-1 static format, not the interactive benchmark; the "matching average human performance" comparison is on a specific public split.
- **Gain type:** **not applicable / out of scope by construction** — parameters are updated. It is included precisely as the contrast case: the paper's own framing is that in-context learning is *insufficient* for structurally novel tasks and weight updates are needed. That is the strongest direct challenge to the FYP's premise in this corpus.
- **Relevance to this FYP (1–5) and why:** **5.** It is the position the FYP must argue against, or concede. The honest reading: on *static* ARC, TTT beats in-context adaptation decisively. Whether that survives the move to an interactive setting — where the "training examples" are self-collected transitions rather than given pairs — is an open question, and one the project could actually answer.
- **Reusable structure:** The TTT arm as a mandatory baseline; and its data construction (build a training set from the task's own examples) transposed to ARC-AGI-3 as "build a training set from this game's own observed transitions".
- **BibTeX:** 

```bibtex
@misc{akyrek2024surprising,
  title         = {{The Surprising Effectiveness of Test-Time Training for Few-Shot Learning}},
  author        = {Akyürek, Ekin and Damani, Mehul and Zweiger, Adam and Qiu, Linlu and Guo, Han and Pari, Jyothish and Kim, Yoon and Andreas, Jacob},
  year          = {2024},
  eprint        = {2411.07279},
  archivePrefix = {arXiv},
  primaryClass  = {cs.AI},
  url           = {https://arxiv.org/abs/2411.07279}
}
```

### [CompressARC] — ARC-AGI Without Pretraining
- **Authors / Year / Venue:** Isaac Liao, Albert Gu / 2025 / arXiv preprint (no venue on the record).
- **Link:** arXiv:2512.06104
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2512.06104.json`).
- **Type:** method / position
- **Problem:** Whether ARC-AGI requires capabilities derived from massive pretraining at all.
- **Method:** CompressARC is a **76K-parameter** model with **no pretraining** that solves puzzles by minimising the description length (MDL) of the target puzzle purely during inference. Training happens on a single sample — the target puzzle itself, with the solution removed — and the model does not train on the provided ARC-AGI training set at all.
- **Verification signal:** the compression objective itself; final answers checked against the puzzle's held-out output.
- **What changes:** **weights**, optimised from scratch per puzzle at inference time.
- **Results that matter:** **20% of ARC-AGI-1 evaluation puzzles** solved under these conditions — where, as the authors note, one would not ordinarily expect any puzzles to be solvable.
- **Limitations / criticisms:** Weights change (per puzzle), so it is not frozen-weights; 20% is far below the state of the art; ARC-AGI-1 static format; per-puzzle optimisation is slow.
- **Gain type:** **not applicable / out of scope by construction** — but it makes an argument that reframes the whole section: the capability came from an *objective* (MDL), not from prior knowledge. This is the cleanest evidence in the corpus that competence on these tasks need not be elicited from a pretrained prior at all.
- **Relevance to this FYP (1–5) and why:** **4.** It is the strongest existence proof that a tiny model with the right inductive objective can do non-trivial ARC work, which matters for a compute-constrained project. The MDL/simplicity principle also reappears as the refactoring bias in [ExecWM], so the idea does transfer to the interactive setting — as a bias on *world models*, not on grids.
- **Reusable structure:** Description-length minimisation as a selection criterion between competing hypotheses — for ARC-AGI-3, prefer the shortest world-model program consistent with all observed transitions.
- **BibTeX:** 

```bibtex
@misc{liao2025arcagi,
  title         = {{ARC-AGI Without Pretraining}},
  author        = {Liao, Isaac and Gu, Albert},
  year          = {2025},
  eprint        = {2512.06104},
  archivePrefix = {arXiv},
  primaryClass  = {cs.LG},
  url           = {https://arxiv.org/abs/2512.06104}
}
```

### [TRM] — Less is More: Recursive Reasoning with Tiny Networks
- **Authors / Year / Venue:** Alexia Jolicoeur-Martineau / 2025 / arXiv preprint (no venue on the record).
- **Link:** arXiv:2510.04871
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2510.04871.json`). A follow-up analysis, *Tiny Recursive Models on ARC-AGI-1: Inductive Biases, Identity Conditioning, and Test-Time Compute* (arXiv:2512.11847, Roye-Azar et al.), was also verified and cached; it is listed in `adjacent.md`.
- **Type:** method
- **Problem:** Whether recursive reasoning in a very small network can substitute for scale on hard puzzle tasks.
- **Method:** TRM simplifies the Hierarchical Reasoning Model to a **single tiny network with two layers**, applied recursively, trained on roughly 1,000 examples. The capability comes from the recursive application of a small function rather than from parameter count or pretraining.
- **Verification signal:** supervised targets (puzzle solutions) during training.
- **What changes:** **weights**, trained conventionally.
- **Results that matter:** With **7M parameters**, 45% test accuracy on ARC-AGI-1 and 8% on ARC-AGI-2 — higher than most LLMs (the paper names DeepSeek R1, o3-mini, Gemini 2.5 Pro) at **less than 0.01% of the parameters**.
- **Limitations / criticisms:** Trained per task family and not an agent; static ARC only; the follow-up analysis (arXiv:2512.11847) examines how much of the result rests on inductive biases, identity conditioning and test-time compute rather than on recursion itself.
- **Gain type:** **not applicable** — supervised training. Included because it is the standing counter-argument to "capability must come from a large pretrained prior".
- **Relevance to this FYP (1–5) and why:** **3.** No mechanism transfers to an interactive, goal-unknown setting, and TRM needs supervised input/output pairs that ARC-AGI-3 does not provide. It matters as the citation for "small models can do ARC", which is the premise the FYP's small-model framing rests on, and as a reminder that this premise has so far only been demonstrated in the *static* format.
- **Reusable structure:** Nothing directly. Its value is as a scale reference point in the write-up: 7M parameters, 45% on ARC-AGI-1.
- **BibTeX:** 

```bibtex
@misc{jolicoeurmartineau2025recursive,
  title         = {{Less is More: Recursive Reasoning with Tiny Networks}},
  author        = {Jolicoeur-Martineau, Alexia},
  year          = {2025},
  eprint        = {2510.04871},
  archivePrefix = {arXiv},
  primaryClass  = {cs.LG},
  url           = {https://arxiv.org/abs/2510.04871}
}
```

---

## §4 Critical and negative results: is any of this new capability?

### [RLVR-Elicitation] — Does Reinforcement Learning Really Incentivize Reasoning Capacity in LLMs Beyond the Base Model?
- **Authors / Year / Venue:** Yang Yue, Zhiqi Chen, Rui Lu, Andrew Zhao, Zhaokai Wang, Yang Yue, Shiji Song, Gao Huang / 2025 (v5 2025-11) / **NeurIPS 2025 Oral**; ICML 2025 AI4MATH workshop best paper (journal-ref on the arXiv record).
- **Link:** arXiv:2504.13837
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2504.13837.json`); the journal-ref field states the NeurIPS 2025 Oral and the workshop best-paper award.
- **Type:** empirical study
- **Problem:** RLVR is believed to give models genuinely new reasoning abilities. Does it?
- **Method:** Systematically probe the reasoning boundary of RLVR-trained models across model families, RL algorithms and maths/coding/visual benchmarks, using **pass@k at large k** as the metric — the measurement that distinguishes "the model can produce this answer" from "the model produces this answer first". Coverage and perplexity analyses then locate where the reasoning paths come from.
- **Verification signal:** mechanical answer checking (the "verifiable rewards" of RLVR).
- **What changes:** weights (that is the thing being audited); the finding is about what the weights gain.
- **Results that matter:** RLVR-trained models beat their base models at small k, but **base models achieve higher pass@k at large k**. Coverage and perplexity analyses show the reasoning abilities originate from and are **bounded by** the base model. Six popular RLVR algorithms perform similarly and remain far from optimally exploiting the base model. By contrast, **distillation does introduce new reasoning patterns** from a teacher.
- **Limitations / criticisms:** Large-k pass@k rewards the base model's higher entropy, which some argue is not a fair notion of capability; results are on established benchmarks that may be contaminated; the paper's own framing is that current RLVR setups, not RL in principle, are the limitation.
- **Gain type:** **(b) elicitation — argued as a general result.** This is the paper that makes elicitation-vs-acquisition an empirical question with a method attached.
- **Relevance to this FYP (1–5) and why:** **5.** It is the central citation of the FYP's Topic-3 argument and it sets the evidentiary bar: any claim of new capability must show pass@k at large k, not pass@1. Its closing suggestion — that **multi-turn agent–environment interaction** may be what unlocks genuine capability gain — is a direct argument for why an interactive benchmark like ARC-AGI-3 is the right place to test this, and a strong motivation sentence for the FYP.
- **Reusable structure:** Large-k pass@k as the capability-boundary test, and the base-model-as-upper-bound framing. The ARC-AGI-3 analogue: run the unaided base agent for many episodes and check whether the harness ever solves a game the base agent never solves at any budget.
- **BibTeX:** 

```bibtex
@misc{yue2025reinforcement,
  title         = {{Does Reinforcement Learning Really Incentivize Reasoning Capacity in LLMs Beyond the Base Model?}},
  author        = {Yue, Yang and Chen, Zhiqi and Lu, Rui and Zhao, Andrew and Wang, Zhaokai and Yue, Yang and Song, Shiji and Huang, Gao},
  year          = {2025},
  eprint        = {2504.13837},
  archivePrefix = {arXiv},
  primaryClass  = {cs.AI},
  url           = {https://arxiv.org/abs/2504.13837},
  note          = {NeurIPS 2025 Oral; ICML 2025 AI4MATH workshop best paper}
}
```

### [ReasoningWithSampling] — Reasoning with Sampling: Your Base Model is Smarter Than You Think
- **Authors / Year / Venue:** Aayush Karan, Yilun Du / 2025 / arXiv preprint (no venue on the record).
- **Link:** arXiv:2510.14901
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2510.14901.json`).
- **Type:** method / empirical study
- **Problem:** If RL's gains are bounded by the base model, can the same gains be had at inference time with no training at all?
- **Method:** An iterative sampling algorithm inspired by MCMC for sampling from *sharpened* distributions, using only the base model's own likelihoods. No training, no curated data, and — importantly — **no verifier**.
- **Verification signal:** none; the model's own likelihood is the only signal.
- **What changes:** nothing persists; the sampling procedure only.
- **Results that matter:** Across different base models, the sampler gives boosts that **nearly match and sometimes outperform RL post-training** on MATH500, HumanEval and GPQA, while **avoiding the diversity collapse over multiple samples that characterises RL post-training**.
- **Limitations / criticisms:** No peer-review record; single-shot tasks with clean answers; not demonstrated in agentic or long-horizon settings; sharpening a distribution cannot add mass where there is none.
- **Gain type:** **(b) elicitation, demonstrated constructively.** If a training-free sampler matches RL, then what RL added was mostly sharpening — which is the [RLVR-Elicitation] thesis proved from the other direction.
- **Relevance to this FYP (1–5) and why:** **4.** Together with [RLVR-Elicitation] it forms the strongest pair of arguments that weight updates are not where the capability is — which is the FYP's licence to freeze the weights and work on the scaffold instead. The diversity-preservation result also connects to Topic 2's collapse problem: sampling-based elicitation does not collapse, whereas RL does.
- **Reusable structure:** The verifier-free sharpened-sampling baseline — a control the FYP should include so that "our loop helped" is not confused with "we sampled better".
- **BibTeX:** 

```bibtex
@misc{karan2025reasoning,
  title         = {{Reasoning with Sampling: Your Base Model is Smarter Than You Think}},
  author        = {Karan, Aayush and Du, Yilun},
  year          = {2025},
  eprint        = {2510.14901},
  archivePrefix = {arXiv},
  primaryClass  = {cs.LG},
  url           = {https://arxiv.org/abs/2510.14901}
}
```

### [MATH-Beyond] — MATH-Beyond: A Benchmark for RL to Expand Beyond the Base Model
- **Authors / Year / Venue:** Prasanna Mayilvahanan, Ricardo Dominguez-Olmedo, Thaddäus Wiedemer, Wieland Brendel / 2025 / arXiv preprint (no venue on the record).
- **Link:** arXiv:2510.11653
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2510.11653.json`).
- **Type:** benchmark
- **Problem:** The elicitation debate cannot be settled on benchmarks that base models already solve under large sampling budgets.
- **Method:** Show first that with enough draws (e.g. pass@1024) many base models already solve nearly all of MATH-500 and AIME 2024 — so RL there can only be sharpening. Then construct **MATH-Beyond**, deliberately built to defeat open-source models up to 8B parameters *even under large sampling budgets*, while drawing problems from existing datasets so the topic distribution stays ordinary high-school maths.
- **Verification signal:** mechanical answer checking.
- **What changes:** n/a — it is a benchmark.
- **Results that matter:** RL-fine-tuned models such as Nemotron-Research-Reasoning-Qwen-1.5B and DeepScaleR-1.5B-Preview **perform poorly on MATH-B at pass@1024**, confirming that current approaches do not reach beyond the base model's support.
- **Limitations / criticisms:** No peer-review record; capped at 8B models; a benchmark defined by what current models fail at will age.
- **Gain type:** n/a — it is the *instrument* for classifying gain type, which is why it belongs here.
- **Relevance to this FYP (1–5) and why:** **4.** It supplies the methodology the FYP needs: to claim capability rather than elicitation, evaluate on tasks the base system fails at under a large budget. ARC-AGI-3's private set is arguably already a MATH-Beyond-style instrument for agents — and [BenchmarkValidity] shows the *public* set is not.
- **Reusable structure:** The construction principle — filter tasks by base-model failure at high k, then measure improvement — as the way to build an honest ARC-AGI-3 evaluation subset.
- **BibTeX:** 

```bibtex
@misc{mayilvahanan2025mathbeyond,
  title         = {{MATH-Beyond: A Benchmark for RL to Expand Beyond the Base Model}},
  author        = {Mayilvahanan, Prasanna and Dominguez-Olmedo, Ricardo and Wiedemer, Thaddäus and Brendel, Wieland},
  year          = {2025},
  eprint        = {2510.11653},
  archivePrefix = {arXiv},
  primaryClass  = {cs.LG},
  url           = {https://arxiv.org/abs/2510.11653}
}
```

### [LimitsResampling] — The Limits of Inference Scaling Through Resampling
- **Authors / Year / Venue:** Benedikt Stroebl, Sayash Kapoor, Arvind Narayanan / 2024 (v3 2026-03) / arXiv preprint (no venue on the record).
- **Link:** arXiv:2411.17501
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2411.17501.json`).
- **Type:** empirical study / theory
- **Problem:** [Monkeys] shows coverage scales with samples where a verifier exists. But real verifiers are imperfect.
- **Method:** Analyse resampling against a verifier with a non-zero false-positive rate. Since resampling cannot reduce the probability of a false positive being accepted, it imposes an **upper bound on achievable accuracy regardless of compute budget**. The analysis is then checked empirically on HumanEval and MBPP, whose unit tests have limited coverage.
- **Verification signal:** the object of study — imperfect executable verifiers (unit tests).
- **What changes:** nothing; the paper is about a ceiling.
- **Results that matter:** A strong correlation between a model's single-sample accuracy and its false-positive rate, so **no amount of inference scaling lets a weaker model match a sufficiently strong model's single-sample accuracy**; empirically, optimal sampling attempts are often **fewer than 10**, because the negative utility of false positives bends the scaling curve downward.
- **Limitations / criticisms:** Code benchmarks with known-weak test suites; assumes false-positive rate is fixed rather than improvable; does not model verifiers that can be strengthened adaptively.
- **Gain type:** **(b) elicitation, with a hard ceiling.** The paper's contribution is showing where elicitation stops paying.
- **Relevance to this FYP (1–5) and why:** **5.** It is the precise counterweight to [Monkeys] and it changes an ARC-AGI-3 design decision: the environment's own score is a near-perfect verifier, so resampling *against the environment* does not suffer this ceiling — but resampling against a **self-authored world model** (as [Twin] and [Tycho] do) does, since a wrong world model is exactly a false-positive generator. This is the argument for [Twin]'s replay-consistency gate.
- **Reusable structure:** Measuring and reporting the verifier's false-positive rate as a first-class experimental quantity; and the "optimal number of attempts" analysis, which under ARC-AGI-3's squared efficiency metric becomes an optimal-actions analysis.
- **BibTeX:** 

```bibtex
@misc{stroebl2024limits,
  title         = {{The Limits of Inference Scaling Through Resampling}},
  author        = {Stroebl, Benedikt and Kapoor, Sayash and Narayanan, Arvind},
  year          = {2024},
  eprint        = {2411.17501},
  archivePrefix = {arXiv},
  primaryClass  = {cs.LG},
  url           = {https://arxiv.org/abs/2411.17501}
}
```

### [InverseScaling] — Inverse Scaling in Test-Time Compute
- **Authors / Year / Venue:** Aryo Pradipta Gema, Alexander Hägele, Runjin Chen, Andy Arditi, Jacob Goldman-Wetzler, Kit Fraser-Taliente, Henry Sleight, Linda Petrini, et al. (14 authors) / 2025 (v2 2025-12) / **TMLR** (12/2025, Featured Certification) — journal reference on the arXiv record.
- **Link:** arXiv:2507.14417
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2507.14417.json`); the journal-ref field states TMLR publication with certification.
- **Type:** empirical study
- **Problem:** Test-time compute is assumed monotonically helpful. Is it?
- **Method:** Construct evaluation tasks in four categories — counting with distractors, regression with spurious features, deduction with constraint tracking, and advanced AI risks — where reasoning length can be varied, then measure accuracy as a function of reasoning length across several frontier model families.
- **Verification signal:** mechanical task correctness.
- **What changes:** nothing; reasoning length is the independent variable.
- **Results that matter:** An **inverse** relationship between test-time compute and accuracy on these tasks, with five distinct failure modes: increasing distraction by irrelevant information; overfitting to problem framings; drift from reasonable priors to spurious correlations; loss of focus on complex deductive tasks; and amplification of concerning behaviours under extended reasoning.
- **Limitations / criticisms:** Tasks are constructed to elicit the effect, so prevalence in natural workloads is unknown; model-family-specific findings may not generalise across versions.
- **Gain type:** n/a — a negative result about the *mechanism* rather than a capability claim.
- **Relevance to this FYP (1–5) and why:** **4.** Directly relevant because ARC-AGI-3 environments are *made of* distractors and constraint tracking — two of the four categories where longer reasoning hurts. It also undercuts the easy assumption from [s1] that the FYP can freely spend tokens because only actions are scored: more deliberation is not free if it degrades the decision.
- **Reusable structure:** Evaluate across a **sweep** of reasoning lengths rather than at one setting — cheap to run, and it turns a hidden confound into a reported curve.
- **BibTeX:** 

```bibtex
@misc{gema2025inverse,
  title         = {{Inverse Scaling in Test-Time Compute}},
  author        = {Gema, Aryo Pradipta and Hägele, Alexander and Chen, Runjin and Arditi, Andy and Goldman-Wetzler, Jacob and Fraser-Taliente, Kit and Sleight, Henry and Petrini, Linda and Michael, Julian and Alex, Beatrice and Minervini, Pasquale and Chen, Yanda and Benton, Joe and Perez, Ethan},
  year          = {2025},
  eprint        = {2507.14417},
  archivePrefix = {arXiv},
  primaryClass  = {cs.AI},
  url           = {https://arxiv.org/abs/2507.14417},
  note          = {Transactions on Machine Learning Research (TMLR); 12/2025; https://openreview.net/forum?id=NXgyHW1c7M}
}
```

### [SelfCorrect] — Large Language Models Cannot Self-Correct Reasoning Yet
- **Authors / Year / Venue:** Jie Huang, Xinyun Chen, Swaroop Mishra, Huaixiu Steven Zheng, Adams Wei Yu, Xinying Song, Denny Zhou / 2023 (v2 2024) / ICLR 2024 (venue stated on the arXiv record).
- **Link:** arXiv:2310.01798
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2310.01798.json`); the comment field states ICLR 2024.
- **Type:** empirical study
- **Problem:** Whether the self-correction loops behind [Self-Refine] and [Reflexion] work when there is no external feedback.
- **Method:** Isolate **intrinsic** self-correction — the model revising its own answer using only its own judgement, with no external signal, and with no oracle telling it when to stop. Prior positive results are re-examined under this stricter protocol on reasoning tasks.
- **Verification signal:** the absence of one is the point.
- **What changes:** nothing persists.
- **Results that matter:** LLMs struggle to self-correct reasoning without external feedback, and **performance sometimes degrades after self-correction**.
- **Limitations / criticisms:** Pre-2024 models; reasoning-specific; the paper's "yet" concedes the finding may not hold for later models — and [Twin]/[Tycho] arguably show it does not, once an *external* replay check is supplied.
- **Gain type:** n/a — a negative result that bounds where elicitation works.
- **Relevance to this FYP (1–5) and why:** **5.** It draws the line the FYP must respect: reflection loops need an external check, and the whole design should be arranged so that the environment provides it. It is also the reason to be suspicious of any component that grades itself — the same conclusion [BlindCurator] reaches from the skill-library side.
- **Reusable structure:** The intrinsic-versus-extrinsic feedback ablation: run the FYP's loop once with environment verification and once with the agent's own judgement, and report the gap.
- **BibTeX:** 

```bibtex
@misc{huang2023large,
  title         = {{Large Language Models Cannot Self-Correct Reasoning Yet}},
  author        = {Huang, Jie and Chen, Xinyun and Mishra, Swaroop and Zheng, Huaixiu Steven and Yu, Adams Wei and Song, Xinying and Zhou, Denny},
  year          = {2023},
  eprint        = {2310.01798},
  archivePrefix = {arXiv},
  primaryClass  = {cs.CL},
  url           = {https://arxiv.org/abs/2310.01798}
}
```

### [GSM-Symbolic] — GSM-Symbolic: Understanding the Limitations of Mathematical Reasoning in Large Language Models
- **Authors / Year / Venue:** Iman Mirzadeh, Keivan Alizadeh, Hooman Shahrokhi, Oncel Tuzel, Samy Bengio, Mehrdad Farajtabar / 2024 (v2 2025-08) / ICLR (camera-ready stated on the arXiv record).
- **Link:** arXiv:2410.05229
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2410.05229.json`); the comment field states "ICLR camera ready".
- **Type:** benchmark / empirical study
- **Problem:** GSM8K scores have risen sharply; has reasoning improved, or has the benchmark been absorbed?
- **Method:** Generate many instantiations of the same question from symbolic templates, so that surface details and numeric values can be varied while the required reasoning is held fixed. Then measure variance across instantiations, sensitivity to changing only the numbers, and sensitivity to adding clauses.
- **Verification signal:** mechanical answer checking against the template's ground truth.
- **What changes:** nothing; it is a measurement instrument.
- **Results that matter:** Noticeable variance across instantiations of the same question; performance declines when **only the numerical values change**; performance degrades as the number of clauses grows; adding a single relevant-looking but irrelevant clause causes drops of **up to 65%** across all state-of-the-art models tested.
- **Limitations / criticisms:** Grade-school maths only; the authors' inference that models "replicate reasoning steps from training data" is a hypothesis rather than a demonstrated mechanism.
- **Gain type:** n/a — it is a contamination/fragility instrument, and it is the template for how to build one.
- **Relevance to this FYP (1–5) and why:** **4.** Its method is the transferable part. ARC-AGI-3 environments are exactly the kind of artefact that can be re-instantiated with surface variation and fixed underlying rules, so a GSM-Symbolic-style perturbation suite is a realistic and genuinely novel contribution an FYP could make — and it would answer the contamination question the ARC Prize team raises for the interactive setting.
- **Reusable structure:** Symbolic templating with held-fixed reasoning and varied surface form, plus the irrelevant-clause perturbation — both directly constructible in a grid environment.
- **BibTeX:** 

```bibtex
@misc{mirzadeh2024gsmsymbolic,
  title         = {{GSM-Symbolic: Understanding the Limitations of Mathematical Reasoning in Large Language Models}},
  author        = {Mirzadeh, Iman and Alizadeh, Keivan and Shahrokhi, Hooman and Tuzel, Oncel and Bengio, Samy and Farajtabar, Mehrdad},
  year          = {2024},
  eprint        = {2410.05229},
  archivePrefix = {arXiv},
  primaryClass  = {cs.LG},
  url           = {https://arxiv.org/abs/2410.05229}
}
```

### [IllusionOfThinking] — The Illusion of Thinking: Understanding the Strengths and Limitations of Reasoning Models via the Lens of Problem Complexity
- **Authors / Year / Venue:** Parshin Shojaee, Iman Mirzadeh, Keivan Alizadeh, Maxwell Horton, Samy Bengio, Mehrdad Farajtabar / 2025 (v3 2025-11) / **NeurIPS 2025** (venue stated on the arXiv record).
- **Link:** arXiv:2506.06941
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2506.06941.json`); the comment field states "NeurIPS 2025. camera-ready version".
- **Type:** empirical study
- **Problem:** Reasoning-model evaluations focus on final-answer accuracy on contaminated maths and coding benchmarks, and say nothing about the reasoning traces.
- **Method:** Use **controllable puzzle environments** in which complexity can be varied precisely while the logical structure stays constant, and analyse not only final answers but the internal reasoning traces, comparing reasoning models against standard models at matched inference compute.
- **Verification signal:** mechanical puzzle correctness, plus trace inspection.
- **What changes:** nothing; it is a measurement study.
- **Results that matter:** **Complete accuracy collapse beyond a complexity threshold**; a counterintuitive scaling limit where reasoning effort rises with complexity then *declines* despite remaining token budget; and three regimes — standard models win at low complexity, reasoning models win at medium, both collapse at high. The models fail to use explicit algorithms and reason inconsistently across scales.
- **Limitations / criticisms:** Puzzle environments are artificial and the paper's setup drew public methodological criticism after release regarding output-length limits on the largest instances; the results are about specific model families at a specific time.
- **Gain type:** n/a — a limitation study that constrains what "reasoning improvement" can mean.
- **Relevance to this FYP (1–5) and why:** **4.** ARC-AGI-3 is precisely a controllable-complexity puzzle environment with levels that escalate, so the collapse-beyond-threshold finding predicts what the FYP will see on later levels — and the effort-declines-with-complexity result predicts a specific, checkable pathology. The evaluation design (vary complexity, hold structure fixed, inspect traces) is the right shape for the FYP's analysis chapter.
- **Reusable structure:** Complexity-controlled evaluation with trace analysis, and reporting *effort* (actions, tokens) alongside accuracy as complexity rises — which ARC-AGI-3's per-level structure supports natively.
- **BibTeX:** 

```bibtex
@misc{shojaee2025illusion,
  title         = {{The Illusion of Thinking: Understanding the Strengths and Limitations of Reasoning Models via the Lens of Problem Complexity}},
  author        = {Shojaee, Parshin and Mirzadeh, Iman and Alizadeh, Keivan and Horton, Maxwell and Bengio, Samy and Farajtabar, Mehrdad},
  year          = {2025},
  eprint        = {2506.06941},
  archivePrefix = {arXiv},
  primaryClass  = {cs.AI},
  url           = {https://arxiv.org/abs/2506.06941}
}
```

### [BenchmarkValidity] — Explore Before You Solve: The Speed–Depth Trade-off in Epistemic Agents for ARC-AGI-3
- **Authors / Year / Venue:** Liew Keong Han / 2026 / arXiv preprint (record comment: 22 pages, 3 figures; code released CC0).
- **Link:** arXiv:2605.25931
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2605.25931.json`).
- **Type:** empirical study / benchmark critique
- **Problem:** Whether the public ARC-AGI-3 set actually measures the exploration and goal inference it claims to.
- **Method:** Systematically attack all 25 public games with deliberately non-intelligent strategies and record what suffices. Then present AERA, a three-phase EXPLORE / VERIFY / PLAN agent, and formalise a Speed–Depth trade-off in which the benchmark's quadratic scoring appears as a second-order penalty for deviating from the Pareto frontier between action efficiency and information gain.
- **Verification signal:** environment reward (the official RHAE score).
- **What changes:** nothing persistent in the critique; the AERA agent is a scripted three-phase harness.
- **Results that matter:** **Every one of the 25 public games is reachable by non-intelligent strategies** — 10 in a single blind step, 5 after one probing action, 1 via repeated ACTION1, 1 via diverse exploration, and 8 via single repeated actions within a 50–200 step budget; a library-level null-coordinate vulnerability additionally bypasses **18 games in one step**. AERA reaches RHAE 0.2116 (4/25 solved) with a **Qwen2.5-0.5B** model where random and no-explore baselines score 0.0000; the linked code-track entry reaches **RHAE 0.30 on the full 55-game private evaluation**.
- **Limitations / criticisms:** Single author, no peer-review record; the "non-intelligent strategies" analysis is about reachability of *completion*, and the benchmark scores efficiency rather than mere completion, so the critique is sharper for pass/fail readings than for RHAE; the private-set figure comes from a linked competition entry rather than from a controlled experiment in the paper.
- **Gain type:** n/a — a validity critique. Its relevance to the gain-type question is that it undermines public-set evidence for *anyone's* capability claim.
- **Relevance to this FYP (1–5) and why:** **5.** It is the paper that keeps the FYP honest. The near-saturated public-set numbers from [Twin], [Tycho] and [WMAblation] must be read against this: the public set does not discriminate. It also supplies the only small-model ARC-AGI-3 datapoint in the corpus (Qwen2.5-0.5B, RHAE 0.2116) — an actual baseline at FYP scale — and a private-set figure to aim at.
- **Reusable structure:** The non-intelligent-baseline suite (blind step, single probing action, repeated single action) as a mandatory floor for any ARC-AGI-3 claim; and the explicit statement that results are public-set only.
- **BibTeX:** 

```bibtex
@misc{han2026explore,
  title         = {{Explore Before You Solve: The Speed--Depth Trade-off in Epistemic Agents for ARC-AGI-3}},
  author        = {Han, Liew Keong},
  year          = {2026},
  eprint        = {2605.25931},
  archivePrefix = {arXiv},
  primaryClass  = {cs.AI},
  url           = {https://arxiv.org/abs/2605.25931}
}
```

### [ARCPrize2025] — ARC Prize 2025: Technical Report
- **Authors / Year / Venue:** François Chollet, Mike Knoop, Gregory Kamradt, Bryan Landers / 2026 / arXiv technical report (no venue on the record).
- **Link:** arXiv:2601.10904
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2601.10904.json`).
- **Type:** empirical study / technical report
- **Problem:** Reporting what actually worked in the ARC Prize 2025 competition and what it implies for the benchmark series.
- **Method:** Survey of top-performing methods across 1,455 teams and 15,154 entries on the ARC-AGI-2 private evaluation set, plus analysis of contamination and of the role of iterative refinement.
- **Verification signal:** the competition's own held-out private evaluation — the strongest verification protocol in this corpus, since submissions cannot see the test set.
- **What changes:** n/a (report); it surveys methods that change weights and methods that change scaffolds.
- **Results that matter:** Top private-set score **24%** on ARC-AGI-2. The defining theme is the **refinement loop** — per-task iterative program optimisation guided by a feedback signal — in both scaffold form (evolutionary program synthesis, application-layer refinement of commercial systems) and weight form (zero-pretraining networks at **7M parameters**). The report states that frontier reasoning performance "remains fundamentally constrained to knowledge coverage", giving rise to new forms of **benchmark contamination**.
- **Limitations / criticisms:** Written by the benchmark's own organisers, so the framing is not neutral; the contamination analysis is presented as an indication rather than a controlled study.
- **Gain type:** **(b) elicitation**, as the organisers' own diagnosis — frontier performance is bounded by knowledge coverage, which is an elicitation claim about the whole field, made by the people holding the private test set.
- **Relevance to this FYP (1–5) and why:** **5.** It is the authoritative source for the private-set numbers the FYP will be compared against, for the refinement-loop framing that connects Topics 1 and 3, and for the contamination argument that motivates ARC-AGI-3's existence. The 24% private ARC-AGI-2 figure alongside near-saturated *public* ARC-AGI-3 numbers is the clearest available illustration of how far public and private results can diverge.
- **Reusable structure:** The refinement-loop taxonomy (scaffold-space versus weight-space refinement) as an organising device, and the private-versus-public reporting discipline.
- **BibTeX:** 

```bibtex
@misc{chollet2026arc,
  title         = {{ARC Prize 2025: Technical Report}},
  author        = {Chollet, François and Knoop, Mike and Kamradt, Gregory and Landers, Bryan},
  year          = {2026},
  eprint        = {2601.10904},
  archivePrefix = {arXiv},
  primaryClass  = {cs.AI},
  url           = {https://arxiv.org/abs/2601.10904}
}
```
