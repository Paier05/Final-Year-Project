# Topic 2 — Teacher–student / proposer–solver training structures

**Scope.** Work where an explicit generator of *tasks or curricula* is paired with a solver, and the
generator is optimised against the solver's learning. Classical teacher–student and distillation are
included **only** where the teacher adapts to the student — static distillation and one-shot
synthetic-data generation are excluded (Self-Instruct and Evol-Instruct are therefore in
`adjacent.md`, not here).

**Corpus size:** 27 entries, all verified against the live record and cached under `refs/`.

**Reading order.** §1 is the pre-LLM foundation: the proposer–solver game and the first learning-progress
teachers. §2 is the open-endedness and unsupervised-environment-design line, where the objects
generated are *environments* rather than problems — the closest structural match to ARC-AGI-3. §3 is
the 2025–2026 LLM proposer–solver literature, which is where the FYP's method lives. §4 is the
failure-mode literature, which is unusually well developed for such a young topic and is the reason
this section should be read before designing any loop.

---

## §1 Foundations: the proposer–solver game and learning-progress teachers

### [AsymSelfPlay] — Intrinsic Motivation and Automatic Curricula via Asymmetric Self-Play
- **Authors / Year / Venue:** Sainbayar Sukhbaatar, Zeming Lin, Ilya Kostrikov, Gabriel Synnaeve, Arthur Szlam, Rob Fergus / 2017 (v5 2018) / ICLR 2018 (venue stated on the arXiv record).
- **Link:** arXiv:1703.05407
- **Verified:** yes — record retrieved and cached (`refs/arxiv/1703.05407.json`); the comment field states "Published in ICLR 2018".
- **Type:** method
- **Problem:** Learning about an environment without any external reward or task specification.
- **Method:** Two copies of the same agent, Alice and Bob, play an asymmetric game. Alice *proposes* a task by executing a sequence of actions; Bob must then undo it (reversible environments) or repeat it (resettable environments). The reward structure makes Alice prefer tasks that are easy for herself but hard for Bob, which automatically produces a curriculum that tracks Bob's competence. Because the task is defined by Alice's own trajectory, no goal space needs to be hand-specified — the environment's dynamics define the task space.
- **Verification signal:** environment reward — success is mechanically checkable (did Bob reach Alice's state?), with no external labels.
- **What changes:** weights (both agents) and the task distribution (Alice's proposals).
- **Results that matter:** Unsupervised pre-training with Alice/Bob reduces the number of supervised episodes required on a downstream RL task, and in some cases converges to higher reward. No headline number in the abstract, so none is quoted.
- **Limitations / criticisms:** Requires reversible or resettable environments — a strong structural assumption; Alice's incentive is "hard for Bob", not "informative for Bob", which is the difficulty-vs-learnability distinction later work ([AbsoluteZero], [SOAR-Teacher]) had to fix.
- **Relevance to this FYP (1–5) and why:** **4.** It is the origin of the proposer–solver structure the FYP inherits, and its self-defined task space (a task *is* a trajectory) is unusually well suited to ARC-AGI-3, where no goal vocabulary exists and a "task" can only be defined by what the environment does. Its limitation — rewarding difficulty rather than learnability — is the first thing the FYP must not repeat.
- **Reusable structure:** Trajectory-as-goal task specification, requiring no goal language; and the reset/undo framing, which is directly implementable in a deterministic grid environment.
- **BibTeX:** 

```bibtex
@misc{sukhbaatar2017intrinsic,
  title         = {{Intrinsic Motivation and Automatic Curricula via Asymmetric Self-Play}},
  author        = {Sukhbaatar, Sainbayar and Lin, Zeming and Kostrikov, Ilya and Synnaeve, Gabriel and Szlam, Arthur and Fergus, Rob},
  year          = {2017},
  eprint        = {1703.05407},
  archivePrefix = {arXiv},
  primaryClass  = {cs.LG},
  url           = {https://arxiv.org/abs/1703.05407},
  note          = {Published in ICLR 2018}
}
```

### [TSCL] — Teacher-Student Curriculum Learning
- **Authors / Year / Venue:** Tambet Matiisen, Avital Oliver, Taco Cohen, John Schulman / 2017 / arXiv preprint (no venue on the record).
- **Link:** arXiv:1707.00183
- **Verified:** yes — record retrieved and cached (`refs/arxiv/1707.00183.json`).
- **Type:** method
- **Problem:** Choosing which subtask a student should practise next, automatically, instead of hand-designing a curriculum.
- **Method:** A Teacher selects subtasks from a given set for a Student to train on. The family of Teacher algorithms is built on one intuition: practise the tasks where the *slope of the learning curve* is steepest — i.e. where the student is improving fastest right now. The Teacher additionally samples tasks where performance is *degrading*, which addresses forgetting. Note that the task set is given; the Teacher chooses among tasks rather than inventing them.
- **Verification signal:** environment reward (the student's own learning curve is the teacher's signal).
- **What changes:** the task distribution (a sampling policy over a fixed set) and the student's weights.
- **Results that matter:** Matches or beats hand-crafted curricula on decimal addition with an LSTM and Minecraft navigation; solved a Minecraft maze that **could not be solved at all** when trained directly on the target task, with learning an order of magnitude faster than uniform subtask sampling.
- **Limitations / criticisms:** Requires a pre-existing decomposition into subtasks — the hard part in an unstructured environment; learning-progress signals are noisy and can chase transient fluctuations.
- **Relevance to this FYP (1–5) and why:** **5.** ARC-AGI-3 hands the project a task set for free — 135 environments with difficulty-ordered levels — so TSCL's setting (choose among given tasks by measured learning progress) applies without modification, and it is by far the cheapest teacher to implement. It is also the historical source of the "reward the teacher for the student's measured improvement" idea that [SOAR-Teacher] later formalises as bilevel meta-RL.
- **Reusable structure:** The learning-curve-slope acquisition function, and the forgetting term (sample tasks where performance is dropping) — the second is routinely omitted by modern LLM curricula and is cheap to add.
- **BibTeX:** 

```bibtex
@misc{matiisen2017teacherstudent,
  title         = {{Teacher-Student Curriculum Learning}},
  author        = {Matiisen, Tambet and Oliver, Avital and Cohen, Taco and Schulman, John},
  year          = {2017},
  eprint        = {1707.00183},
  archivePrefix = {arXiv},
  primaryClass  = {cs.LG},
  url           = {https://arxiv.org/abs/1707.00183}
}
```

### [GoalGAN] — Automatic Goal Generation for Reinforcement Learning Agents
- **Authors / Year / Venue:** Carlos Florensa, David Held, Xinyang Geng, Pieter Abbeel / 2017 (v5 2018) / ICML 2018, PMLR 80 (venue stated on the arXiv record).
- **Link:** arXiv:1705.06366
- **Verified:** yes — record retrieved and cached (`refs/arxiv/1705.06366.json`); the comment field states ICML 2018 acceptance.
- **Type:** method
- **Problem:** An RL agent trained on one reward can only do one task; how can it discover the range of tasks it is capable of?
- **Method:** A generator network proposes goal states for the agent. The generator is trained *adversarially* against a label indicating whether the agent achieves the goal at an intermediate success rate — so the generator learns to produce goals of appropriate difficulty (neither always achieved nor never achieved) and follows the agent as it improves. This is the earliest clean instantiation of a **goal-of-intermediate-difficulty** objective, the direct ancestor of learnability rewards.
- **Verification signal:** environment reward (goal reached or not), used both to train the agent and to label goals for the generator.
- **What changes:** the task distribution (generated goals) and the agent's weights.
- **Results that matter:** The agent learns a wide set of tasks without prior knowledge of the environment, including tasks with sparse rewards that are otherwise hard to learn. No headline number in the abstract.
- **Limitations / criticisms:** Needs a parameterised goal space that the generator can sample from — precisely what ARC-AGI-3 does not provide, since goals are unstated and must be inferred; GAN training is unstable.
- **Relevance to this FYP (1–5) and why:** **3.** The *objective* transfers (target intermediate success rate) but the *mechanism* does not, because there is no goal space to sample. Its value here is as the origin of the intermediate-difficulty criterion, and as a reminder that this criterion needs a representable goal space — a requirement the FYP has to satisfy some other way, e.g. by generating environment variants instead of goals.
- **Reusable structure:** The intermediate-success-rate labelling rule (a goal is "good" if success is in some band, e.g. 0.2–0.8), which is the cheapest possible learnability signal.
- **BibTeX:** 

```bibtex
@misc{florensa2017automatic,
  title         = {{Automatic Goal Generation for Reinforcement Learning Agents}},
  author        = {Florensa, Carlos and Held, David and Geng, Xinyang and Abbeel, Pieter},
  year          = {2017},
  eprint        = {1705.06366},
  archivePrefix = {arXiv},
  primaryClass  = {cs.LG},
  url           = {https://arxiv.org/abs/1705.06366},
  note          = {Accepted at ICML 2018, Proceedings of the 35th International Conference on Machine Learning, Stock}
}
```

### [AlphaZero] — Mastering Chess and Shogi by Self-Play with a General Reinforcement Learning Algorithm
- **Authors / Year / Venue:** David Silver, Thomas Hubert, Julian Schrittwieser, Ioannis Antonoglou, Matthew Lai, Arthur Guez, Marc Lanctot, Laurent Sifre, et al. (13 authors) / 2017 / arXiv preprint (no venue on the record).
- **Link:** arXiv:1712.01815
- **Verified:** yes — record retrieved and cached (`refs/arxiv/1712.01815.json`).
- **Type:** method
- **Problem:** Whether a single general algorithm can reach superhuman play in multiple games from scratch, without domain-specific engineering.
- **Method:** Tabula rasa reinforcement learning from self-play, given only the rules. A single network provides policy and value; Monte Carlo tree search uses that network to produce improved move distributions; the network is trained toward the search's output; the improved network makes the next round of search stronger. Note the shape of the loop: **search improves the policy, and the improved policy makes search better** — the curriculum is an emergent property of playing an opponent of exactly one's own strength.
- **Verification signal:** environment reward — the game's own win/loss rule, a perfect verifier.
- **What changes:** weights, with the task distribution (the distribution of positions played) emerging from the self-play dynamic.
- **Results that matter:** Superhuman play in chess, shogi and Go within 24 hours from random play, defeating a world-champion program in each case.
- **Limitations / criticisms:** Depends on a perfect simulator, a perfect verifier, and a symmetric two-player game that automatically supplies an opponent at the right level — none of which holds for a single-agent, goal-unknown interactive benchmark; the compute is far outside FYP scale.
- **Relevance to this FYP (1–5) and why:** **3.** Included as the reference point the issue names, and because it isolates what makes self-play work: perfect verification plus an automatically level-matched opponent. Neither is free in ARC-AGI-3 — the environment verifies but nothing supplies difficulty matching — which is exactly the job the FYP's teacher must do.
- **Reusable structure:** The policy-improvement-operator framing (search output as training target) — the ARC-AGI-3 analogue being to treat an expensive search's action sequence as the target for a cheap policy, which is also how the efficiency metric can be attacked.
- **BibTeX:** 

```bibtex
@misc{silver2017mastering,
  title         = {{Mastering Chess and Shogi by Self-Play with a General Reinforcement Learning Algorithm}},
  author        = {Silver, David and Hubert, Thomas and Schrittwieser, Julian and Antonoglou, Ioannis and Lai, Matthew and Guez, Arthur and Lanctot, Marc and Sifre, Laurent and Kumaran, Dharshan and Graepel, Thore and Lillicrap, Timothy and Simonyan, Karen and Hassabis, Demis},
  year          = {2017},
  eprint        = {1712.01815},
  archivePrefix = {arXiv},
  primaryClass  = {cs.AI},
  url           = {https://arxiv.org/abs/1712.01815}
}
```

### [POET] — Paired Open-Ended Trailblazer (POET): Endlessly Generating Increasingly Complex and Diverse Learning Environments and Their Solutions
- **Authors / Year / Venue:** Rui Wang, Joel Lehman, Jeff Clune, Kenneth O. Stanley / 2019 / arXiv preprint (no venue on the record).
- **Link:** arXiv:1901.01753
- **Verified:** yes — record retrieved and cached (`refs/arxiv/1901.01753.json`).
- **Type:** method
- **Problem:** Whether the problems themselves can be generated by the algorithm at the same time as they are being solved.
- **Method:** POET maintains a *population of paired environments and agents*. It repeatedly mutates existing environments to create new ones, optimises each agent on its paired environment, and — the critical mechanism — periodically attempts **transfer**: any agent may be tested on any other environment, and if it does better than the incumbent it takes over. Environments are admitted only if they are neither trivial nor unsolvable for the current population (a minimal-criterion filter). Stepping stones therefore need not be useful in their own lineage.
- **Verification signal:** environment reward (walker performance on generated terrain).
- **What changes:** the task distribution (generated environments) and agent weights, jointly, as a population.
- **Results that matter:** POET produces agents solving environments that direct optimisation cannot solve at all, and that a direct-path curriculum control algorithm also fails to solve; the paper reports that transfer between environments is essential to the result.
- **Limitations / criticisms:** Very expensive (a population of agents *and* environments); the environment space is a hand-designed parameterisation of 2D terrain; "open-endedness" is asserted more than measured — the gap [EnhancedPOET] tries to close.
- **Relevance to this FYP (1–5) and why:** **5.** This is the structural template for a teacher that generates *environments* rather than problems, which is what ARC-AGI-3 requires. The transfer mechanism is the single most transferable idea: an agent specialised on game A being tried on game B, and replacing B's incumbent if better, is directly implementable across the 135 environments.
- **Reusable structure:** The paired population plus periodic cross-environment transfer, and the minimal-criterion admission filter (not too easy, not impossible) — a difficulty gate that needs no learned model.
- **BibTeX:** 

```bibtex
@misc{wang2019paired,
  title         = {{Paired Open-Ended Trailblazer (POET): Endlessly Generating Increasingly Complex and Diverse Learning Environments and Their Solutions}},
  author        = {Wang, Rui and Lehman, Joel and Clune, Jeff and Stanley, Kenneth O.},
  year          = {2019},
  eprint        = {1901.01753},
  archivePrefix = {arXiv},
  primaryClass  = {cs.NE},
  url           = {https://arxiv.org/abs/1901.01753}
}
```

---

## §2 Generating environments: open-endedness and unsupervised environment design

### [EnhancedPOET] — Enhanced POET: Open-Ended Reinforcement Learning through Unbounded Invention of Learning Challenges and their Solutions
- **Authors / Year / Venue:** Rui Wang, Joel Lehman, Aditya Rawal, Jiale Zhi, Yulun Li, Jeff Clune, Kenneth O. Stanley / 2020 / arXiv preprint (no venue on the record).
- **Link:** arXiv:2003.08536
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2003.08536.json`).
- **Type:** method
- **Problem:** The original POET could not demonstrate open-endedness, partly because of algorithmic limits and partly because there was no way to *measure* whether a system keeps innovating.
- **Method:** Four changes. Two are algorithmic: (1) a domain-general measure of how meaningfully novel a new challenge is, used to decide what to admit; (2) an efficient heuristic for when an agent should goal-switch to a different environment. Two are external: (3) a more flexible environment encoding, and (4) **ANNECS**, a generic measure of the extent to which a system continues to exhibit open-ended innovation.
- **Verification signal:** environment reward, plus the novelty measure as an admission criterion.
- **What changes:** the task distribution (environments) and agent weights.
- **Results that matter:** Described by the authors as the most open-ended algorithmic demonstration to date, producing behaviours that solve challenges unreachable by other means. The contribution to quote is the *measure*, not a score.
- **Limitations / criticisms:** Still confined to 2D walker terrain; ANNECS is a proxy whose validity outside this domain is unestablished; compute-hungry.
- **Relevance to this FYP (1–5) and why:** **4.** Its real contribution to this project is methodological: if the FYP claims its teacher keeps producing useful new environments, it needs a *metric* for that claim, and ANNECS-style "how many newly admitted challenges are neither trivial nor already solved" is the ready-made answer.
- **Reusable structure:** The novelty-admission criterion and an ANNECS-style progress metric — both belong in the FYP's evaluation chapter as the anti-collapse diagnostic.
- **BibTeX:** 

```bibtex
@misc{wang2020enhanced,
  title         = {{Enhanced POET: Open-Ended Reinforcement Learning through Unbounded Invention of Learning Challenges and their Solutions}},
  author        = {Wang, Rui and Lehman, Joel and Rawal, Aditya and Zhi, Jiale and Li, Yulun and Clune, Jeff and Stanley, Kenneth O.},
  year          = {2020},
  eprint        = {2003.08536},
  archivePrefix = {arXiv},
  primaryClass  = {cs.NE},
  url           = {https://arxiv.org/abs/2003.08536}
}
```

### [PAIRED] — Emergent Complexity and Zero-shot Transfer via Unsupervised Environment Design
- **Authors / Year / Venue:** Michael Dennis, Natasha Jaques, Eugene Vinitsky, Alexandre Bayen, Stuart Russell, Andrew Critch, Sergey Levine / 2020 (v2 2021) / arXiv preprint (no venue on the record).
- **Link:** arXiv:2012.02096
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2012.02096.json`).
- **Type:** method
- **Problem:** Domain randomisation cannot adapt difficulty or generate structure; minimax adversarial training generates unsolvable worst cases. Neither produces a useful curriculum.
- **Method:** Unsupervised Environment Design (UED) is introduced as a paradigm: developers supply an environment with free parameters, and those parameters are set automatically to produce a distribution over valid, solvable environments. PAIRED implements it with three agents — a protagonist, an antagonist, and an environment-generating adversary allied with the antagonist. The adversary maximises **regret**, the gap between antagonist and protagonist return. Regret is the key trick: an unsolvable level has zero regret (neither agent can do it), so the adversary is automatically pushed toward levels that are solvable but not yet solved.
- **Verification signal:** environment reward (returns of the two agents).
- **What changes:** the task distribution (environment parameters) and agent weights.
- **Results that matter:** PAIRED produces a natural curriculum of increasing complexity and achieves higher zero-shot transfer to highly novel test environments than domain randomisation and minimax baselines.
- **Limitations / criticisms:** Three simultaneous learners are unstable and expensive; regret is only approximated; later work ([RobustPLR]) shows that simply *curating* random levels can match or beat generating them.
- **Relevance to this FYP (1–5) and why:** **5.** Regret is the best-motivated learnability signal in the literature and it solves the exact failure the FYP's teacher would otherwise hit — proposing ARC-AGI-3 variants that are simply impossible. The antagonist-as-reference-solver construction also suggests a cheap ARC-AGI-3 analogue: use the *human baseline action count* the benchmark already provides as the reference return, making regret computable without a second trained agent.
- **Reusable structure:** The regret objective, and (specific to this benchmark) the substitution of the published human baseline for the antagonist's return.
- **BibTeX:** 

```bibtex
@misc{dennis2020emergent,
  title         = {{Emergent Complexity and Zero-shot Transfer via Unsupervised Environment Design}},
  author        = {Dennis, Michael and Jaques, Natasha and Vinitsky, Eugene and Bayen, Alexandre and Russell, Stuart and Critch, Andrew and Levine, Sergey},
  year          = {2020},
  eprint        = {2012.02096},
  archivePrefix = {arXiv},
  primaryClass  = {cs.LG},
  url           = {https://arxiv.org/abs/2012.02096}
}
```

### [PLR] — Prioritized Level Replay
- **Authors / Year / Venue:** Minqi Jiang, Edward Grefenstette, Tim Rocktäschel / 2020 (v4 2021) / arXiv preprint (no venue on the record).
- **Link:** arXiv:2010.03934
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2010.03934.json`).
- **Type:** method
- **Problem:** In procedurally generated environments, training levels are sampled uniformly regardless of what the current policy can learn from them.
- **Method:** PLR keeps a score for every level seen so far, estimating its **future learning potential**, and samples the next training level in proportion to that score. The estimator is the level's recent TD-error magnitude — a signal already computed by the RL algorithm, so the curriculum is essentially free. No level is generated; the curriculum comes entirely from *replay ordering*.
- **Verification signal:** environment reward (TD-errors derived from it).
- **What changes:** the task distribution (a sampling policy over existing levels) and agent weights.
- **Results that matter:** Significant sample-efficiency and generalisation gains on Procgen, matching the previous state of the art in test return; combined with the previous leading method it raises the state of the art to **over 76% improvement in test return** relative to standard RL baselines.
- **Limitations / criticisms:** Needs a large pool of levels to replay; TD-error is a proxy for learning potential that conflates stochasticity with learnability — the problem [GroundingAleatoric] (see `adjacent.md`) attacks.
- **Relevance to this FYP (1–5) and why:** **5.** ARC-AGI-3 gives a fixed pool of environments and levels; PLR is exactly the algorithm for that setting, needs no environment generator at all, and costs almost nothing on top of ordinary training. It is the strongest candidate for the FYP's *cheap teacher* baseline.
- **Reusable structure:** Score-and-replay curriculum using a signal the learner already produces; the level-scoring/staleness bookkeeping generalises directly to ARC-AGI-3 game-level pairs.
- **BibTeX:** 

```bibtex
@misc{jiang2020prioritized,
  title         = {{Prioritized Level Replay}},
  author        = {Jiang, Minqi and Grefenstette, Edward and Rocktäschel, Tim},
  year          = {2020},
  eprint        = {2010.03934},
  archivePrefix = {arXiv},
  primaryClass  = {cs.LG},
  url           = {https://arxiv.org/abs/2010.03934}
}
```

### [RobustPLR] — Replay-Guided Adversarial Environment Design
- **Authors / Year / Venue:** Minqi Jiang, Michael Dennis, Jack Parker-Holder, Jakob Foerster, Edward Grefenstette, Tim Rocktäschel / 2021 (v2 2022) / NeurIPS 2021 (venue stated on the arXiv record).
- **Link:** arXiv:2110.02439
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2110.02439.json`); the comment field states NeurIPS 2021.
- **Type:** method / theory
- **Problem:** PLR worked but had no theory; PAIRED had theory but struggled empirically. Are they the same thing?
- **Method:** The paper recasts PLR as a UED method — curating random levels is itself a way of generating novel ones — and defines **Dual Curriculum Design (DCD)**, a class containing both PLR and PAIRED as special cases, inheriting their guarantees. The theory then suggests a counterintuitive fix: **stop updating the policy on uncurated levels**, i.e. train on strictly less data. The resulting method, PLR⊥, has a robustness guarantee at Nash equilibria.
- **Verification signal:** environment reward.
- **What changes:** the task distribution (curation policy) and agent weights.
- **Results that matter:** PLR⊥ improves zero-shot out-of-distribution transfer over PLR, and also improves PAIRED when applied to it. The headline conceptual result — that training on *less* data (only curated levels) improves convergence — is the number-free finding worth carrying.
- **Limitations / criticisms:** Guarantees hold at Nash equilibria that deep RL does not reach; the empirical gains are domain-limited.
- **Relevance to this FYP (1–5) and why:** **4.** Two transfers. First, the unification tells the FYP it does not need an environment generator to claim it is doing UED — curation counts. Second, the "do not learn from uncurated experience" rule is a concrete, cheap design decision with a theoretical justification, and it is unusual enough to be worth an ablation.
- **Reusable structure:** The DCD framing (curation and generation as one design space) for positioning the FYP's teacher; the train-only-on-curated-levels ablation.
- **BibTeX:** 

```bibtex
@misc{jiang2021replayguided,
  title         = {{Replay-Guided Adversarial Environment Design}},
  author        = {Jiang, Minqi and Dennis, Michael and Parker-Holder, Jack and Foerster, Jakob and Grefenstette, Edward and Rocktäschel, Tim},
  year          = {2021},
  eprint        = {2110.02439},
  archivePrefix = {arXiv},
  primaryClass  = {cs.LG},
  url           = {https://arxiv.org/abs/2110.02439}
}
```

### [ACCEL] — Evolving Curricula with Regret-Based Environment Design
- **Authors / Year / Venue:** Jack Parker-Holder, Minqi Jiang, Michael Dennis, Mikayel Samvelyan, Jakob Foerster, Edward Grefenstette, Tim Rocktäschel / 2022 (v3 2023) / arXiv preprint (no venue on the record).
- **Link:** arXiv:2203.01302
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2203.01302.json`).
- **Type:** method
- **Problem:** Regret-based UED is general but struggles to *find* effective levels in large design spaces; evolutionary methods explore well but rely on domain heuristics and heavy compute.
- **Method:** ACCEL (Adversarially Compounding Complexity by Editing Levels) combines them: rather than generating levels from scratch, it makes small **edits** to levels already identified as high-regret, and re-scores them. Because high-regret levels are at the frontier of the agent's ability, editing them tends to produce more frontier levels, so complexity compounds — curricula start simple and become complex without any explicit difficulty schedule.
- **Verification signal:** environment reward (regret estimated from it).
- **What changes:** the task distribution (edited levels) and agent weights.
- **Results that matter:** Retains the theoretical properties of regret-based UED while delivering significant empirical gains across a diverse set of environments; the qualitative result — curricula that start simple and compound in complexity — is the claim to carry.
- **Limitations / criticisms:** Edit operators are domain-specific; regret approximations remain crude; no LLM-scale demonstration.
- **Relevance to this FYP (1–5) and why:** **5.** *Edit an existing environment* is a far cheaper and more reliable generator than *write a new one*, and ARC-AGI-3 environments are exactly the kind of structured artefact that supports small semantic edits (object counts, obstacle placement, rule composition). This is the most implementable environment-generation mechanism in the corpus for this benchmark.
- **Reusable structure:** Edit-the-frontier as a generation operator, and the "curriculum complexity over time" plot as a diagnostic that the teacher is escalating rather than stalling.
- **BibTeX:** 

```bibtex
@misc{parkerholder2022evolving,
  title         = {{Evolving Curricula with Regret-Based Environment Design}},
  author        = {Parker-Holder, Jack and Jiang, Minqi and Dennis, Michael and Samvelyan, Mikayel and Foerster, Jakob and Grefenstette, Edward and Rocktäschel, Tim},
  year          = {2022},
  eprint        = {2203.01302},
  archivePrefix = {arXiv},
  primaryClass  = {cs.LG},
  url           = {https://arxiv.org/abs/2203.01302}
}
```

### [TRACED] — TRACED: Transition-aware Regret Approximation with Co-learnability for Environment Design
- **Authors / Year / Venue:** Geonwoo Cho, Jaegyun Im, Jihwan Lee, Hojun Yi, Sejin Kim, Sundong Kim / 2025 (v5 2026-03) / ICLR 2026 (venue stated on the arXiv record).
- **Link:** arXiv:2506.19997
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2506.19997.json`); the comment field states ICLR 2026.
- **Type:** method
- **Problem:** UED regret is usually approximated by value-function loss alone, and existing methods ignore how training on one task affects performance on others.
- **Method:** Two additions to regret approximation. (1) **Transition-prediction error** as an extra term — how badly the agent predicts the environment's dynamics — which captures learning potential that value loss misses. (2) **Co-Learnability**, a lightweight metric estimating how training on task A changes performance on task B, so the curriculum can prefer tasks whose gains spill over.
- **Verification signal:** environment reward, plus the agent's own dynamics-prediction error (self-supervised, no reward needed).
- **What changes:** the task distribution and agent weights.
- **Results that matter:** Improved zero-shot generalisation over strong UED baselines across multiple benchmarks; ablations attribute rapid complexity ramp-up to the transition-prediction term and additional gains to Co-Learnability when combined with it.
- **Limitations / criticisms:** Both signals are approximations; Co-Learnability needs cross-task evaluations, which costs rollouts; grid-world scale.
- **Relevance to this FYP (1–5) and why:** **5.** ARC-AGI-3 is a *world-modelling* benchmark where reward is sparse and inferred, so a curriculum signal based on dynamics-prediction error — which needs no reward at all — is far better matched to it than value-loss regret. Co-Learnability is also the right formal tool for asking which of the 135 environments teach each other.
- **Reusable structure:** Transition-prediction error as a reward-free learnability signal (the single most portable idea in §2 for this benchmark), and Co-Learnability as a cross-game transfer matrix for the results chapter.
- **BibTeX:** 

```bibtex
@misc{cho2025traced,
  title         = {{TRACED: Transition-aware Regret Approximation with Co-learnability for Environment Design}},
  author        = {Cho, Geonwoo and Im, Jaegyun and Lee, Jihwan and Yi, Hojun and Kim, Sejin and Kim, Sundong},
  year          = {2025},
  eprint        = {2506.19997},
  archivePrefix = {arXiv},
  primaryClass  = {cs.LG},
  url           = {https://arxiv.org/abs/2506.19997}
}
```

### [OMNI] — OMNI: Open-endedness via Models of human Notions of Interestingness
- **Authors / Year / Venue:** Jenny Zhang, Joel Lehman, Kenneth Stanley, Jeff Clune / 2023 (v3 2024) / arXiv preprint (no venue on the record).
- **Link:** arXiv:2306.01711
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2306.01711.json`).
- **Type:** method
- **Problem:** Even after filtering for tasks the agent can currently learn, infinitely many *learnable but uninteresting* tasks remain — trivial variations of things already learned. Open-endedness research had no way to quantify interestingness.
- **Method:** Use a foundation model as a **Model of Interestingness**: because FMs are trained on human-generated text in which people constantly say what they find interesting or boring, they already encode a usable prior over interestingness. The task sampler then prioritises tasks that are both learnable *and* judged interesting, instead of learning progress alone.
- **Verification signal:** environment reward for learnability; a **learned/LLM judgement** for interestingness — a learned reward model, with the reliability caveats that implies.
- **What changes:** the task distribution.
- **Results that matter:** Outperforms uniform task sampling and learning-progress-only baselines on open-ended learning. No single headline number in the abstract.
- **Limitations / criticisms:** Interestingness is an LLM judgement with no ground truth — precisely the biased-judge setting [BlindCurator] (Topic 1) shows can silently break a self-evolving loop; ARC-AGI-3 deliberately avoids cultural and linguistic content, so the FM's human-derived prior has much less to grip.
- **Relevance to this FYP (1–5) and why:** **3.** The problem it identifies is real and will bite — an ARC-AGI-3 teacher that only optimises learnability will produce near-duplicate variants. But the proposed solution is the weakest link in a benchmark designed to defeat language priors, so the FYP likely needs a *structural* diversity measure instead. Included because the problem statement is essential even though the mechanism transfers poorly.
- **Reusable structure:** The explicit separation of two filters — learnable **and** interesting — as a design requirement, with the FYP substituting a behavioural/structural novelty measure for the FM judgement.
- **BibTeX:** 

```bibtex
@misc{zhang2023omni,
  title         = {{OMNI: Open-endedness via Models of human Notions of Interestingness}},
  author        = {Zhang, Jenny and Lehman, Joel and Stanley, Kenneth and Clune, Jeff},
  year          = {2023},
  eprint        = {2306.01711},
  archivePrefix = {arXiv},
  primaryClass  = {cs.AI},
  url           = {https://arxiv.org/abs/2306.01711}
}
```

### [OMNI-EPIC] — OMNI-EPIC: Open-endedness via Models of human Notions of Interestingness with Environments Programmed in Code
- **Authors / Year / Venue:** Maxence Faldor, Jenny Zhang, Antoine Cully, Jeff Clune / 2024 (v3 2025) / arXiv preprint (no venue on the record).
- **Link:** arXiv:2405.15568
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2405.15568.json`).
- **Type:** method
- **Problem:** Environment generators are confined to manually predefined, narrow parameterisations, which bounds what can ever be generated.
- **Method:** OMNI-EPIC has a foundation model **write code** that specifies both the environment and its reward function, then uses the OMNI interestingness/learnability filters to decide what to keep. Because the environment is a program rather than a point in a parameter vector, the generator's reach is limited only by what is simulatable.
- **Verification signal:** environment reward (defined by the generated code itself) plus FM judgement for interestingness — note the circularity: the generator writes the verifier.
- **What changes:** the task distribution (environments **and** reward functions, as code).
- **Results that matter:** Continuous generation of new, varied learning challenges, with demonstrated adaptation to the RL agent's learning progress. Qualitative; no headline number.
- **Limitations / criticisms:** The generator authoring its own reward function is a reward-hacking hazard by construction; no measure of whether generated tasks form a coherent curriculum; results are demonstrations rather than controlled comparisons.
- **Relevance to this FYP (1–5) and why:** **4.** Environments-as-code is the right representation for ARC-AGI-3 variant generation — grid environments are small programs, and generated variants can be executed and checked. But the circular-verifier problem is exactly what the FYP must avoid, and it is avoidable here because the *real* ARC-AGI-3 environments provide an external, uncorrupted score.
- **Reusable structure:** Code-as-environment generation with an execution check on the generated program; and, as a cautionary design rule, keeping generated-task reward and evaluation reward strictly separate.
- **BibTeX:** 

```bibtex
@misc{faldor2024omniepic,
  title         = {{OMNI-EPIC: Open-endedness via Models of human Notions of Interestingness with Environments Programmed in Code}},
  author        = {Faldor, Maxence and Zhang, Jenny and Cully, Antoine and Clune, Jeff},
  year          = {2024},
  eprint        = {2405.15568},
  archivePrefix = {arXiv},
  primaryClass  = {cs.AI},
  url           = {https://arxiv.org/abs/2405.15568}
}
```
---

## §3 LLM proposer–solver loops (2022–2026)

### [STaR] — STaR: Bootstrapping Reasoning With Reasoning
- **Authors / Year / Venue:** Eric Zelikman, Yuhuai Wu, Jesse Mu, Noah D. Goodman / 2022 / arXiv preprint (no venue on the record).
- **Link:** arXiv:2203.14465
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2203.14465.json`).
- **Type:** method
- **Problem:** Rationale-based reasoning needs massive rationale datasets, which do not exist.
- **Method:** A four-step loop: generate rationales for many questions using a few exemplars; keep the rationales whose final answer is correct; for wrong answers, *rationalise* — re-generate the rationale given the correct answer, and keep that; fine-tune on all kept rationales; repeat. The task set is fixed, so STaR is not a curriculum generator — it is the reference case for **self-generated training data filtered by a mechanical check**, which is the substrate every later proposer–solver loop builds on.
- **Verification signal:** executable/mechanical check — final-answer correctness against a known label.
- **What changes:** weights, trained on self-generated data.
- **Results that matter:** Substantially better than fine-tuning to predict the answer directly, and comparable to fine-tuning a **30× larger** model on CommonsenseQA.
- **Limitations / criticisms:** Requires ground-truth answers (so it is not zero-data); rationalisation can produce plausible reasoning that reaches the right answer for the wrong reason, an unverified failure mode; iterating amplifies the model's own biases.
- **Relevance to this FYP (1–5) and why:** **3.** The mechanism (filter self-generated attempts by outcome, train on survivors) transfers, and ARC-AGI-3 supplies the filter for free. The 30×-smaller-model result is the historical origin of the FYP's central bet: self-generated, verified experience substitutes for scale.
- **Reusable structure:** The keep-only-verified-trajectories filter, and the "match a k× larger baseline" reporting frame, which is how a small-model FYP should present its result.
- **BibTeX:** 

```bibtex
@misc{zelikman2022star,
  title         = {{STaR: Bootstrapping Reasoning With Reasoning}},
  author        = {Zelikman, Eric and Wu, Yuhuai and Mu, Jesse and Goodman, Noah D.},
  year          = {2022},
  eprint        = {2203.14465},
  archivePrefix = {arXiv},
  primaryClass  = {cs.LG},
  url           = {https://arxiv.org/abs/2203.14465}
}
```

### [AbsoluteZero] — Absolute Zero: Reinforced Self-play Reasoning with Zero Data
- **Authors / Year / Venue:** Andrew Zhao, Yiran Wu, Yang Yue, Tong Wu, Quentin Xu, Yang Yue, Matthieu Lin, Shenzhi Wang, et al. (11 authors) / 2025 (v3 2025-10) / arXiv preprint (no venue on the record).
- **Link:** arXiv:2505.03335
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2505.03335.json`).
- **Type:** method
- **Problem:** RLVR still depends on human-curated question sets; and for a system stronger than its teachers, human-provided tasks would carry little learning signal anyway.
- **Method:** A single model plays both roles: it proposes tasks that maximise its own learning progress, then solves them. The Absolute Zero Reasoner (AZR) grounds the loop in code, using a **code executor** both to validate that a proposed task is well-formed and to verify the solver's answer — one mechanism serving as the unified source of verifiable reward. Proposals are rewarded by learnability (tasks the solver sometimes but not always solves), so the curriculum tracks the solver automatically.
- **Verification signal:** executable check (a Python interpreter), used twice — task validity and answer correctness.
- **What changes:** weights, and the task distribution (self-proposed).
- **Results that matter:** Trained with **no external data at all**, AZR reaches overall state-of-the-art on coding and mathematical reasoning, beating zero-setting models trained on tens of thousands of in-domain human-curated examples; the authors report it works across model scales and classes.
- **Limitations / criticisms:** The domain must be executable — the loop cannot leave code without losing its verifier; [R-Diverse] and [VocabDropout] both report that R-Zero-style loops of this kind plateau or decay as diversity collapses; [SOAR-Teacher] reports that grounded rewards beat the intrinsic learnability reward AZR uses.
- **Relevance to this FYP (1–5) and why:** **5.** This is the reference architecture the internal briefing already identified, and its central design lesson is exactly right for ARC-AGI-3: build the loop around the *one* thing that verifies mechanically. In ARC-AGI-3 that thing is the environment itself, which validates a proposed level (it runs) and scores a solution (efficiency) — the same double duty the code executor performs here.
- **Reusable structure:** The proposer-validity/solver-correctness double use of a single verifier; the learnability reward defined as intermediate solve rate; and the "trained with zero curated data" comparison frame.
- **BibTeX:** 

```bibtex
@misc{zhao2025absolute,
  title         = {{Absolute Zero: Reinforced Self-play Reasoning with Zero Data}},
  author        = {Zhao, Andrew and Wu, Yiran and Yue, Yang and Wu, Tong and Xu, Quentin and Yue, Yang and Lin, Matthieu and Wang, Shenzhi and Wu, Qingyun and Zheng, Zilong and Huang, Gao},
  year          = {2025},
  eprint        = {2505.03335},
  archivePrefix = {arXiv},
  primaryClass  = {cs.LG},
  url           = {https://arxiv.org/abs/2505.03335}
}
```

### [R-Zero] — R-Zero: Self-Evolving Reasoning LLM from Zero Data
- **Authors / Year / Venue:** Chengsong Huang, Wenhao Yu, Xiaoyang Wang, Hongming Zhang, Zongxia Li, Ruosen Li, Jiaxin Huang, Haitao Mi, et al. (9 authors) / 2025 (v4 2026-02) / arXiv preprint (no venue on the record).
- **Link:** arXiv:2508.05004
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2508.05004.json`).
- **Type:** method
- **Problem:** Self-evolving methods still lean on curated tasks and labels; R-Zero removes both.
- **Method:** From a single base model, two independent models are initialised with distinct roles — a **Challenger** and a **Solver** — and optimised separately while co-evolving through interaction. The Challenger is rewarded for proposing tasks near the edge of the Solver's capability; the Solver is rewarded for solving increasingly hard proposals. Unlike [AbsoluteZero]'s single dual-role model, the two roles have separate parameters, so the teacher can specialise in teaching without also having to be the best solver.
- **Verification signal:** self-consistency — majority voting over Solver samples stands in for ground truth, since no labels exist.
- **What changes:** weights (both roles) and the task distribution.
- **Results that matter:** +6.49 on math-reasoning benchmarks and +7.54 on general-domain reasoning for Qwen3-4B-Base, with gains reported across backbones.
- **Limitations / criticisms:** The verifier is majority voting, not execution — so the loop can converge on confidently wrong consensus; [R-Diverse] shows R-Zero's gains are **non-sustained**, degrading as self-play continues, and [VocabDropout] independently reports proposer collapse in the same setup. This is the corpus's clearest case of a headline result that later work qualifies.
- **Relevance to this FYP (1–5) and why:** **5.** Doubly relevant: it is the separate-teacher/separate-student architecture the FYP is prototyping (see `experiments/mini_r_zero/` on the sibling branch), and it is the specific system whose failure modes two independent 2026 papers document. Adopting the architecture means adopting its known pathologies, and the fixes are known too.
- **Reusable structure:** The separate-parameters Challenger/Solver split; and — as a lesson rather than a mechanism — the need to report performance **over iterations**, since collapse only appears in the later ones.
- **BibTeX:** 

```bibtex
@misc{huang2025rzero,
  title         = {{R-Zero: Self-Evolving Reasoning LLM from Zero Data}},
  author        = {Huang, Chengsong and Yu, Wenhao and Wang, Xiaoyang and Zhang, Hongming and Li, Zongxia and Li, Ruosen and Huang, Jiaxin and Mi, Haitao and Yu, Dong},
  year          = {2025},
  eprint        = {2508.05004},
  archivePrefix = {arXiv},
  primaryClass  = {cs.LG},
  url           = {https://arxiv.org/abs/2508.05004}
}
```

### [SQLM] — Self-Questioning Language Models
- **Authors / Year / Venue:** Lili Chen, Mihir Prabhudesai, Katerina Fragkiadaki, Hao Liu, Deepak Pathak / 2025 (v4 2025-09) / arXiv preprint (no venue on the record).
- **Link:** arXiv:2508.03682
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2508.03682.json`).
- **Type:** method
- **Problem:** Can a model improve given only a *topic* — no dataset, no questions, no answers?
- **Method:** An asymmetric self-play framework in which a proposer is given only a topic prompt and generates questions for a solver; both are trained with RL. The proposer's reward is explicitly shaped so that problems that are **not too easy and not too difficult** pay best. The solver is rewarded by majority voting where no ground truth exists — except in coding, where the proposer instead generates **unit tests**, restoring a mechanical verifier.
- **Verification signal:** self-consistency (majority voting) in general; executable check (proposer-written unit tests) for code.
- **What changes:** weights (proposer and solver) and the task distribution.
- **Results that matter:** Improvement on downstream benchmarks with no curated training data, demonstrated on three-digit multiplication, OMEGA algebra problems, and Codeforces programming problems. No single headline number in the abstract.
- **Limitations / criticisms:** Majority voting rewards consensus, not correctness; proposer-written unit tests can be wrong or trivially satisfiable — the reward-hacking channel [VHG] addresses with an independent verifier.
- **Relevance to this FYP (1–5) and why:** **4.** The minimal-input premise ("here is a topic, go") is the closest analogue to ARC-AGI-3's "here is an environment, no instructions". The paper's contrast between voting-based and test-based verification within one framework is also the cleanest available demonstration of how much the verifier matters.
- **Reusable structure:** The proposer-writes-the-verifier pattern (here, unit tests) as a way to get mechanical checking in domains that lack it — with the FYP variant being proposer-written success predicates over grid states, checkable against replays.
- **BibTeX:** 

```bibtex
@misc{chen2025selfquestioning,
  title         = {{Self-Questioning Language Models}},
  author        = {Chen, Lili and Prabhudesai, Mihir and Fragkiadaki, Katerina and Liu, Hao and Pathak, Deepak},
  year          = {2025},
  eprint        = {2508.03682},
  archivePrefix = {arXiv},
  primaryClass  = {cs.LG},
  url           = {https://arxiv.org/abs/2508.03682}
}
```

### [SOAR-Teacher] — Teaching Models to Teach Themselves: Reasoning at the Edge of Learnability
- **Authors / Year / Venue:** Shobhita Sundaram, John Quan, Ariel Kwiatkowski, Kartik Ahuja, Yann Ollivier, Julia Kempe / 2026 (v3 2026-06) / ICML 2026 (venue stated on the arXiv record).
- **Link:** arXiv:2601.18778
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2601.18778.json`); the comment field states "ICML 2026".
  **Naming note:** the issue refers to this as "SOAR"; a different 2025 paper by Pourcel et al. ([SOAR-ProgSynth], arXiv:2507.14172) also uses that name. They are unrelated works.
- **Type:** method / empirical study
- **Problem:** RL for reasoning stalls on datasets where the initial success rate is ~0 — every rollout fails, so there is no gradient signal at all.
- **Method:** An asymmetric self-play framework using **bilevel meta-RL**. A teacher model proposes synthetic problems for a student; the teacher's reward is the student's *measured improvement on a held-out subset of hard problems*. This is the key departure from [AbsoluteZero]-style loops: the teacher is graded by real student progress, not by an intrinsic proxy such as the solver's success variance. The paper's framing question is whether a pretrained LLM can generate a curriculum for problems it cannot itself solve.
- **Verification signal:** the student's measured improvement on held-out hard problems (a grounded, outcome-based teacher reward), with per-problem correctness checked mechanically.
- **What changes:** weights (teacher and student) and the task distribution.
- **Results that matter:** On the hardest math subsets (**0/128 success rate**), three findings: bilevel meta-RL unlocks learning under sparse binary rewards; **grounded rewards outperform intrinsic learnability rewards** and reliably avoid the instability and diversity-collapse modes seen in prior LLM self-play; and the structure and well-posedness of generated questions matters more for learning progress than whether the teacher's own solutions are correct.
- **Limitations / criticisms:** Bilevel optimisation is expensive — every teacher update needs student training; results are on maths benchmarks with clean answer checking; the held-out hard set must exist and be representative.
- **Relevance to this FYP (1–5) and why:** **5.** This is the most important paper in Topic 2 for the FYP. The 0%-success regime *is* the ARC-AGI-3 regime (frontier systems score below 1%), and the finding that a teacher need not be able to solve the hard problems to generate useful stepping stones is the licence for a small model to bootstrap. The result that question *well-posedness* beats solution correctness also transfers: an ARC-AGI-3 teacher must generate valid, playable environments, and need not solve them.
- **Reusable structure:** The grounded teacher reward (student's improvement on a held-out hard set) — adopt directly, with held-out ARC-AGI-3 games as the hard set; and the diversity-collapse comparison against an intrinsic-learnability baseline as a mandatory ablation.
- **BibTeX:** 

```bibtex
@misc{sundaram2026teaching,
  title         = {{Teaching Models to Teach Themselves: Reasoning at the Edge of Learnability}},
  author        = {Sundaram, Shobhita and Quan, John and Kwiatkowski, Ariel and Ahuja, Kartik and Ollivier, Yann and Kempe, Julia},
  year          = {2026},
  eprint        = {2601.18778},
  archivePrefix = {arXiv},
  primaryClass  = {cs.LG},
  url           = {https://arxiv.org/abs/2601.18778}
}
```

### [SOAR-ProgSynth] — Self-Improving Language Models for Evolutionary Program Synthesis: A Case Study on ARC-AGI
- **Authors / Year / Venue:** Julien Pourcel, Cédric Colas, Pierre-Yves Oudeyer / 2025 (v2 2026-03) / ICML 2025, PMLR 267 (journal reference on the arXiv record).
- **Link:** arXiv:2507.14172
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2507.14172.json`); the journal-ref field states ICML 2025 / PMLR 267.
- **Type:** method
- **Problem:** Evolutionary search over programs is bounded by the fixed capability of the LLM doing the sampling — search cannot get better at searching.
- **Method:** SOAR alternates two phases. (1) An evolutionary search in which the LLM samples and refines candidate programs. (2) A **hindsight learning** phase that converts search attempts — including failed ones — into valid problem–solution pairs by relabelling them with what they actually achieved, and fine-tunes the LLM's sampling and refinement abilities on those pairs. The next search round is therefore run by a better searcher. The task distribution is fixed; what improves is the proposer of *solutions*.
- **Verification signal:** executable check — programs are run against the ARC-AGI input/output pairs.
- **What changes:** weights, plus the search population.
- **Results that matter:** Significant gains across model scales and iterations, with positive transfer between the sampling and refinement fine-tuning tasks; the improvements carry over to test-time adaptation, letting SOAR solve **52% of the ARC-AGI public test set**.
- **Limitations / criticisms:** Static-format ARC-AGI-1, not the interactive benchmark; hindsight relabelling on ARC depends on grid-pair supervision that ARC-AGI-3 does not provide; requires fine-tuning, so it is not a frozen-weights method.
- **Relevance to this FYP (1–5) and why:** **4.** The closest ARC-family precedent for a self-improvement loop, and the source of the 52% figure the internal briefing cites. Its structural lesson matters more than its numbers: **failed attempts become training data once relabelled by what they achieved** — and in ARC-AGI-3, a failed attempt still produces a trajectory whose reached states can be relabelled as goals.
- **Reusable structure:** Hindsight relabelling of failed rollouts into valid (task, solution) pairs — the mechanism that makes a near-0% success regime trainable without a teacher at all. Cross-referenced from `topic3-frozen-weights.md` for its test-time adaptation result.
- **BibTeX:** 

```bibtex
@misc{pourcel2025selfimproving,
  title         = {{Self-Improving Language Models for Evolutionary Program Synthesis: A Case Study on ARC-AGI}},
  author        = {Pourcel, Julien and Colas, Cédric and Oudeyer, Pierre-Yves},
  year          = {2025},
  eprint        = {2507.14172},
  archivePrefix = {arXiv},
  primaryClass  = {cs.LG},
  url           = {https://arxiv.org/abs/2507.14172},
  note          = {Proceedings of the 42 nd International Conference on Machine Learning, Vancouver, Canada. PMLR 267, 2025}
}
```

### [MetaEvolve] — Teaching LLMs to Self-Evolve: Cultivating Core Meta-Skills with Reinforcement Learning
- **Authors / Year / Venue:** Shujin Wu, Cheng Qian, Xiusi Chen, Heng Ji / 2026 / arXiv preprint (no venue on the record).
  **Naming note:** the issue calls this "MetaEvolve"; that is the framework's name inside the paper, not the paper's title.
- **Link:** arXiv:2607.21971
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2607.21971.json`).
- **Type:** method
- **Problem:** Evolutionary self-improvement frameworks such as AlphaEvolve work at inference time, but the models inside them were never trained to be good at multi-round refinement. The paper's hypothesis is that "self-reflection with environment feedback" is a *meta-skill* that post-training neglects.
- **Method:** Three parts. (1) A data-synthesis pipeline that builds **evolution trajectories**: a current program, its fitness score (combining correctness and efficiency), and the history of prior attempts. (2) Evolution-aware RL with verifiable rewards derived from test-case execution. (3) Inference-time evolutionary search using the resulting model. The training target is thus not "solve this problem" but "improve on your own previous attempt given its score".
- **Verification signal:** executable check — test-case execution, giving continuous fitness rather than binary correctness.
- **What changes:** weights (the meta-skill), then context at inference (the attempt history).
- **Results that matter:** Across seven coding benchmarks, +10.01% absolute over the strongest baseline in-distribution and **+24.12% out-of-distribution**; on open-ended algorithm-optimisation problems entirely outside the training domain, a **46.9% relative** improvement.
- **Limitations / criticisms:** No peer-review record; trained and evaluated primarily in code, where fitness is cheap; the out-of-distribution claims rest on the authors' own task selection.
- **Relevance to this FYP (1–5) and why:** **5.** Two things transfer directly. First, **fitness combining correctness and efficiency** is exactly ARC-AGI-3's scoring shape, and this is the only paper in the corpus that trains on such a fitness. Second, the out-of-domain transfer result supports the FYP's most speculative move: practise self-improvement in a cheap verifiable domain, then deploy the meta-skill in ARC-AGI-3 where rollouts are expensive.
- **Reusable structure:** The evolution-trajectory training format — (current attempt, its fitness, history of prior attempts) → better attempt — which is directly constructible from ARC-AGI-3 replays and scores.
- **BibTeX:** 

```bibtex
@misc{wu2026teaching,
  title         = {{Teaching LLMs to Self-Evolve: Cultivating Core Meta-Skills with Reinforcement Learning}},
  author        = {Wu, Shujin and Qian, Cheng and Chen, Xiusi and Ji, Heng},
  year          = {2026},
  eprint        = {2607.21971},
  archivePrefix = {arXiv},
  primaryClass  = {cs.LG},
  url           = {https://arxiv.org/abs/2607.21971}
}
```

### [Learnability] — Learning to Reason at the Frontier of Learnability
- **Authors / Year / Venue:** Thomas Foster, Anya Sims, Johannes Forkel, Mattie Fellows, Jakob Foerster / 2025 (v6 2026-04) / arXiv preprint (no venue on the record).
- **Link:** arXiv:2502.12272
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2502.12272.json`).
- **Type:** empirical study / method
- **Problem:** In RL post-training, how much of each training step is actually wasted?
- **Method:** The paper first *measures* the problem: across PPO and VinePPO on two standard datasets, it shows that throughout training many questions are solved by all sampled attempts (already learned) or by none (no signal). It then imports **sampling for learnability** from the RL literature — prioritise questions with high *variance* of success — and applies it to LLM RL training.
- **Verification signal:** mechanical answer checking (the success/failure that variance is computed over).
- **What changes:** the task distribution (a sampling policy over a fixed dataset) and weights.
- **Results that matter:** The curriculum consistently improves training performance across multiple algorithms and datasets. The more valuable result is diagnostic: a large fraction of training questions provide *no* gradient signal at any point in training.
- **Limitations / criticisms:** Needs several samples per question to estimate variance, which costs rollouts; success-variance conflates learnability with stochasticity; gains are consistent but not dramatic.
- **Relevance to this FYP (1–5) and why:** **5.** This is the cheapest defensible learnability signal, it needs no teacher model at all, and its diagnostic — measure what fraction of your training tasks give any signal — is a measurement the FYP should make on ARC-AGI-3 *before* building anything, since a benchmark where frontier systems score below 1% is very likely almost entirely in the all-fail bucket.
- **Reusable structure:** Success-variance prioritisation over a fixed task pool, and the "fraction of tasks with non-degenerate success rate" diagnostic plot — the single most useful early experiment suggested by this corpus.
- **BibTeX:** 

```bibtex
@misc{foster2025learning,
  title         = {{Learning to Reason at the Frontier of Learnability}},
  author        = {Foster, Thomas and Sims, Anya and Forkel, Johannes and Fellows, Mattie and Foerster, Jakob},
  year          = {2025},
  eprint        = {2502.12272},
  archivePrefix = {arXiv},
  primaryClass  = {cs.LG},
  url           = {https://arxiv.org/abs/2502.12272}
}
```

### [GASP] — GASP: Guided Asymmetric Self-Play For Coding LLMs
- **Authors / Year / Venue:** Swadesh Jana, Cansu Sancaktar, Tomáš Daniš, Georg Martius, Antonio Orvieto, Pavel Kolev / 2026 / ICLR 2026 Workshop on AI with Recursive Self-Improvement (Spotlight) and ICLR 2026 Workshop on Lifelong Agents — stated on the arXiv record.
- **Link:** arXiv:2603.15957
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2603.15957.json`); the comment field states both workshop acceptances.
- **Type:** method
- **Problem:** Asymmetric self-play is goal-agnostic: not every hard problem is an *informative* one, and ungrounded teachers drift toward hard-looking but useless tasks.
- **Method:** GASP grounds the curriculum in **real-data "goalpost" questions** identified as posing a hard exploration challenge to the model. During self-play the teacher first generates an *easier* variant of a goalpost question, then a *harder* variant of that easier one, progressively closing the gap to the goalpost. The curriculum therefore has a fixed external target rather than wandering in task space.
- **Verification signal:** executable check (code tests) for the solver; the goalpost set anchors the teacher.
- **What changes:** the task distribution and weights.
- **Results that matter:** +2.5% pass@20 on LiveCodeBench over *unguided* asymmetric self-play, and — more informative than the delta — the teacher's curriculum solves hard goalpost questions that remain out of reach for all baselines.
- **Limitations / criticisms:** Requires a real-data goalpost set, so it is not zero-data; workshop-scale evaluation; the easier-then-harder schedule is hand-designed rather than learned.
- **Relevance to this FYP (1–5) and why:** **5.** ARC-AGI-3 hands the project a natural goalpost set — the public games the agent currently fails — and the easy-variant-then-harder-variant schedule is directly implementable by editing environments ([ACCEL]'s operator with GASP's direction). This is the most practical recipe in §3 for a benchmark where the target tasks are known but unsolved.
- **Reusable structure:** Goalpost anchoring plus the down-then-up variant schedule; and the "solves goalposts no baseline can" reporting style, which is more meaningful than an aggregate delta when baseline scores are near zero.
- **BibTeX:** 

```bibtex
@misc{jana2026gasp,
  title         = {{GASP: Guided Asymmetric Self-Play For Coding LLMs}},
  author        = {Jana, Swadesh and Sancaktar, Cansu and Daniš, Tomáš and Martius, Georg and Orvieto, Antonio and Kolev, Pavel},
  year          = {2026},
  eprint        = {2603.15957},
  archivePrefix = {arXiv},
  primaryClass  = {cs.LG},
  url           = {https://arxiv.org/abs/2603.15957},
  note          = {Accepted at ICLR 2026 Workshop on AI with Recursive Self-Improvement (RSI 2026) as Spotlight, and}
}
```

### [SkillSP] — Skill Self-Play: Pushing the Frontier of LLM Capability with Co-Evolving Skills
- **Authors / Year / Venue:** Siyuan Huang, Pengyu Cheng, Haotian Liu, Tao Chen, Yihao Liu, Jingwei Ni, Shijie Zhou, Ziyi Yang, et al. (13 authors) / 2026 / arXiv preprint (no venue on the record).
- **Link:** arXiv:2607.22529
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2607.22529.json`).
- **Type:** method
- **Problem:** A stated dilemma between task diversity and verification reliability: environment-bound self-evolution has precise feedback but a narrow domain, while open-ended self-generation has a wide task space and unreliable verification, so misleading rewards pollute the loop.
- **Method:** **Agent skills** are proposed as the middle ground: each skill guarantees deep, verifiable execution within a specific scenario, while dynamic routing across skills preserves open-ended variety. Three components co-evolve under RL — a proposer that generates tasks conditioned on dynamically sampled skills, a solver that explores solutions, and a **skill controller** that collects execution feedback to update and expand the skill library.
- **Verification signal:** executable check, per skill (each skill carries its own verifiable execution scenario).
- **What changes:** weights, the task distribution, and memory (the skill library) — the only entry in this corpus that changes all three.
- **Results that matter:** Consistent gains on tool-use and reasoning benchmarks, reported both as raising the ceiling of competent backbones and as producing large turnarounds for initially misaligned models. No single headline number in the abstract.
- **Limitations / criticisms:** No peer-review record; three co-evolving components make attribution of the gains difficult without ablations the abstract does not describe; skills must be authorable in the first place.
- **Relevance to this FYP (1–5) and why:** **4.** It names the FYP's central design tension exactly — diversity versus verifiability — and its resolution maps onto ARC-AGI-3 unusually well: each *game* is a skill-like unit with its own reliable verifier, and routing across games preserves diversity without ever leaving verifiable ground.
- **Reusable structure:** The skill-as-verifiable-scenario unit and the dynamic routing controller; the diversity-vs-verifiability framing is the right way to motivate the FYP's design choices in the write-up.
- **BibTeX:** 

```bibtex
@misc{huang2026skill,
  title         = {{Skill Self-Play: Pushing the Frontier of LLM Capability with Co-Evolving Skills}},
  author        = {Huang, Siyuan and Cheng, Pengyu and Liu, Haotian and Chen, Tao and Liu, Yihao and Ni, Jingwei and Zhou, Shijie and Yang, Ziyi and Jiang, Gangwei and Zhou, Mengyu and Cheng, Yu and Jiang, Xiaoxi and Jiang, Guanjun},
  year          = {2026},
  eprint        = {2607.22529},
  archivePrefix = {arXiv},
  primaryClass  = {cs.CL},
  url           = {https://arxiv.org/abs/2607.22529}
}
```

---

## §4 Failure modes: collapse, hacking, and what keeps a loop alive

### [R-Diverse] — R-Diverse: Mitigating Diversity Illusion in Self-Play LLM Training
- **Authors / Year / Venue:** Gengsheng Li, Jinghan He, Shijie Wang, Dan Zhang, Ruiqi Liu, Renrui Zhang, Zijun Yao, Junfeng Fang, et al. (10 authors) / 2026 / arXiv preprint (no venue on the record).
- **Link:** arXiv:2602.13103
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2602.13103.json`).
- **Type:** empirical study / method
- **Problem:** [R-Zero]-style Challenger–Solver loops show **non-sustained improvement** — early gains degrade as self-play continues.
- **Method:** The paper names the mechanism **Diversity Illusion**: training signals look diverse but collapse onto recurring underlying patterns. It decomposes this into *Local* Diversity Illusion (diversity enforced only within a batch, which induces cross-iteration mode cycling) and *Surface* Diversity Illusion (questions that vary superficially but exercise near-identical reasoning skills). The fix has two matching parts: a Memory-Augmented Penalty using a persistent memory bank to discourage recycling across iterations, and Skill-Aware Measurement, which measures diversity by the *skills exercised* rather than by surface variation.
- **Verification signal:** inherits the underlying self-play loop's signal; the contribution is a diversity measure, not a correctness measure.
- **What changes:** the task distribution (via diversity regularisation) and weights.
- **Results that matter:** Across 10 maths and general reasoning benchmarks, R-Diverse sustains gains over more iterations and outperforms prior self-play methods. The finding that matters most is the diagnosis: **batch-local diversity enforcement produces cross-iteration mode cycling**, so a loop can look diverse at every step while repeating itself globally.
- **Limitations / criticisms:** No peer-review record; skill-aware measurement needs a skill taxonomy, which is domain-specific; the sustained-gain claim is over a limited number of iterations.
- **Relevance to this FYP (1–5) and why:** **5.** The FYP's prototype follows the R-Zero architecture, so this is a direct, documented failure mode of the chosen design. The distinction between surface and functional diversity is also precisely the one that matters in ARC-AGI-3, where two generated environments can look different and pose the identical inference problem.
- **Reusable structure:** The persistent cross-iteration memory penalty (not just within-batch), and skill-level rather than surface-level diversity measurement — for ARC-AGI-3 the analogue is measuring diversity over the *rules* an environment exercises, not over its pixels.
- **BibTeX:** 

```bibtex
@misc{li2026rdiverse,
  title         = {{R-Diverse: Mitigating Diversity Illusion in Self-Play LLM Training}},
  author        = {Li, Gengsheng and He, Jinghan and Wang, Shijie and Zhang, Dan and Liu, Ruiqi and Zhang, Renrui and Yao, Zijun and Fang, Junfeng and Guo, Haiyun and Wang, Jinqiao},
  year          = {2026},
  eprint        = {2602.13103},
  archivePrefix = {arXiv},
  primaryClass  = {cs.LG},
  url           = {https://arxiv.org/abs/2602.13103}
}
```

### [VocabDropout] — Vocabulary Dropout for Curriculum Diversity in LLM Co-Evolution
- **Authors / Year / Venue:** Jacob Dineen, Aswin RRV, Zhikun Xu, Ben Zhou / 2026 (v4 2026-07) / COLM 2026 (venue stated on the arXiv record).
- **Link:** arXiv:2604.03472
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2604.03472.json`); the comment field states "Accepted to COLM 2026".
- **Type:** method
- **Problem:** In co-evolutionary self-play the proposer converges early to a narrow set of problems that satisfy the reward function, and the collapsed curriculum then teaches the solver nothing.
- **Method:** **Vocabulary dropout** randomly masks the proposer's output logits during both policy training and curriculum generation. The mask is hard and non-stationary, so the proposer cannot lock into fixed token sequences. The authors frame this as supplying an explicit action-space constraint — filling the structural role that *game rules* play in classical self-play, which language-space self-play otherwise lacks.
- **Verification signal:** inherits R-Zero's; the contribution is a constraint on the proposer.
- **What changes:** the task distribution (proposer output distribution) and weights.
- **Results that matter:** Training Qwen3-4B and Qwen3-8B on mathematical reasoning via R-Zero, vocabulary dropout sustains proposer diversity across lexical, semantic **and functional** measures, and improves the solver by an average of **+4.4 points at 8B**, with the largest gains on competition-level benchmarks.
- **Limitations / criticisms:** A blunt instrument — masking logits is not targeted at the semantic collapse it aims to prevent; demonstrated on maths with two model sizes; the analogy to game rules is a framing claim rather than a result.
- **Relevance to this FYP (1–5) and why:** **4.** The framing is the contribution for this project: classical self-play is stable partly because *rules* constrain the action space, and language self-play has no such constraint. ARC-AGI-3 is closer to classical self-play than to language self-play — an environment editor has a small, structured action space by construction — which is a genuine argument that the FYP's setting is *less* collapse-prone than the LLM literature it borrows from.
- **Reusable structure:** The explicit-action-space-constraint principle for the proposer (rather than the logit-masking implementation), plus the three-level diversity measurement (lexical, semantic, functional).
- **BibTeX:** 

```bibtex
@misc{dineen2026vocabulary,
  title         = {{Vocabulary Dropout for Curriculum Diversity in LLM Co-Evolution}},
  author        = {Dineen, Jacob and RRV, Aswin and Xu, Zhikun and Zhou, Ben},
  year          = {2026},
  eprint        = {2604.03472},
  archivePrefix = {arXiv},
  primaryClass  = {cs.CL},
  url           = {https://arxiv.org/abs/2604.03472},
  note          = {Accepted to COLM 2026}
}
```

### [LearnableInfoGain] — Self-Play Only Evolves When Self-Synthetic Pipeline Ensures Learnable Information Gain
- **Authors / Year / Venue:** Wei Liu, Siya Qi, Yali Du, Yulan He / 2026 (v2 2026-05) / ICML 2026, position-paper track (venue stated on the arXiv record).
- **Link:** arXiv:2603.02218
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2603.02218.json`); the comment field states acceptance to the ICML 2026 position paper track.
- **Type:** position (with supporting experiments)
- **Problem:** Many "self-evolving" proposals are really self-play and plateau quickly; the paper asks what distinguishes a loop that keeps improving from one that does not.
- **Method:** Experiments on a self-play coding task motivate a systems argument: sustainable self-evolution requires a self-synthesised data pipeline whose **learnable information increases across iterations**. The paper names three roles — Proposer (generates tasks), Solver (attempts them), Verifier (provides training signal) — and three system designs that target learnable information gain: asymmetric co-evolution closing a weak-to-strong-to-weak loop across roles; capacity growth expanding parameter and inference-time budgets to match rising information; and proactive information seeking, which introduces external context and new task sources to prevent saturation.
- **Verification signal:** executable check in the supporting coding experiments; the position concerns the *role* of the verifier in the loop.
- **What changes:** n/a for the position; the analysis covers task distribution, weights and inference budget together.
- **Results that matter:** The load-bearing claim is diagnostic rather than numeric: **a loop that synthesises more data without increasing learnable information will plateau**, which is the common mechanism behind the collapses reported by [R-Diverse] and [VocabDropout].
- **Limitations / criticisms:** A position paper — the three prescriptions are argued, not demonstrated at scale; "learnable information gain" is not given an operational estimator, which is the obvious follow-up.
- **Relevance to this FYP (1–5) and why:** **5.** It supplies the triadic vocabulary (Proposer / Solver / Verifier) that this survey's taxonomy uses, and its third prescription — *proactive information seeking*, i.e. bringing in new external task sources — is unusually well matched to ARC-AGI-3, where 135 handcrafted environments are an external, non-self-generated source of genuinely new information that the loop can draw on to avoid saturation.
- **Reusable structure:** The Proposer/Solver/Verifier decomposition as the FYP's system description; and "does learnable information increase across iterations?" as the question the evaluation must actually answer, rather than "did the score go up once".
- **BibTeX:** 

```bibtex
@misc{liu2026selfplay,
  title         = {{Self-Play Only Evolves When Self-Synthetic Pipeline Ensures Learnable Information Gain}},
  author        = {Liu, Wei and Qi, Siya and Du, Yali and He, Yulan},
  year          = {2026},
  eprint        = {2603.02218},
  archivePrefix = {arXiv},
  primaryClass  = {cs.LG},
  url           = {https://arxiv.org/abs/2603.02218},
  note          = {accepted by ICML 2026 position paper track}
}
```

### [VHG] — Verifier-Backed Hard Problem Generation for Mathematical Reasoning
- **Authors / Year / Venue:** Yuhang Lai, Jiazhan Feng, Yee Whye Teh, Ning Miao / 2026 / arXiv preprint (no venue on the record).
- **Link:** arXiv:2605.06660
- **Verified:** yes — record retrieved and cached (`refs/arxiv/2605.06660.json`).
- **Type:** method
- **Problem:** LLMs are poor at producing *valid, challenging, novel* problems: naive self-play frequently yields invalid problems because the setter reward-hacks difficulty.
- **Method:** VHG adds an **independent verifier** to the usual setter–solver pair, making it a three-party game. The setter's reward is jointly determined by problem *validity* (judged by the verifier) and *difficulty* (judged by the solver), so a problem that is hard only because it is broken scores zero. Two verifier variants are instantiated: a hard symbolic verifier and a soft LLM-based verifier, evaluated on indefinite-integral and general mathematical reasoning tasks.
- **Verification signal:** executable/symbolic check (hard variant) versus learned reward model (soft variant) — the comparison is the point.
- **What changes:** the task distribution and weights.
- **Results that matter:** VHG substantially outperforms all baselines; the structural result is that **separating validity from difficulty in the setter's reward removes the dominant reward-hacking channel** in setter–solver self-play.
- **Limitations / criticisms:** No peer-review record; maths-specific; the soft LLM verifier reintroduces exactly the biased-judge risk [BlindCurator] (Topic 1) formalises, and the abstract does not report how much worse it is than the symbolic one.
- **Relevance to this FYP (1–5) and why:** **5.** The validity/difficulty factorisation is the single most directly applicable design rule for an ARC-AGI-3 teacher. A generated environment must be *playable and winnable* (validity — checkable by running it) before its difficulty is even considered, and the benchmark supplies both checks mechanically. This is how the FYP avoids the degenerate-task pitfall the internal briefing flags.
- **Reusable structure:** The three-party setter/solver/verifier game with a factorised setter reward = validity × difficulty; and the hard-vs-soft verifier ablation, which directly measures the cost of giving up a mechanical check.
- **BibTeX:** 

```bibtex
@misc{lai2026verifierbacked,
  title         = {{Verifier-Backed Hard Problem Generation for Mathematical Reasoning}},
  author        = {Lai, Yuhang and Feng, Jiazhan and Teh, Yee Whye and Miao, Ning},
  year          = {2026},
  eprint        = {2605.06660},
  archivePrefix = {arXiv},
  primaryClass  = {cs.LG},
  url           = {https://arxiv.org/abs/2605.06660}
}
```
