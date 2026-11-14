# Work Log — Issue #14: Evolve-harness v3 on ls20 level 1: reject missing skill names in Validate, sprite-change evidence in Analyze — rerun 5 rounds

**Issue:** https://github.com/Paier05/Final-Year-Project/issues/14
**Branch:** `experiment/14-evo-harness-v3-ls20-tc1`
**Started:** 2026-11-15 01:22

## Understanding the issue

#12 ran the evolve loop for 5 rounds (plus 2 extra) on ls20 Level 1 and never
got past "walk to the goal, get blocked, never rotate". #14 says: no more
rounds until four gaps are fixed, then rerun the same 5 rounds on the school
GPU cluster (TC1).

1. **Skill-name check in Validate.** Harness text can name skills that don't
   exist (v6/v7 of #12 told the player to call `find_goal()`, which Validate
   had dropped: 79 cells called it, 37 NameErrors). Validate must reject any
   edit that leaves such a name in the candidate harness. Deterministic.
2. **Frame evidence in Analyze.** The Meta LLM gets nothing about where the
   player went or what else changed on screen. Analyze gains a section built
   from frames only: (A) player movement, (B) other on-screen changes, split
   into regular and rare, (C) the link between rare changes and the player's
   position. Observations only, no hard-coded locations.
3. **Rotation part of the score.** Must compare the held pattern rotation with
   the goal's (the win check's two values), by cyclic distance. Check what
   #12's scorer did; fix and rescore #12 if it differs.
4. **Checkpoint and resume.** TC1 jobs are capped at 6 h. The run must stop
   cleanly, save after every episode and stage, and continue in a later job
   without losing or repeating work. No automatic resubmit: the user says
   "continue" after each part.

Ground-truth facts (where the switch and the icon are, the rotation values)
may be used only in the scorer, the fact-check and the tests. An automated
leak test guards that.

Then: smoke job on TC1, the 5-round run in 6-hour parts with a progress
comment after each, and a final report with pictures.

## Plan

1. Preconditions, branch, this log.
2. Fix 1: `evolve/skill_names.py` + a stage in `evolve/validate.py`; audit v0
   and #12's best version; 3 tests.
3. Fix 2: `evolve/frame_evidence.py` + section in `evolve/analyze.py`, passed
   to the Meta LLM; per-step table next to the trajectories; 4 tests.
4. Fix 3: check `evolve/goal_score.py`'s rotation part against the win check;
   cyclic distance; rescore #12 if anything changes.
5. Fix 4: `evolve/checkpoint.py` (state file, lock, time guard, SIGUSR1) wired
   into `evolve/loop.py` and `evolve_run.py` (`--run-dir`, `--resume`);
   3 tests.
6. Leak test; trajectory frame-per-step check; full self-test; commit.
7. TC1: connect, `MyTCinfo`, upload, conda env, smoke job.
8. Part 1; post the job id; disconnect. Then wait for "continue".
9. After round 5: copy back, final report with pictures, clean up, PR.

## Progress log

### 2026-11-15 01:22 — Preconditions, branch

- What I did: checked the remote, `gh auth status`, the working tree; read
  the issue, the workflow file and #12's code and work log.
- Result / what I found:
  - Untracked files unrelated to this issue (`.vscode/`, `experiments/`,
    `results/round*_ls20.log`, `results/run_info.json`). Left untouched.
  - PR #13 (#12's branch) is still open, so this branch is **stacked on
    `experiment/12-evo-harness-v2-ls20`** (c32e680), as #12 was on #9. The PR
    will target that branch so its diff is only #14's changes.
  - No `ARC_API_KEY` was supplied. As in #9 and #12 the game runs from the
    local `environment_files/` (gitignored), so those files go to the cluster
    with the repo and the preflight checks that the game loads and steps on
    the compute node.
- Next step: fix 1.

## Open questions / risks

- (to be filled as the work goes)

## Summary (fill in at the end)
