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

### 2026-11-26 — Changes 1–5 implemented and tested (step 1)

- **Shared frame-diff code** (`evolve/frame_diff.py`): change regions
  (REGION_GAP clusters), the moved-patch test, the every-step detector, the
  action record and its rendering. `frame_evidence.py` now imports the region
  and moved-patch code from it; its output is **byte-identical** to before on
  #15's vc33 rounds 1 and 4, ft09 round 0 and #14's ls20 round 4.
- **Every-step detector, first attempt failed on real data**: pooling each
  step's smallest cluster made vc33's every-step region grow to rows 0–27 in
  a v4 episode: when the bar's next cell sat right above the column a button
  moves, the two formed one cluster, which got pooled. Fixed: (1) once a
  step's every-step cells are known, only those are pooled; (2) a region grows
  by REGION_GAP only along its long side. Now **every vc33 episode of #15
  (15) gives exactly row 0, and ft09 (18) gives none**, matching the frames.
  A region counts as every-step after ≥ 3 actions, when it changed on ≥ 90 %
  of them, on ≥ 2 different actions.
- **Change 5 (action record)**: per action, `step`, `action`, click `x`, `y`
  and `value_at_click`, `changed`, `n_changed`, `regions` (rows, cols, cells,
  top 3 value changes), `every_step_cells`, `block_before/after` for a
  non-click move, `game_over`/`level_restarted`. Turn message: an ACTION
  RECORD block after RECENT ACTIONS: the every-step regions once, the last 20
  actions (`step 12 · click (31, 8) on 3 · 4 cells changed · rows 30–32,
  cols 7–9 · 3→5`), then clicks per location (top 40, the rest summed) and
  other actions. Sandbox: `action_log`, a read-only sequence (copies on
  access, no append; re-bound before every cell), in RESERVED_NAMES (so a
  skill cannot take the name and the skill-name check knows it). The API text
  gets an `action_log` line (player and Meta). Each action's record is in the
  trajectory; each turn logs `action_record_chars` (for the token-cost
  report). Replays and restored states rebuild the same record.
  Records are fixed when made (each uses what was known before it), so the
  first 2–3 vc33 clicks show the bar as a change. Rebuilding old lines with
  later knowledge was the alternative; fixed records keep `action_log` and
  the trajectory identical to what the player saw.
- **Change 2 (state-change check)**, `evolve/state_change.py`, last in
  Validate. Which skills: add/edit/merge of a skill that calls `action()`
  itself or through another skill (static, transitive). States: up to 5,
  round-robin over seeds, turns where the skill / its helper / a merged
  skill was called first, then evenly spread turns; each restored by
  replaying the seed's logged actions (`api_at_state` now takes the seed),
  checked against the logged `frame_hash_before`. Call: no arguments if none
  are required, else the edit's test snippet, else literal arguments copied
  from a recorded call, else unverifiable. Change = frame cells outside the
  every-step regions (from the parent's episodes, and along the restored
  prefix) or game-state fields other than those that changed on ≥ 90 % of
  the parent's actions (vc33: `steps_left`). The verdict is compared net
  (before vs after the whole call), as the issue says.
- **Change 3 (repeat check)**, `evolve/rejected.py`. Types: promote
  (rule add with replay_strip), merge, delete, edit (any other add/edit).
  Targets: `skill` for all skill code (the function's name is among the
  "names ignored", so one target), `prompt:<key>`, `step` (indices shift).
  Code identity: docstring, comments, layout and every name the function
  binds (its name, parameters, locals) replaced by position; free names
  (API, other skills) kept. Text: difflib ratio ≥ 0.9 after lowercasing and
  collapsing whitespace. Delete/merge: same name set (a step delete compares
  the deleted step's text). The store is synced from each round's
  attempts/validation file and the archive before every Validate and after
  every Gate (idempotent by id), so a job cut between two writes loses
  nothing. Repeat drops are stored too (`repeat_of` set).
- **Change 4**: built at Analyze, stored in `analysis.json`
  (`rejected_since_parent`: data + text), rendered after the frame evidence:
  Gate-rejected children of the current parent with their edits as diffs
  (30 lines each), per-seed scores and cost next to the parent's, gate
  reason; then every Validate drop in those rounds with its check (tests,
  replay, merge-eq, fact-check, skill-name, state-change, repeat) and a short
  reason, a fact-check drop with its label only. Over 9000 chars, the oldest
  diffs are cut to 6 lines, then left out; summary lines always stay.
- **Change 1**: `config_evolve_16.yaml` = #15's config with seeds 1–5 (5 in
  parallel), `action_record`, `validate.state_change`, `validate.repeat_check`,
  `rules.reject_similarity: 0.9`, `meta.rejected_section`, token cap 60 M.
  `delete_min_episodes` stays 10: it counts episodes, so 2 rounds × 5.
- **Old configs unchanged**: every #16 part is off without its config key.
  The Meta LLM input and the player's system prompt built from #14's
  (ls20 round 4) and #15's (vc33 round 2, ft09 round 3) saved reports are
  **byte-identical** before and after these changes.
- Meta prompt (only with the #16 keys): one line on the player's ACTION
  RECORD, a STATE CHANGE and a REPEATS paragraph under VALIDATION.
- Tests (`scorer/tests16.py`, run by `python -m evolve.selftest`): 61 new
  checks, among them the issue's 4 + 5 + 3 + 5, the leak test extended (every
  "Rejected since current parent" section and full Meta input of a scripted
  3-round run per game, the player's turn messages and logged records; the
  record holds only frame-observation keys; no interpretive words in the
  record's text). **Full suite: 285 checks pass locally** (the SIGUSR1 ones
  run on Linux only).
- Stub run (vc33, 2 rounds, 5 seeds): round 2 dropped all 7 repeated edits
  with the ids they repeat; the delete rule fired at exactly 10 episodes.

### 2026-11-26 — #15's saved data (step 2) and the v0 audit (step 3)

`python -m analysis.issue16_from15` → `results/issue16/from15.json`.

- **Repeat check over #15** (store grown with #15's own outcomes, in order):
  - ft09: **5 of 12** proposed edits (42 %) would have been dropped: the
    system-prompt rewrite in rounds 2, 3, 4, 5 (similarity 0.93–0.97 to a
    Gate-rejected one) and round 5's rule delete of `bfs_to_target` (1.0).
    The block-clicking skills were **not** repeats: the code differed each
    round. Those are the state-change check's case.
  - vc33: **1 of 9** (11 %): round 3's `count_orange` (identical code to
    round 2's).
- **No-effect clicks** (the action record's diff, every-step regions found
  in a first pass and known from the first click in a second):
  - ft09: 3599 clicks in 18 episodes, **3431 changed nothing (95 %)**, 2766
    of them at a location already clicked with no effect. Rounds 4–5: 600 of
    600 no effect.
  - vc33: 2616 clicks in 15 episodes, **2002 changed nothing (77 %)**, 1476
    repeated. It falls as the harness improved: 581/599 (v0) → 315/600 (v4).
- **v0 state-change audit**: none of v0's four skills (`bfs_to_target`,
  `grid_region`, `obstacle_map`, `player_detector`) takes actions, for
  either game, so the check has nothing to run on. Proposed: v0 unchanged.

### 2026-11-26 — Model and local smoke check

- Your endpoint URL and key are the same as the local `.env`. Preflight:
  **`qwen38-flash-next-autoround` HTTP 500, `Qwen/Qwen3.8-27B-FP8` OK**, as
  in #15. The config's fallback rule puts both roles on 27B, the model #14
  and #15 ran on.
- Local smoke (vc33): every check passed except "checkpoint written": all 5
  three-turn episodes finished within their last turn before the stop
  landed, so no seed was cut and the replay path was not exercised. Fixed by
  holding back seeds 2–5's first model call 30 s (they start together; their
  trajectories exist at once). Local smoke (ft09) then **passed**: seed 1
  finished, 2–5 cut and replayed on resume, ACTION RECORD in all 18 turn
  messages, 55/55 actions with a logged record, `action_log` works, the
  state-change check ran on 5 saved states (seeds 1–5) and the repeat check
  matched a re-cased line.

### 2026-11-26 13:27 — v0 audit answered; TC1 set up; smoke check submitted

- Posted steps 1–3 on the issue (comment 7182557377). **The user answered
  in chat: keep v0 as it is**, go on to the cluster (recorded on the issue).
- Credentials: the user gave the cluster login and the model URL/key in
  chat. They go to `cluster/tc1.py` as environment variables per call and
  are stored nowhere on this machine or in the repo.
- `MyTCinfo`: QoS `normal`, MaxTRESPU cpu=20, gpu=1, mem=64G, **MaxSubmit
  2**, MaxWall 6 h, partition `UGGPU-TC1`. No jobs of mine queued.
- Upload: commit `4a74ae3` + `environment_files/{ls20,ft09,vc33}` to
  **`~/evo-harness-16`** (`TC1_REMOTE_DIR`); `~/evo-harness` (#15, 79 MB)
  untouched. `file cluster/*.sh`: plain shell, Unix line endings; `cat` of
  both #16 scripts checked on the cluster. `evo-harness` conda env reused.
- `~/.evo_harness_env` (left by #15) rewritten over SFTP with the given model
  URL and key, mode 600; to be deleted when #16 finishes (and #15 no longer
  needs it: #15's vc33 round 5 is still owed).
- **Smoke check submitted, both games at once: job 75429 (ft09), job 75430
  (vc33)**, `cluster/job_smoke16.sh`, 15 min, 10 CPUs / 30 GB each.
- ~13:36, after a local 8-minute timer: **TC1 unreachable** (port 22 timed
  out, internet fine, no VPN adapter up; only Wi-Fi). Most likely the NTU
  VPN dropped, as in #15 (2026-11-25 19:28). Asked the user to reconnect.
  The jobs run on the cluster regardless; part 1 waits for the smoke result.

### 2026-11-26 — Smoke check: vc33 passed, ft09 failed in #14's kill test; fixed

- The user reconnected the VPN. One connection: `sacct` and both logs.
- **Job 75430 (vc33, TC1N03): COMPLETED 0:0, 3 min 15 s. Every check
  passed**: test suite (all self-tests passed on Python 3.12.16); game
  steps; model (both roles on 27B, flash HTTP 500); 5 seeds started at
  once; seed 1 finished, 2–5 cut and replayed on resume, lock gone;
  the action record in all 19 turn messages, 22/22 actions with a logged
  record; `action_log` in the sandbox; the state-change check on 5 saved
  states (seeds 1–5; every-step: the bar in row 0, `steps_left`); the repeat
  check on the saved store; **#15's `runs/ft09` and `runs/vc33`: 0 files
  changed**. Error log empty.
- **Job 75429 (ft09, TC1N02): FAILED 1:0 after 38 s, in the test suite**,
  before any #16 smoke check ran: #14's "checkpoint: a run killed in the
  middle of an episode resumes" failed its last check, "round 0: five
  episodes counted, over two parts". Its other checks passed (every seed once
  in the archive, nothing recorded twice, cut seeds [1, 2, 3, 5] replayed,
  seed 4 not).
- **Cause**: a race in #14's checkpoint, not #16 code. `evaluate()` writes
  `episodes.json`, then `run_state.json`. The test kills the run the moment
  `episodes.json` shows a finished seed; on TC1N02 the kill landed between
  the two writes. Seed 4 was finished (in `episodes.json`, so not replayed)
  but never recorded in the state file, so 4 episodes were counted. In a real
  run this loses no result, only one entry in the state file's bookkeeping
  (used by the time guard and the progress report). Stages already have
  `recovered()` for the same gap; episodes did not.
- **Fix**: on resume, `evaluate()` records once each seed that is in
  `episodes.json` but not in the state file (`Checkpoint.episode_was_completed`),
  with that episode's own wall time. New deterministic test
  (`checkpoint_episode_gap` in `evolve/selftest14.py`): the gap made on
  purpose; **without the fix it fails exactly as on the cluster
  (`[1, 2, 3, 5]`), with it it passes**.
- As the issue says, stopped and reported; part 1 not submitted.

## Open questions / risks

- **Interpretation, repeat check target for skills**: "same target" plus
  "names ignored" only makes sense if the skill's own name is ignored, so
  all skill code shares the target `skill`. A narrower reading (target = the
  skill's name) would let the same code back in under a new name.
- **Interpretation, edit types**: the Meta LLM's adds (new skill, prompt,
  step) are type "edit"; only a rule-based helper promotion is "promote".
- **Every-step threshold** (≥ 90 % of actions, ≥ 3 actions, ≥ 2 different
  actions) is mine. A counter that changes only on some actions (ft09's bar,
  only on tile clicks) is not every-step and stays in the lines, which is
  correct for ft09. A game whose counter sits right next to a changing area
  along its length could hide up to 2 cells of that area.
- **State-change verdict is net**: a skill that toggles a tile and toggles
  it back in one call counts as "no change". That follows the issue's "the
  game state and frame before and after".
- **Token cost of the record**: about 1–2.5 k chars per turn (≈ 300–700
  tokens); with ~100–200 turns per episode that is up to ~0.1 M tokens per
  episode, below the 1.2 M episode cap. Logged per turn.
- **#15 is not finished** (vc33 round 5). Nothing of #16 touches it: separate
  remote directory, separate run directories, new behaviour off in its config.
  The smoke job also checks that #15's run directories get no new file.
- The flash model is still down; the run uses the 27B fallback, as #15 did.

## Summary (fill in at the end)
