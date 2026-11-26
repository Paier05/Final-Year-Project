# Work Log — Issue #16: Evolve-harness v4 on ft09 and vc33: 5 seeds, drop skills that don't change the game, block repeated rejected edits, show rejected versions to the Meta LLM

**Issue:** https://github.com/Paier05/Final-Year-Project/issues/16
**Branch:** `experiment/16-evo-harness-v4-ft09-vc33-tc1`
**Started:** 2026-11-26

## Understanding the issue

#15 ran #14's evolve loop on ft09 and vc33 (Level 1, 3 seeds, 5 rounds, the
two games in parallel on TC1). ft09 accepted no child: every round the Meta
LLM proposed the same block-clicking skill and prompt line again, sometimes
word for word, and the skill's clicks changed nothing. vc33 accepted v1 and
v4. #16 keeps #15's settings and changes five things:

1. 5 seeds per round (1–5); the unused-skill delete rule stays at 2 rounds
   (it counts evaluated episodes, so 10).
2. Validate drops an action-taking skill whose actions change nothing (in the
   frame or the game state, outside regions that change on every step) from
   any of up to 5 restored states of the parent's trajectories.
3. Validate drops an edit that repeats one rejected earlier in this game's run
   (`runs/<game>-v4/rejected_edits.jsonl`), before the other checks.
4. The Meta LLM's input gets a "Rejected since current parent" section: every
   Gate-rejected child of the current parent and every edit dropped at
   Validate since that parent became the parent.
5. The player gets a record of what each action changed on screen: the last
   20 actions in its context, a per-location click summary, and the full
   record as `action_log` in the sandbox. Fixed infrastructure, observations
   only, this episode only.

Run directories `runs/ft09-v4`, `runs/vc33-v4`; #15's are not touched.

## Plan

1. Branch, this log.
2. Shared frame-diff code: per-step change regions, an every-step detector,
   the per-action record (used by the action record, the state-change check
   and the frame evidence).
3. Change 5 (action record) in the action loop, `action_log` in the sandbox,
   gated by config so #14/#15 configs behave as before.
4. Change 2 (state-change check) and change 3 (repeat check + store) in
   Validate; change 4 in Analyze/Propose; change 1 in `config_evolve_16.yaml`.
5. Tests for each change (4 + 5 + 3 + 5), leak test extended; full self-test.
6. From #15's saved data: repeat rate, no-effect clicks.
7. v0 state-change audit per game: post, wait for the user's answer.
8. TC1: connect, `MyTCinfo`, upload, smoke check (both games), part 1.

## Progress log

### 2026-11-26 — Preconditions, branch

- What I did: checked the remote and `gh auth status` (Paier05, repo scope);
  read the issue (no comments), the workflow file, `WORK_LOG-15.md` and the
  loop code.
- Result / what I found:
  - Untracked files unrelated to this issue (`.vscode/`, `experiments/`,
    `results/round*_ls20.log`, `results/run_info.json`, `runs/`), as at the
    start of #15. Left untouched; `runs/ft09`, `runs/vc33` are #15's runs.
  - No PR is open for #14 or #15, so this branch is **stacked on
    `experiment/15-evo-harness-ft09-vc33-tc1`** (902e30d), as #15 was on #14.
  - **#15 is not finished**: vc33 paused before round 5 (v5 written, not
    played). Its part 2 needs the cluster code at #15's commit. So #16 is
    uploaded to a **separate remote directory** (`~/evo-harness-16`), and the
    new behaviour is switched on by #16's config only; #15's code, run
    directories and config on the cluster stay as they are.
  - v0's four skills (`bfs_to_target`, `grid_region`, `obstacle_map`,
    `player_detector`) take no actions: the v0 audit (step 3) will check none.
  - #15's saved frames: vc33's step bar (row 0) changes on every click, and a
    button click changes the columns in rows 1–63, one row below the bar.
    #15's frame evidence pools both into one "regular" region (noted in
    WORK_LOG-15). Using those regions to mask "changes every step" would hide
    a button click's effect, so the every-step detector for #16 is built on
    per-step changes (step 2 of the plan), not on #15's pooled regions.
  - ft09: a tile click changes the 6x6 tile and 2 cells of a bar in row 63;
    a miss changes nothing. The bar changes only on tile clicks, so it is not
    an every-step region.

## Open questions / risks

## Summary (fill in at the end)
