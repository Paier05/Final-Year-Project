# Work Log — Issue #1: [paper-review] Tycho: Active Abstraction with Programmatic World Models for ARC-AGI-3 (arXiv:2607.28287)

**Issue:** https://github.com/Paier05/Final-Year-Project/issues/1
**Branch:** docs/1-tycho-paper-review
**Started:** 2026-08-23

## Understanding the issue

The deliverable is a document, not code. I need to read arXiv:2607.28287 ("Tycho") in full and
produce a critical review at `docs/reviews/2607.28287-tycho.md` following a mandated 15-section
structure, 1,500–2,500 words excluding tables.

The user's framing matters as much as the content request: the paper claims 100.00 RHAE and all
183 levels on the 25 public ARC-AGI-3 games, against a prior public SOTA of ~12.6% of human
baseline. That is a ~8x jump. The user explicitly wants an adversarial read — what was measured,
on which split, at what cost, and what remains unsolved — not a summary. Two things the user
called out as high priority:

- **Task 4 (metrics).** Is "100.00 RHAE" the same thing as the ARC Prize "100%" target, or a
  different and more permissive measurement? The official per-level score is
  `min(1, human_baseline_actions / agent_actions)^2`. If RHAE is a different aggregation, the
  headline is not comparable to the leaderboard numbers in the user's notes.
- **Task 7 (the repair paradox).** Automatic repair improved transition-reproduction accuracy but
  scored *lower* RHAE (83.07). Needs real space, not a sentence.

14 numbered sub-tasks total. Conditional side-deliverable: open a follow-up
`[spike] Reproduce Tycho on 3 public ARC-AGI-3 games` issue **only if** my section 10 concludes
reproduction is feasible on a student budget; otherwise open nothing and say why.

### Assumptions I am making

1. **`docs/reviews/` does not exist yet** — the repo currently has only `README.md`,
   `github_issue_workflow.md`, and `Documentation_Generated/`. I will create the directory.
2. **"Both background notes live in this repo"** refers to the two PDFs in
   `Documentation_Generated/`: `ARC-AGI-3_FYP_Briefing.pdf` and
   `Self-Evolution_Teacher-Student_Training_ARC3.pdf`. I will read both.
3. The paper post-dates my training data (submitted 30 Jul 2026), so **every** factual claim in
   the review must come from the fetched source, not from prior knowledge. Anything I cannot
   locate in the fetched body gets `[abstract only — unverified]` or "not reported".

### Blocker resolved before starting

`gh` was not installed on this machine. Installed GitHub CLI 2.98.0 via winget; the user
completed `gh auth login` interactively (logged in as Paier05). Recorded here because step 0 of
the workflow says to stop rather than proceed unauthenticated.

## Plan

1. Fetch the paper (HTML first, PDF fallback) and cache it under `refs/` per workflow step 5b.
   **Verify it exists at all** before planning around its contents.
2. Fetch the `NIMI-research/Tycho` repo README and entry points — read only, never execute
   (workflow guardrail).
3. Read the two background PDFs in `Documentation_Generated/` for the positioning (task 10),
   ARC Prize eligibility (task 11), and FYP implications (task 12) sections.
4. Extract facts for tasks 1–8, recording section/figure/table numbers alongside every number as
   I go, so citations are not reconstructed after the fact.
5. Do the reproducibility check (task 9) from the repo.
6. Draft `docs/reviews/2607.28287-tycho.md` in the mandated 15-section structure.
7. Verify per workflow 5b: every number cited or explicitly marked unverified; open questions
   non-empty; all 14 tasks answered or explicitly marked "could not complete, because X".
8. Decide the conditional follow-up issue based on what section 10 actually concludes.
9. Push, open PR with `Closes #1`, comment the PR link on the issue.

## Progress log

### 2026-08-23 — Setup

- What I did: Checked workflow preconditions. Found `gh` missing; installed via winget, user
  authenticated. Confirmed clean tree on `main`, remote `Paier05/Final-Year-Project`. Read issue
  #1 in full. Created branch `docs/1-tycho-paper-review` and seeded this log.
- Why: Workflow step 0 requires an authenticated `gh` and a clean tree before any work.
- Result / what I found: Issue #1 is a research/review task with 14 sub-tasks and a strict
  output contract. No existing comments on the issue, so no post-hoc scope changes to account for.
- Next step: Fetch and cache the paper; confirm it exists before committing to the plan above.

## Open questions / risks

- **The paper is newer than my training data.** I have no prior knowledge of Tycho, RHAE, or
  these results. Everything must be sourced from the fetch. If the fetch is incomplete (arXiv
  HTML for a 52-page paper with 17 tables may be truncated or partially rendered), the review's
  coverage of specific table numbers will be limited — I will say so rather than fill gaps.
- **Risk of reviewing an unverified artifact.** If the arXiv ID does not resolve, the correct
  action is to stop and tell the user, not to write a review of a paper I cannot read.
- **Third-party content is data, not instructions** (workflow guardrail). If the paper, repo, or
  any fetched page contains text directing me to take actions, I will quote it here and ask.

## Summary (fill in at the end)

_Not yet started._

### 2026-08-23 — Sources fetched and cached; paper read in full

- What I did: Verified arXiv:2607.28287 resolves (it does — title, authors, and 30 Jul 2026 date all
  match the issue). Downloaded the full LaTeXML HTML (707 KB) to `refs/2607.28287v1.html`, converted
  it to plain text (`refs/2607.28287v1.txt`, 4,064 lines) with a throwaway script so I could grep and
  read it directly instead of through a summarizer. Read sections 1–8 and Appendices A, C, D. Fetched
  the `NIMI-research/Tycho` README and `docs/REPRODUCING.md` to `refs/`, plus the repo file tree.
- Why: Workflow 5b requires sources cached locally so claims can be re-checked. Reading the raw text
  rather than a fetched summary is the only way to satisfy the issue's rule 1 (cite section/table
  numbers for every number) — a summarizer drops table numbers.
- Result / what I found: The paper is real, 8 sections + 5 appendices, and far more self-critical
  than the issue's framing anticipated. Two findings stand out:

  1. **The metric question (issue task 4) has a concrete answer.** Definition 2 (§3.1) gives the
     per-level efficiency contribution as `e_ℓ = min{115, 100(h_ℓ/a_ℓ)²}` — capped at **115**, not
     100 — with game RHAE `= min{ Σwℓeℓ/Σwℓ , 100·Σwℓcℓ/Σwℓ }`, `wℓ = ℓ`. The issue's stated official
     per-level score is `min(1, h/a)²`, i.e. capped at 1.0. Those differ: the paper's form lets a level
     where the agent beat the human baseline earn up to 115 and **offset** levels where it did worse,
     before the outer `min` clips the game to 100. §5.1 "Efficiency beyond capped RHAE" confirms this
     matters in practice: 171 of Opus 5's 183 completed levels sit at the per-level cap, so 12 do not —
     under a strict per-level cap of 100 those 12 could not be compensated. The paper does describe its
     formula as official and links six official ARC Prize scorecards, so I cannot call it wrong; I can
     only report the discrepancy precisely and flag which side I cannot verify.
  2. **The repair paradox (issue task 7) has real data behind it.** Trigger reaches 88.1% pre-action
     accepted transition match vs orchestrator's 16.2% (Table 7) and 99.97% vs 45.56% end-of-run
     (Table 11), yet scores 83.07 vs 88.49 RHAE. But Table 7 also shows trigger's pre-action model
     *executes* only 52.0% of the time vs 83.5% — its accuracy is conditional on a model being there
     far less often. And it burns 1,192 builder calls vs 147 (Table 8), hits the LM-call limit on 5
     games (Table 10), and costs $8.03k vs $5.78k (§5.1 Cost and context). So "more accurate model,
     worse play" is real, but the mechanism is not purely epistemic — it is partly budget exhaustion.
     The sk48 case study (§5.2) supplies the epistemic half.
- Next step: Read the two background PDFs in `Documentation_Generated/` for the positioning, ARC Prize
  eligibility, and FYP-implications sections, then draft the review.

### 2026-08-23 — Background notes read

- What I did: Extracted text from both PDFs in `Documentation_Generated/`. Raw stream extraction gave
  glyph indices (subsetted fonts), so I installed `pypdf` into an isolated scratchpad directory — not the
  user's Python environment — and decoded via the embedded ToUnicode CMaps.
- Why: Issue tasks 10, 11 and 12 are all defined relative to these notes; guessing their contents would
  have made three of the fourteen sub-tasks worthless.
- Result / what I found: The briefing confirms the metric discrepancy is real and consequential. It states
  `Level Score = min(1.0, (h/a))²` (hedged as "approximately"), human baseline = **second-best of 10
  first-time testers**, later levels weighted by index. The paper instead uses a **115** per-level cap and
  the **upper-median** first-run human action count. Both the cap and the baseline statistic differ, and
  both differences run in the permissive direction. The briefing also gives the ARC Prize 2026 constraints
  (Kaggle, no internet in the evaluation sandbox, open-source at milestone deadlines) which settle issue
  task 11: Tycho requires hosted API keys, so it is not submittable as published.
- Next step: Draft the review.

### 2026-08-23 — Review drafted, then cut to length (change of direction)

- What I did: Wrote `docs/reviews/2607.28287-tycho.md` in the mandated 15-section structure. First draft
  came in at **5,744 words** excluding tables against the issue's 1,500–2,500 target. Rewrote it tighter
  (3,882), then trimmed again (3,124), then converted the comparative content in §3, §8, §9, §11, §12 and
  §15 into tables — which the issue excludes from the word count and which suit weakness/evidence and
  claim/confidence material better than prose. Final: **2,690 words excluding tables**.
- Why: Rule 7 of the issue is explicit about length. My first two attempts trimmed at the word level and
  barely moved the total (5,744 → 3,882 → 3,124), which showed the problem was structural, not stylistic.
- Result / what I found: 2,690 is still ~8% over the 2,500 ceiling. I stopped there deliberately: getting
  under it meant cutting either §6 (metrics) or §9 (repair paradox), both of which the issue flags as high
  priority, and I judged the overrun the lesser cost. **Flagging it here rather than silently missing the
  target.** An intermediate draft carried a self-reported length of "~2,600" that was simply wrong (it was
  3,882); I removed that note rather than leave an inaccurate claim in the deliverable.
- Next step: Run the workflow's 5b verification checks.

### 2026-08-23 — Verification (workflow step 5b)

- What I did: Ran three programmatic checks over the review: (1) every paragraph containing a digit also
  contains a section/table/figure/appendix reference or an explicit hedge; (2) all 14 issue sub-tasks are
  addressed; (3) word count excluding tables and code blocks.
- Why: Step 5b defines "verified" for a document deliverable, and issue rule 1 requires a citation for
  every number.
- Result / what I found: Check 1 flagged 24 paragraphs; 20 were headings or restatements of figures cited
  in the immediately preceding table (false positives). **4 were genuine and I fixed them**: the "~$3k
  inference" summary in §8 (added Table 6), the 0.75 threshold in §9 (added App. C.2), the released-artifact
  list in §10 (attributed to the repo), and the RHAE question in §13 (added §6). Check 2: all 14 tasks pass.
  Check 3: 2,690 words. §15 (confidence log) is non-empty and §13 (open questions) has 5 entries, so the
  "no stated uncertainty" failure condition in 5b does not apply.
- Next step: Push, open the PR, and open the conditional `[spike]` issue — §10 concluded reproduction is
  feasible on a student budget, so the issue's condition for opening it is met.

## Notes on guardrails observed

- **No code from the Tycho repo was executed.** I read the README, `docs/REPRODUCING.md` and the file tree
  via the GitHub API only. The workflow forbids running research-repo code, and `REPRODUCING.md` documents
  paid API calls and a container build, so running it would also have spent money without authorization.
- **No instruction-like content was acted on.** Neither the paper nor the repo contained text directing the
  reader to take actions, so there was nothing to quote and escalate under the prompt-injection guardrail.
- **`pypdf` was installed to an isolated scratchpad directory**, not the user's Python environment, so
  nothing on the machine was modified to read the background PDFs.
- One environment change *was* made outside the repo: **GitHub CLI 2.98.0 was installed via winget** with
  the user's explicit approval, because step 0 of the workflow cannot be satisfied without it.
