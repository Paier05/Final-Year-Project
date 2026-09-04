# Search log

An honest record of how the corpus was built: what was searched, what was found, what failed, and
what was not done. Written so a supervisor can audit the review's coverage rather than take it on
trust.

**Dates:** all searching and fetching done 2026-09-04.
**Tooling:** `literature/tools/fetch.py` (arXiv API, Semantic Scholar Graph API, page caching, BibTeX
generation). Every record retrieved is cached under `literature/refs/` and committed, so every claim
in the corpus can be re-checked without re-fetching.

---

## 1. Verification method, and why it is this one

Each entry is written from a **cached canonical record**, never from memory of a title. For arXiv
work that record is the arXiv API entry (title, full author list, dates, categories, DOI,
journal-ref, comment); for the non-archival sources it is the fetched page text.

Two consequences worth stating because they shape the corpus:

1. **BibTeX is generated from the same cached record the prose is written from**
   (`fetch.py bib` / `expand` / `resync`). Hand-typed BibTeX is where fabricated metadata usually
   enters a review; here the citation and the description cannot drift apart. `refs.bib` is validated
   by `tools/checkbib.py`.
2. **Venue is stated only where it is confirmed.** The arXiv `journal_ref` and `comment` fields carry
   venue information for many entries ("ICLR 2026 (Oral)", "NeurIPS 2025 Oral", "Accepted to COLM
   2026", "ICML 2025, PMLR 267", "ACL 2025 main"). Where neither field carries it and a Semantic
   Scholar lookup did not succeed, the entry says **"no venue on the record"** rather than guessing.
   This means some entries understate their publication status — a deliberate trade, since an
   invented venue is a citation error and an omitted one is not.

**Verification outcome: 120 sources cited, 120 verified.** No entry in the corpus carries
`Verified: no`.

---

## 2. Seed verification (issue §"Seed leads")

All nine arXiv IDs given in the issue resolved to real papers. Two naming problems were found and are
reported here as the issue requires:

| Seed as written in the issue | What the record actually says | Action |
|---|---|---|
| `"Teaching Models to Teach Themselves..." (SOAR) — arXiv:2601.18778` **and** `SOAR (self-improving evolutionary program synthesis) — arXiv:2507.14172` | Two unrelated papers by different groups that both use the name **SOAR**. 2601.18778 = Sundaram, Quan, Kwiatkowski, Ahuja, Ollivier, Kempe (ICML 2026), asymmetric self-play with bilevel meta-RL. 2507.14172 = Pourcel, Colas, Oudeyer (ICML 2025, PMLR 267), evolutionary program synthesis on ARC-AGI. | Disambiguated throughout as **[SOAR-Teacher]** and **[SOAR-ProgSynth]**, with a naming note in each entry. |
| `MetaEvolve — arXiv:2607.21971` | The paper's title is *Teaching LLMs to Self-Evolve: Cultivating Core Meta-Skills with Reinforcement Learning* (Wu, Qian, Chen, Ji). "MetaEvolve" is the framework's name **inside** the paper, not the title. | Handle kept as **[MetaEvolve]**; the entry states the real title and flags the mismatch. |

Other seed leads named without an ID were resolved by search and verified: Darwin Gödel Machine
(arXiv:2505.22954), ADAS (arXiv:2408.08435), Gödel machine (arXiv:cs/0309048), Voyager
(arXiv:2305.16291), Reflexion (arXiv:2303.11366), Self-Refine (arXiv:2303.17651), ExpeL
(arXiv:2308.10144), PromptBreeder (arXiv:2309.16797), EvoPrompt (arXiv:2309.08532), DSPy
(arXiv:2310.03714), PAIRED (arXiv:2012.02096), POET (arXiv:1901.01753) and Enhanced POET
(arXiv:2003.08536), asymmetric self-play (arXiv:1703.05407), TSCL (arXiv:1707.00183), AlphaZero
(arXiv:1712.01815), STaR (arXiv:2203.14465), Tree of Thoughts (arXiv:2305.10601), self-consistency
(arXiv:2203.11171), Algorithm Distillation (arXiv:2210.14215), AdA (arXiv:2301.07608), s1
(arXiv:2501.19393), TRM (arXiv:2510.04871) and its follow-up (arXiv:2512.11847), CompressARC
(arXiv:2512.06104), and the ARC Prize 2025 technical report (arXiv:2601.10904).

**The Lilian Weng blog seed resolved.** `lilianweng.github.io/posts/2026-07-04-harness/` exists, is
dated 4 July 2026, and is cached at `refs/web/weng-harness.txt` (~47k characters). Cited as
`[non-archival]`.

**One seed correction worth noting:** the internal briefing and several citations refer to
arXiv:2411.07279 as "test-time training for abstract reasoning". The record's actual title is *The
Surprising Effectiveness of Test-Time Training for **Few-Shot Learning***. Corrected in the entry.

---

## 3. Databases searched

| Source | How | Outcome |
|---|---|---|
| **arXiv** | `export.arxiv.org` API: 20+ keyword queries plus batched `id_list` lookups | Primary source. 117 records cached. |
| **Semantic Scholar** | Graph API: `paper/arXiv:<id>` for venue and citation counts | **Partially successful.** Anonymous access is heavily rate-limited; roughly half the lookups returned HTTP errors even with a 10s throttle and 4 retries. Confirmed venues for ADAS (ICLR, 303 citations), AFlow (ICLR, 351), Promptbreeder (ICML, 589), Agentless (arXiv.org, 479). Cached under `refs/s2/`. |
| **OpenReview** | `api2.openreview.net/notes/search` for each topic | **Found one paper nothing else surfaced:** the review threads for *Gödel Agent* (arXiv:2410.04444, ACL 2025), now a full Topic 1 entry and the missing link between ADAS and DGM. Other queries returned papers already in the corpus (TRACED, VocabDropout), which is useful corroboration of coverage. |
| **ACL Anthology** | `aclanthology.org/search/` reachable (HTTP 200); ACL-published work reached via arXiv records carrying ACL venue strings | Yielded Self-Instruct (ACL 2023), Gödel Agent (ACL 2025 main). See limitation L2 below. |
| **ARC Prize blog / docs** | Pages fetched and cached: `arcprize.org/arc-agi/3`, `arcprize.org/competitions/2026/arc-agi-3`, `arcprize.org/blog/arc-agi-3-preview-30-day-learnings` | Source for the competition constraints used in `synthesis.md` §4 (no internet at evaluation, mandatory open-sourcing, $850K/$700K prize structure, June 30 / September 30 2026 milestones) and for the four evaluated capabilities (exploration, modelling, goal-setting, planning). Cached under `refs/web/`. |
| **Papers with Code** | `paperswithcode.com/api/v1/papers/` | **Dead end** — the API returned an empty body for every query. Recorded as a coverage limitation (L1). |
| **Google Scholar** | Not queried | **Not done** — no API, and scraping is blocked and against its terms. Semantic Scholar was used as the substitute citation-graph source. Recorded as limitation L3. |

---

## 4. Queries run

Verbatim arXiv query strings, grouped by topic. Queries that produced nothing new are kept.

**Topic 1 — harness / self-modifying scaffolds**
```
all:"agent harness"
all:"self-improving agent" AND all:"scaffold"
all:"self-modifying" AND all:"LLM agent"
all:"automated design of agentic systems"
all:"prompt optimization" AND all:"evolutionary"
all:"tool creation" AND all:"agent"
all:"experience" AND all:"memory" AND ti:"agent" AND all:"reuse"
all:"self-evolving" AND all:"agent"
ti:"context engineering"
all:"frozen" AND all:"weights" AND all:"agent" AND all:"improve"
ti:"Godel Agent"                                     -> no results (see note)
all:"self-referential agent framework" AND all:"recursive self-improvement"
```

**Topic 2 — teacher–student / proposer–solver**
```
all:"unsupervised environment design"
all:"learnability" AND all:"curriculum" AND all:"reinforcement learning"
all:"asymmetric self-play"
all:"proposer" AND all:"solver" AND all:"self-play" AND all:"LLM"
all:"open-ended" AND all:"environment generation" AND all:"agent"
all:"reward hacking" AND all:"self-play" AND all:"verifier"
```

**Topic 3 — capability without parameter updates**
```
all:"test-time compute" AND all:"scaling"
all:"in-context reinforcement learning"
all:"elicitation" AND all:"reasoning" AND all:"base model"
all:"test-time training" AND all:"abstract reasoning"
all:"adaptive memory" AND all:"test-time"
all:"imperfect verifiers" AND all:"inference scaling"    -> no results
all:"data contamination" AND all:"reasoning benchmark"   -> nothing on-topic
all:"multiagent debate" AND all:"language models"
ti:"self-consistency" AND all:"chain of thought"
all:"ARC-AGI-3"
```

**OpenReview**
```
self-improving agent scaffold        (surfaced Godel Agent via its review thread)
unsupervised environment design learnability
test-time scaling frozen model capability
proposer solver curriculum LLM self-play
```

Note on `ti:"Godel Agent"`: the arXiv title uses "Gödel" with a diaeresis, and the API's title index
did not match the ASCII spelling. Found instead by searching distinctive abstract phrasing. **Lesson
worth recording: ASCII-folding is not reliable in the arXiv title index; search abstract phrases when
a known title fails to resolve.**

---

## 5. Snowballing

The issue asks for both directions (works cited by, and works citing) for each seed. This was done
**unevenly**, and the reason is mechanical:

- **Backward (references) and forward (citations) via Semantic Scholar** were implemented
  (`fetch.py refs` / `cites`) but the anonymous Graph API rate-limited hard enough that systematic
  two-directional snowballing over all seeds was not completed within this session.
- **What was used instead:** arXiv keyword search on the vocabulary each seed introduced, which is a
  reasonable proxy for forward citation in a fast-moving 2026 literature where most citing work is
  itself on arXiv. It worked well — the 2026 papers that most changed this review's conclusions
  ([Twin], [Tycho], [WMAblation], [WorkspaceOpt], [BenchmarkValidity], [R-Diverse], [VocabDropout])
  were all found this way, and each of them cites the seeds.
- **What this risks missing:** older work that cites the classical seeds but does not share their
  2026 vocabulary, and non-arXiv citing work.

This is recorded as limitation L4 rather than papered over.

---

## 6. Dead ends and things deliberately not included

- **Papers with Code API** returned empty bodies for every query. Not pursued further.
- **`all:"imperfect verifiers" AND all:"inference scaling"`** returned nothing; the paper that
  actually covers this ([LimitsResampling], arXiv:2411.17501) was found by its real title, *The
  Limits of Inference Scaling Through Resampling* — note it is **not** titled "Inference Scaling
  fLaws", as it is sometimes cited.
- **`all:"data contamination" AND all:"reasoning benchmark"`** returned only domain-specific
  benchmarks (medical, chemistry, Korean-language). The contamination material that was useful came
  from [GSM-Symbolic], [ARCPrize2025] and [BenchmarkValidity] instead.
- **UED for interactive, goal-unknown environments.** Searched specifically for this and it does not
  exist: every UED paper found parameterises an environment whose reward function is known. **This
  absence is a finding, not a search failure**, and it is E2 in `taxonomy.md`.
- **Static distillation and one-shot synthetic data** (Self-Instruct, WizardLM/Evol-Instruct) were
  found repeatedly by the Topic 2 queries and moved to `adjacent.md`: the issue excludes teachers
  that do not adapt to the student.
- **AI-safety / RSI-risk material** (e.g. arXiv:2509.26354, arXiv:2606.23075, arXiv:2602.15654) was
  surfaced by the "self-evolving agent" queries and left out per the issue's out-of-scope list; the
  one with a directly overlapping failure taxonomy is listed in `adjacent.md`.

---

## 7. Known limitations of this search

- **L1 — Papers with Code not covered.** Its API returned nothing. Given that everything in this
  corpus is either on arXiv or indexed by Semantic Scholar, the expected loss is small, but it is a
  gap against the issue's stated protocol.
- **L2 — ACL Anthology not searched systematically.** ACL-venue work entered the corpus through arXiv
  records carrying ACL venue strings rather than through an Anthology-side search. NLP-only work with
  no arXiv preprint could be missed.
- **L3 — Google Scholar not queried.** No API; scraping is blocked and against its terms. Semantic
  Scholar substituted.
- **L4 — Snowballing incomplete** (see §5): forward/backward citation traversal was rate-limited and
  replaced by vocabulary-based arXiv search for most seeds.
- **L5 — Venue data is under-reported, not wrong.** See §1.2. Entries reading "no venue on the record"
  may well be published; the record simply did not say so and Semantic Scholar did not answer.
- **L6 — Numbers are taken from abstracts and records, not from full texts.** Where an abstract
  reports no headline figure, the entry says so explicitly rather than supplying one from elsewhere
  ("The abstract gives no single headline number, so none is quoted"). Every quantitative claim in
  the corpus can be traced to the cached record it came from. Before any of these numbers goes into
  the dissertation, the specific figures being leaned on should be confirmed against the full PDFs —
  particularly the ARC-AGI-3 scores in `synthesis.md` §4.
- **L7 — One benchmark discrepancy is unresolved.** The internal briefing says 135 environments at
  roughly 1:5 public:private; [BenchmarkValidity] refers to 25 public games and a 55-game private
  evaluation; [Twin] and [Tycho] report 183 levels across the 25 public games. Marked `[unverified]`
  in `synthesis.md` §4 and flagged for confirmation against `docs.arcprize.org`.

---

## 8. Open leads for whoever picks this up next

1. **Run the two-directional snowball properly** with a Semantic Scholar API key (removes the rate
   limit that caused L4), starting from [Twin], [Tycho], [SOAR-Teacher] and [DarwinX].
2. **Search specifically for the gap-refuting system** described in `synthesis.md` §5: a loop that
   co-evolves scaffold *and* task distribution for a frozen learner under an efficiency metric. If it
   exists, the gap statement needs rewriting. Suggested queries:
   `all:"co-evolve" AND all:"harness" AND all:"curriculum"`,
   `all:"self-generated environments" AND all:"frozen model"`,
   `all:"curriculum" AND all:"scaffold" AND all:"without fine-tuning"`.
3. **Check `docs.arcprize.org` and the ARC-AGI-3 leaderboard** for the current public/private split
   and the current private-set state of the art — the interactive results in this corpus moved by
   two orders of magnitude in five months, so anything here dated before September 2026 should be
   re-checked before submission.
4. **Look for ARC-AGI-3 private-set results.** Every interactive result in this corpus is public-set
   only, except [BenchmarkValidity]'s linked competition entry (RHAE 0.30 on 55 private games). The
   Milestone #2 deadline of 30 September 2026 requires open-sourcing, so more private-set evidence
   should appear shortly after that date.
