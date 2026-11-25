# Work Log — Issue #15: Evolve-harness on ARC-AGI-3 ft09 and vc33 (level 1): same architecture and setup as #14, 3 seeds × 5 rounds

**Issue:** https://github.com/Paier05/Final-Year-Project/issues/15
**Branch:** `experiment/15-evo-harness-ft09-vc33-tc1`
**Started:** 2026-11-25 14:36

## Understanding the issue

#14 ran the evolve loop (Analyze with frame evidence, Propose, Validate with
the skill-name check and the fact-check, Write, Gate, checkpoint/resume) on
ls20 Level 1. #15 asks whether that architecture carries over: run the same
loop, same settings, same v0, on two games it has never seen, **ft09** and
**vc33**, Level 1 only, 5 rounds each, 3 seeds per round, the two games in
parallel on TC1.

What has to be built because the games are new:

1. A goal-progress scorer per game (same contract as ls20's: deterministic,
   from game state, in [0, 1], clear = 1.0), with three tests.
2. Frame evidence that works when there is no moving block (click games):
   Part A reports clicks and their coordinates, Part C links rare changes to
   clicks. Three tests.
3. Everything that is ls20-specific in the loop has to stop being so for the
   new games, without leaking what I learn about ft09/vc33 into anything the
   player or the Meta LLM sees. Game knowledge lives only in
   `scorer/<game>/` (notes, scorer, tests).
4. A v0 audit, posted, and **no v0 change without the user's answer**.
5. Baseline B: #14's best ls20 harness (v4) on each game, seeds 1–3.
6. TC1: script A or B, a smoke check of both games at once, baseline B,
   part 1, then "continue" parts.

## Plan

1. Branch, this log.
2. Inspect both games; `scorer/<game>/GAME_NOTES.md`.
3. Scorers + tests.
4. Make the loop game-aware where it is ls20-specific (scorer, probe,
   Analyze, the Meta prompt's score paragraph, the fact-check's ground truth)
   while keeping ls20's behaviour byte-identical.
5. Frame evidence click mode + tests.
6. v0 audit: post, ask, wait.
7. `--game`, `config_evolve_15.yaml`, baseline-B stage, job scripts.
8. Leak test extended to both games' notes; full self-test; commit.
9. TC1: connect, `MyTCinfo`, upload, env, smoke (both games at once),
   baseline B, part 1. Post job ids, disconnect.

## Progress log

### 2026-11-25 14:36 — Preconditions, branch

- What I did: checked the remote, `gh auth status`, the working tree; read
  the issue (no comments yet), the workflow file, #14's work log and code.
- Result / what I found:
  - Untracked files unrelated to this issue (`.vscode/`, `experiments/`,
    `results/round*_ls20.log`, `results/run_info.json`, `runs/`). Left
    untouched (`runs/v3` is #14's run, copied back).
  - #14's PR is not open yet (still owed), so this branch is **stacked on
    `experiment/14-evo-harness-v3-ls20-tc1`** (04e607d), as #14 was on #12.
  - The model endpoint the user gave is the same URL and key as the local
    `.env`. At 14:33 **both models answer HTTP 500** (flash and the 27B
    fallback: "connection refused" behind the gateway). Not fixable here;
    re-check before the cluster steps.
  - Game files for ft09 and vc33 are in `environment_files/` (gitignored, as
    ls20's): the games run offline, as in #14.
- Discrepancy noted: the issue's table says #14 used "3 seeds"; #14 used 5
  (`config_evolve.yaml`: seeds 1–5). The issue says 3 seeds (1, 2, 3) for
  this run, consistently, in five places. I follow the issue: **3 seeds**.

## Open questions / risks

- Model availability (see 14:36).

## Summary (fill in at the end)
