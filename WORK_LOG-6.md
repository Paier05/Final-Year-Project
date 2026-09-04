# Work Log — Issue #6: [Research] Literature survey: self-evolving harnesses, teacher–student training, and non-parametric capability gain

**Issue:** https://github.com/Paier05/Final-Year-Project/issues/6
**Branch:** docs/6-literature-survey-self-evolution
**Started:** 2026-09-04

## Understanding the issue

The FYP is about self-evolution / recursive self-improvement applied to **ARC-AGI-3** (interactive,
no-instruction grid environments, scored by `min(1, human_baseline_actions/agent_actions)^2`).
Two internal briefing notes exist (`Documentation_Generated/*.pdf`) but between them they cite only
~6 papers. This issue asks for a **proper, auditable literature corpus**: ≥10 (target ~20) verified
papers for each of three topics, each written up with a fixed per-paper template, plus a synthesis
that produces a taxonomy, lineages, disagreements, an ARC-AGI-3 transfer analysis, a gap statement,
and evaluation-design notes.

Three topics:
1. **Harness engineering / self-modifying scaffolds** — the thing that improves is the scaffold
   (agent loop, prompts, tools, memory, the agent's own code), not the weights.
2. **Teacher–student / proposer–solver structures** — an explicit task/curriculum generator
   optimized against the solver's learning.
3. **Capability gain without parameter updates** — measurable improvement with frozen weights.
   Every entry here must be classified as (a) new capability, (b) better elicitation, (c) unclear.

The deliverable is a `literature/` directory (README, three topic files, adjacent, synthesis,
taxonomy, refs.bib, search-log).

**Hard constraint from the issue:** citation integrity. Every arXiv ID / title / author list / venue
must be confirmed against the actual record. The seed IDs given in the issue came from internal notes
and are explicitly *not* pre-verified — several of them look like they may have been produced by an
LLM writing the briefing PDFs, so checking them is part of the job, and mismatches must be reported.

### Assumptions made
- **A1.** "Opening the abstract page" is satisfied by retrieving the canonical record from the
  arXiv API / abstract page over the network and caching the returned metadata (title, authors,
  date, abstract, DOI/journal ref) locally. The cached record is what the write-up is based on;
  nothing is written from memory of a title.
- **A2.** Papers are cached under `literature/refs/` per workflow step 5b, so every claim can be
  re-checked later without re-fetching. This directory is committed.
- **A3.** Where the FYP context is dated (ARC-AGI-3 launched March 2026; today 2026-09-04), the
  2026 material is treated as primary and older work is included only where it anchors a lineage.

## Plan

1. Preconditions: verify remote/auth/clean tree, branch off an up-to-date `main`. *(done)*
2. Read the two internal briefing notes to lock the framing and extract the seed citations. *(done)*
3. Build a small fetch/cache helper so every citation is verified against a real record and the
   record is stored in `literature/refs/`.
4. **Verify the seed leads first** — the issue's seed list for all three topics. Report every ID
   that does not resolve, and search by title to find the real record.
5. Snowball per topic (references + citations of each seed) across arXiv, Semantic Scholar,
   OpenReview, ACL Anthology, Papers with Code, and the ARC Prize blog/docs.
6. Write `topic1-harness.md`, `topic2-teacher-student.md`, `topic3-frozen-weights.md` using the
   exact per-paper template, committing per topic.
7. Write `taxonomy.md`, `synthesis.md`, `adjacent.md`, `refs.bib`, `search-log.md`, `README.md`.
8. Verify per workflow 5b: every number carries a reference or `[unverified]`; every issue task
   answered or explicitly marked incomplete; refs.bib compiles clean; open questions non-empty.
9. Push, open PR with `Closes #6`, comment on the issue.

## Progress log

### 2026-09-04 — Branch and framing
- What I did: checked preconditions (remote `Paier05/Final-Year-Project`, `gh` authenticated as
  Paier05, clean tree), updated `main`, branched `docs/6-literature-survey-self-evolution`,
  extracted the text of both internal briefing PDFs (via `pypdf`, since no PDF renderer is present).
- Why: the briefings define the framing the review has to serve, and they are the source of the
  unverified seed citations.
- Result / what I found: the briefings give the benchmark mechanics (64x64 grids, 16 colours,
  135 environments, ~1:5 public:private, second-best-of-10 human baseline, level weights, squared
  efficiency score, no-internet Kaggle sandbox, mandatory open-sourcing) and the teacher–student
  loop framing (propose → attempt → verify → reward → escalate). Confirmed the shell has outbound
  HTTPS, so citations can be verified against live records rather than from memory.
- Next step: build the fetch/cache helper and run every seed ID through it.


### 2026-09-04 — verification pass (workflow step 5b)
- What I did: wrote `literature/tools/checkcorpus.py` and ran it over all 89 entries. It checks
  three things: (1) every template field present and non-blank; (2) every `[Handle]`
  cross-reference resolves to an entry that actually exists; (3) every numeric token in a
  "Results that matter" line appears in the cached record for that paper.
- Why: workflow 5b says "every quantitative claim carries a reference or is marked [unverified]" and
  "re-read the draft and check each number". With ~90 entries that is not reliable by eye.
- Result / what I found: two real defects, both fixed.
  * A dangling cross-reference `[GroundingAleatoric]` in the PLR entry — the paper is in
    `adjacent.md`, which does not use handles. Replaced with the title and arXiv ID.
  * StateM's "roughly a 38x cost reduction" was **my arithmetic** ($574.68 / $15), not a figure the
    paper states. Now labelled as derived. Worth noting the checker did *not* catch this: "38"
    happens to appear elsewhere in that abstract ("less than $38 of adaptation"), so it passed by
    coincidence. **The number checker rules out invented numbers; it does not rule out coincidental
    matches, and I found this one by reading.** Recorded so nobody over-trusts the tool.
  * Also audited quoting against the issue's "under 15 words, one quote per source" rule. Two
    entries (DarwinX, Weng2026) carried two verbatim quotations each; reduced to one. Added an
    explicit quoting convention to each topic file header so the rule is auditable.
- Final state: `checkcorpus.py` reports 0 problems and 0 numbers for review; `checkbib.py` reports
  120 entries, 120 unique keys, structurally clean.

## Open questions / risks

Kept deliberately non-empty per workflow 5b: a review with no stated uncertainty has been summarised,
not checked.

- **R1 (resolved).** Several seed arXiv IDs came from LLM-written briefing notes and were suspect.
  All nine resolved. Two naming problems found and reported in `search-log.md` §2.
- **R2 (live, and the biggest one).** Topic 3's conclusion depends on the model/system distinction:
  [Twin] and [Tycho] are classified "(a) new capability **at the system level**" while their models
  gain nothing. A supervisor could reasonably reject that framing and call it all elicitation. The
  argument is made explicitly in `synthesis.md` §3.1 rather than assumed — but it should be tested
  with the supervisor before the chapter is built on it.
- **R3 (live).** The ARC-AGI-3 environment-count discrepancy is unresolved: briefing says 135
  environments at ~1:5 public:private; the papers describe 25 public games / 183 levels and a 55-game
  private evaluation. Marked `[unverified]`, needs `docs.arcprize.org`.
- **R4 (live).** Every interactive ARC-AGI-3 result in the corpus except one is public-set only, and
  the papers' own authors say the public set is saturated. **Any FYP framing built on beating a
  public-set number is built on sand.** The single private-set datapoint found is RHAE 0.30 from a
  competition entry linked by [BenchmarkValidity] — that number has not been independently checked.
- **R5 (live).** Numbers come from cached abstracts and records, not from full PDFs (limitation L6).
  The automated checker confirms nothing was invented, but it cannot confirm a figure means what the
  entry says it means in context. Before any figure carries argumentative weight in the dissertation,
  read the relevant section of the paper.
- **R6 (live).** `checkcorpus.py`'s number check can pass by coincidence — it did for one derived
  ratio (see the verification-pass entry above). Treat it as a screen against fabrication, not as
  proof of correct attribution.
- **R7 (live).** Search coverage is incomplete in four documented ways (`search-log.md` §7): Papers
  with Code's API returned nothing, ACL Anthology was not searched from its own side, Google Scholar
  was not queried, and two-directional snowballing was rate-limited and replaced by vocabulary-based
  arXiv search. The Gödel Agent case shows this matters: an ACL 2025 paper central to the Topic 1
  lineage was missed by every arXiv query and found only via OpenReview.
- **R8 (live, but low).** Venue information is under-reported by policy — entries reading "no venue
  on the record" may well be published. Worth a pass with a Semantic Scholar API key before the
  bibliography is final, since a reviewer may read "arXiv preprint" as a quality signal.
- **R9 (housekeeping, for the user's attention).** `main` has no `.gitignore` — it exists only on
  `experiment/4-mini-r-zero-toy-demo`. So on this branch the leftover working-tree files from that
  experiment (`experiments/mini_r_zero/__pycache__/`, `_diag_*.py`, `_runall.sh`, `_summarize.py`,
  and ~16 MB of `results/seed_cache/*.npz`) show as untracked rather than ignored. I briefly and
  accidentally committed them with a `git add -A`, then reset that commit and re-committed only the
  literature files; **nothing was deleted from disk and no other branch was touched.** Recommend
  moving `.gitignore` onto `main` so this cannot recur.

## Summary

### What changed
A new `literature/` directory containing the citation-verified corpus asked for by issue #6:

- `topic1-harness.md` — **31 entries** on harness engineering and self-modifying scaffolds.
- `topic2-teacher-student.md` — **27 entries** on proposer-solver / curriculum structures.
- `topic3-frozen-weights.md` — **31 entries** on capability gain with frozen weights, each carrying
  the required new-capability / elicitation / unclear classification.
- `taxonomy.md` — the filled two-axis table with every entry placed and six empty-cell findings.
- `synthesis.md` — all six required sections plus a seventh on chapter structure.
- `adjacent.md` (25 one-liners), `search-log.md`, `refs.bib` (120 entries), `README.md`.
- `refs/` — 127 cached source records, committed, so every claim can be re-checked.
- `tools/` — `fetch.py` (retrieval, caching, BibTeX generation), `checkbib.py`, `checkcorpus.py`.

89 full entries against a required minimum of 30 and a target of ~60.

### Why
The two internal briefing notes cite ~6 papers between them. The review needed breadth, a taxonomy,
and an explicit argument for where the project sits. The method chosen — fetch the canonical record,
cache it, write from the cache, and generate the BibTeX from that same cache — was driven by the
issue's citation-integrity bar: it makes it structurally impossible for a citation's metadata and its
description to disagree.

### How it was verified
- `python literature/tools/checkcorpus.py` -> 89 entries, **0 problems**: no missing or blank template
  fields, all 89 marked `Verified: yes`, no dangling cross-references, and every number in every
  "Results that matter" line traced to the cached record.
- `python literature/tools/checkbib.py literature/refs.bib` -> **120 entries, 120 unique keys, clean**
  (balanced braces, required fields, no unescaped BibTeX specials). No LaTeX toolchain exists in this
  environment, so this is a structural check and the README says so rather than claiming a bibtex run.
- All nine seed arXiv IDs from the issue verified against the live record; two naming problems found
  and reported (the SOAR collision, and MetaEvolve being a framework name rather than a title).
- Manual checks: no paper written up fully in two topic files; quoting audited against the issue's
  one-quote/15-word rule.

### The three findings that matter most
1. **The briefing's ARC-AGI-3 numbers are obsolete by ~two orders of magnitude.** [Twin]
   (arXiv:2608.14490) reports a frozen model going 7.8% -> 61.1% (off-the-shelf harness) -> 93.3%
   (self-authored world model); [Tycho] (arXiv:2607.28287) reports 100.00 RHAE on all 183 public
   levels. The briefing's "frontier ~0.5%, best preview agent ~12.6%" was a March 2026 snapshot.
2. **But the public set may not measure anything.** [BenchmarkValidity] (arXiv:2605.25931) finds all
   25 public games reachable by non-intelligent strategies, with a library-level bug bypassing 18 in
   one step; [WMAblation] (arXiv:2607.15439) concludes its own near-perfect results indicate
   public-set saturation only, and finds backbone/reasoning-effort differences often exceed harness
   differences. So the FYP's question moves to the private set, the no-internet constraint, and
   small models.
3. **The R-Zero architecture prototyped on the sibling branch has two documented failure modes.**
   [R-Diverse] and [VocabDropout], independently, report non-sustained improvement and proposer
   collapse in exactly that design; [SOAR-Teacher] reports that grounded teacher rewards beat the
   intrinsic learnability rewards the briefing recommends. Fixes exist for all three.

### 2026-09-04 — Seed verification complete; all nine seed IDs resolve
- What I did: ran every seed arXiv ID from the issue through the arXiv API and cached the records.
- Why: the issue states the seed IDs came from internal notes and are not pre-verified, and flags
  fabricated citations as an academic-integrity problem.
- Result / what I found: **all nine resolve to real papers**, but two naming problems need reporting:
  (1) the issue lists arXiv:2601.18778 as "(SOAR)" *and* arXiv:2507.14172 as "SOAR" — these are two
  different papers by different groups that both use the name SOAR (Sundaram et al., asymmetric
  self-play with meta-RL; Pourcel/Colas/Oudeyer, evolutionary program synthesis on ARC-AGI). The
  corpus disambiguates them as [SOAR-Teacher] and [SOAR-ProgSynth]. (2) arXiv:2607.21971 is titled
  "Teaching LLMs to Self-Evolve: Cultivating Core Meta-Skills with Reinforcement Learning" — the
  issue refers to it as "MetaEvolve", which is the name of the *framework* in that paper, not its
  title. Both recorded in `search-log.md`.
- Next step: snowball each topic, then write the topic files.

### 2026-09-04 — Tooling decision: verify over the network, cache everything
- What I did: confirmed the shell has outbound HTTPS and wrote `literature/tools/fetch.py`
  (arXiv API, Semantic Scholar Graph API, page caching, BibTeX generation from the fetched record).
- Why: 60+ entries cannot be verified reliably by hand, and hand-typed BibTeX is exactly where
  fabricated metadata creeps in. Generating BibTeX from the same cached record that the prose is
  written from means the citation and the description cannot drift apart.
- Result / what I found: 113 arXiv records cached under `literature/refs/arxiv/`. arXiv rate-limits
  aggressively (HTTP 429) — added a 10s per-host throttle after the first batch of failures.
  Semantic Scholar is much less reliable anonymously: roughly half of the venue lookups failed even
  with retries. **Decision: venue is stated only when the arXiv record's journal-ref or comment field
  confirms it, or when a Semantic Scholar lookup succeeded; otherwise the entry says "no venue on
  the record".** This is deliberately conservative — a wrong venue is a citation error.
- Next step: topic 1.

### 2026-09-04 — topic1-harness.md written (30 entries)
- What I did: wrote Topic 1 in five sections — the Gödel-machine-to-DGM lineage, scaffold/prompt
  optimisation, accumulation (tools/skills/workflows/experience), harness-vs-model empirical
  studies, and failure modes. 29 archival entries plus the Weng blog marked `[non-archival]`.
- Why: the issue's Topic 1 scope; the section split follows the *locus of change* logic the issue
  asks the eventual chapter to use.
- Result / what I found: the 2026 literature is much richer than the briefing notes suggested and
  changes the story in three ways. (a) [HarnessEvo] measured the harness's own contribution by
  fixing the model and varying 35 harness releases — direct evidence that harness churn moves
  benchmark scores at a fixed model. (b) [WorkspaceOpt]/DreamTeam is an ARC-AGI-3 harness paper
  reporting 36% → 38.4% on the 25-game public set with 31% fewer actions — closest prior art found,
  and note this is far above the ~12.6% preview figure in the internal briefing, so the briefing's
  SOTA numbers are already stale. (c) [TextPolicies] is a clean negative result: human-written text
  policies help frozen 7B agents by 5.0 points, but *self-generated* policies do not reliably beat
  fixed prompting — the bottleneck is generating and selecting policies, not applying them.
- Next step: topic 2.

### 2026-09-04 — topic2-teacher-student.md written (27 entries)
- What I did: wrote Topic 2 in four sections — pre-LLM foundations (asymmetric self-play, TSCL,
  GoalGAN, AlphaZero, POET), environment generation / UED (Enhanced POET, PAIRED, PLR, PLR-perp,
  ACCEL, TRACED, OMNI, OMNI-EPIC), the 2025–26 LLM proposer–solver line, and failure modes.
- Why: the issue's Topic 2 scope. Per the issue's instruction to skip static distillation, Self-Instruct
  and WizardLM/Evol-Instruct were moved to `adjacent.md` — in both the teacher does not adapt to the
  student, so they fail the inclusion criterion despite being obvious hits for the search queries.
- Result / what I found:
  * [SOAR-Teacher] is the key paper. Its regime — held-out sets with 0/128 success — is the
    ARC-AGI-3 regime, and it reports that *grounded* teacher rewards (the student's measured
    improvement) beat *intrinsic* learnability rewards and avoid diversity collapse. That contradicts
    the internal briefing, which presents Absolute Zero's intrinsic learnability score as the recipe.
  * Two independent 2026 papers ([R-Diverse], [VocabDropout]) document that R-Zero-style loops —
    the architecture prototyped in `experiments/mini_r_zero/` on the sibling branch — show
    non-sustained improvement and proposer collapse. Both offer fixes. This is the most decision-
    relevant finding for the project's own experiment.
  * [VHG]'s factorised setter reward (validity x difficulty, with an *independent* verifier) is the
    cleanest published answer to the degenerate-task problem the briefing flags as a pitfall.
  * [TRACED]'s transition-prediction error is a curriculum signal that needs no reward at all —
    much better matched to a world-modelling benchmark than value-loss regret.
- Dead end worth recording: I looked for UED work that generates *interactive, goal-unknown* grid
  environments specifically. It does not exist — every UED paper found parameterises a known
  environment with a known reward. That absence is part of the gap statement, not a search failure.
- Next step: topic 3.

### 2026-09-04 — topic3-frozen-weights.md written (31 entries) — and the framing has to change
- What I did: wrote Topic 3 in four sections — search/sampling over a frozen model; learning that
  lives in context, memory or an external world model; a clearly separated test-time-training
  sub-bucket where weights *do* change; and critical/negative results. Every entry carries the
  required new-capability / elicitation / unclear classification.
- Why: the issue's Topic 3 scope and its "required framing".
- Result / what I found — this is the section that changes the project:
  * **The ARC-AGI-3 public set is close to saturated, by frozen-weight harnesses.** [Twin]
    (arXiv:2608.14490) reports the decomposition that matters: the same frozen base model scores
    7.8% played directly, 61.1% with an off-the-shelf harness, and 93.3% with a self-authored
    executable world model (23/25 games, 179/183 levels). [Tycho] (arXiv:2607.28287) reports
    100.00 RHAE with two frontier models, all 183 levels, using 61% fewer scored actions than the
    human baselines. The internal briefing's "frontier ~0.5%, best preview agent ~12.6%" is
    obsolete by roughly two orders of magnitude.
  * **But the public set may not measure anything.** [BenchmarkValidity] (arXiv:2605.25931) reports
    that all 25 public games are reachable by non-intelligent strategies, and that a library-level
    null-coordinate vulnerability bypasses 18 of them in a single step. [WMAblation]
    (arXiv:2607.15439), by the author of the system being ablated, concludes its own near-perfect
    results "indicate public-set saturation only" — and finds that variant differences are often
    smaller than the differences between backbone models and reasoning-effort settings.
  * Consequently the FYP's question is *not* "can a harness beat 1% on ARC-AGI-3" — that is
    answered. The live questions are the private set, contamination (the strong models postdate the
    games), and whether any of this works at small scale. The only small-model datapoint found in
    the whole corpus is AERA at RHAE 0.2116 with Qwen2.5-0.5B.
  * On the required framing: almost everything classifies as **elicitation**. The two entries I
    classified as system-level **new capability** ([Twin], [Tycho]) are honest about the model being
    unchanged, and the only clean model-level (a) is [AlgorithmDistillation]. [RLVR-Elicitation]
    (NeurIPS 2025 Oral) is the methodological anchor: pass@k at large k, base model as upper bound.
- Numbers I could not reconcile, recorded rather than resolved: the internal briefing says 135
  environments at roughly 1:5 public:private; [BenchmarkValidity] refers to 25 public and a
  "full 55-game private evaluation". 25+55 does not equal 135. Flagged `[unverified]` in the
  corpus rather than picking one.
- Next step: taxonomy, synthesis, adjacent, refs.bib, search-log, README.

### 2026-09-04 — supporting files; one late addition from OpenReview
- What I did: wrote `taxonomy.md`, `synthesis.md`, `adjacent.md`, `search-log.md`, `refs.bib` and
  `README.md`. Ran the OpenReview / ACL Anthology / Papers with Code / Google Scholar coverage the
  issue's search protocol asks for, and recorded honestly what each returned.
- Why: deliverables 4–9 of the issue, and the protocol requires more than arXiv.
- Result / what I found:
  * **OpenReview found a paper nothing else surfaced**: *Gödel Agent* (arXiv:2410.04444, ACL 2025
    main), added as a full Topic 1 entry. It is the missing link between ADAS and DGM. Worth noting
    *why* the arXiv search missed it: `ti:"Godel Agent"` returns nothing because the title uses
    "Gödel" with a diaeresis and the title index does not ASCII-fold. Found by searching a
    distinctive abstract phrase instead.
  * **Papers with Code's API returned empty bodies** for every query — dead end, recorded as L1.
  * **Google Scholar was not queried** (no API, scraping blocked and against terms). Semantic Scholar
    substituted; recorded as L3 rather than glossed.
  * Two-directional snowballing was implemented but Semantic Scholar's anonymous rate limit made it
    impractical at this scale; vocabulary-based arXiv search was used instead. Recorded as L4 with
    the specific risk it carries.
- A correctness bug I introduced and fixed: the BibTeX generator's string cleaner stripped
  backslashes wholesale, which silently turned `\$15` in the StateM title into `15`. Caught by the
  refs.bib validator flagging an unescaped `%` in the same title. Fixed the cleaner to protect
  escapes, drop math delimiters and re-escape BibTeX specials, then added `fetch.py resync` to
  regenerate the already-expanded inline BibTeX blocks. **This is exactly the failure mode the
  generated-BibTeX approach is meant to prevent, so it is worth recording that automation moved the
  error from "one wrong citation" to "one wrong function, caught by a checker".**
- `refs.bib`: 120 entries, 120 unique keys, validator clean. No LaTeX toolchain here, so
  "compiles clean" is a structural check — stated as a caveat in the README rather than claimed.
- Next step: verification pass, then PR.
