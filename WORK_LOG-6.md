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

## Open questions / risks

- **R1.** Several seed arXiv IDs are 2026 IDs originating from LLM-written briefing notes. Any that
  fail to resolve must be treated as suspect and reported, not silently replaced.
- **R2.** Topic 3 is the topic the FYP hinges on, and it is also the one where "capability vs
  elicitation" is contested. Risk of overstating consensus — the disagreement section has to be real.
- **R3.** Coverage vs depth: the issue asks for up to ~60 full-template entries. If depth per entry
  has to be traded against count, the log must say so rather than quietly shipping thin entries.

## Summary (fill in at the end)
_To be completed._
