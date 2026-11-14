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

### 2026-11-15 01:30 — Fix 1: skill-name check; audit of v0 and #12's versions

- What I did:
  - `evolve/skill_names.py` reads every text of a harness and lists names
    used like a skill that are not one. Prose (prompts, steps, docstrings):
    call-like `name(...)` and backticked identifiers; backticked code is
    parsed. Skill code: calls found in the AST; names the function binds
    itself are not references.
  - Valid names: the candidate's skills, the sandbox API, the sandbox's
    builtins. Short allowlist `NOT_SKILLS`: action names, engine states, the
    fields of the API's return values.
  - In `validate.py` it is check 7, run right after the static tests. It
    compares the harness before and after the edit, so it flags only what
    the edit caused, including a delete or merge that leaves a name behind.
  - The reason and the CHANGELOG give the missing name, the file and the line.
- Decision: an edit that fails only this check is **held and retried** after
  the other edits of the set. The issue says valid names include "skills
  added or promoted in the same edit set". Validate applies edits in order,
  so without the retry a prompt edit listed before the skill it names would
  be dropped. An edit that still fails after the retry is dropped.
- Audit (`results/evolve_14/skill_name_audit.txt`):

  | version | missing names | where |
  |---|---|---|
  | v0 | 0 | — (nothing to fix before round 1) |
  | #12 v1 | 0 | — |
  | #12 v2 | 3 | `detect_orientation`, `rotate_cluster` in `knowledge`; `rotate_cluster` in step 4 |
  | #12 v3 (best of the 5 rounds) | 4 | `analyze_cluster_state`, `try_rotate` in `knowledge` and in step 4 |
  | #12 v4 | 2 | `analyze_cluster_state` in `knowledge` and step 4 |
  | #12 v5 | 4 | as v3 |
  | #12 v6 (final parent of the extension) | 2 | `find_goal` in `knowledge` and step 4 |
  | #12 v7 | 2 | `find_goal` in `knowledge` and step 4 |

  - New finding: the gap started at v2, one round earlier than #12's log
    said (it named v3). Every accepted version from v2 on told the player to
    call at least one skill that did not exist.
  - #9's v0–v5 have none.

### 2026-11-15 01:40 — Fix 2: frame evidence

- What I did: `evolve/frame_evidence.py`, wired into `analyze.py` and the
  Meta LLM's message (`propose.py`).
  - **Finding the block.** For each step it looks for a patch that moved
    rigidly: cells p where p and p+s both changed and what was at p is now at
    p+s. The same test fits "the floor moved by −s", so of the two the patch
    with the rarer colours is taken. The pattern seen in 3 agreeing steps is
    the block. Then the block is tracked by exact pattern match in each frame.
    Nothing tells it where to look or which colour to look for.
  - **Other changes.** Changed cells outside the block's old and new position
    are clustered into regions (cells within 2 of each other), pooled over
    the version's episodes. Clusters that change on exactly the same steps
    are merged (one thing redrawn as a whole). A region that changes on ≥ 50%
    of the steps that change anything is regular; otherwise each change is an
    event.
  - **Link.** Each event carries the action, the block's position before and
    after, the region's values before and after, and what the stepped-on cell
    held. Per region: for each cell the block entered when the region
    changed, how many times the block entered that cell in all episodes and
    how many of those the change followed.
  - "Open cells never visited": cells one normal move from a visited or open
    cell that show only the floor the block leaves behind.
- Checked against #12's data (the game's own logged positions): the block's
  position after each step is right on 2,886 of 2,886 steps (rounds 0, 4 and
  7). Build time 0.3 s for 5 episodes.
- What it shows on #12's v4 (the version with the best episode): one rare
  region, rows 57–58, cols 3–8, changed twice: once when the block entered
  (30,19), once when the block jumped back to the start. In v0 and v7: no
  rare change at all, in any episode. This is the evidence the Meta LLM
  never had.
- Choices worth knowing:
  - A cell that holds something other than floor is not listed as "open,
    never visited". From frames alone the code cannot know it can be
    entered. So the switch cell shows up only once a player steps on it.
  - The lives display sits within 2 cells of the move counter, so both are
    one regular region. A life lost is still visible as a jump of the block.
  - Limit: the block is found from moves of at least its own size (ls20's).
- Dead end: my first version paired changed components of equal shape. In
  ls20 the block moves by exactly its own size, so the vacated and the filled
  patch touch and form one component. Replaced by the shift search above.

### 2026-11-15 01:45 — Fix 3: rotation part of the score

- What I found: #12's scorer read `cklxociuu` (the held rotation index, +1
  mod 4 at each switch touch, line 1906 of ls20.py) and `ehwheiwsk[i]` (the
  goal's), the two values `bejndxqqzf` compares at line 2040. So it read the
  right things, from game state, never the moving block's look. It compared
  them for equality.
- What changed: the part is now `max(0, 1 − needed / needed at the start)`
  with `needed = (goal − held) mod 4`. The episode record also says whether
  a touch too many happened and when.
- Assumption (small, logged, not asked): the normalisation. `1 − needed/4`
  would give an untouched start 0.75 for rotation and put "under the goal,
  never rotated" (0.84) above "rotated, at the switch" (0.60), which is the
  wrong order. Normalising by the start, as the position part does, keeps
  #12's ladder. On Level 1 it equals #12's 0/1 value.
- Rescored #12 (`analysis/rescore_12.py` → `results/evolve_14/rescored_12.json`):
  all 40 episodes (v0–v7), **largest difference 0.0**. New fact from the
  rescore: 5 episodes overshot at some point (v1 1, v2 2, v3 1, v6 1).
- "A second touch should lower the score": it lowers that state's score
  (0.6 → 0.2 at the switch). An episode still scores its best state, as in
  #12, so an episode that matched once keeps that credit.

### 2026-11-15 01:55 — Fix 4: checkpoint and resume; a #12 mystery solved

- What I did: `evolve/checkpoint.py`, and `evolve/loop.py` and
  `evolve_run.py` rewritten around it (see the commit message of ec7c87d).
- Decisions:
  - The stage files stay the record; `run_state.json` is their summary.
    `--stage status` cross-checks the two.
  - Propose and Validate are saved separately (`attempts.json`), so a cut in
    Validate does not repeat the Meta LLM call.
  - A clean stop exits 0 with status `paused`, so `sacct` shows COMPLETED for
    a part that hit the time guard and FAILED only for real errors.
  - On a stop request the run waits for turns in flight (120 s at the stop
    time, 10 s on SIGUSR1), then exits anyway. The state on disk is complete
    up to the last finished unit, so nothing is lost; the cut episodes are
    replayed.
  - Lock: a lock whose process is dead (same host) or whose SLURM job is no
    longer queued is taken over; otherwise the run refuses (`--break-lock`).
- **Found while testing: why #12's log stopped mid-run.** A stub run through
  the new driver printed nothing after "evaluating v0". The sandbox used
  `contextlib.redirect_stdout`, which swaps `sys.stdout` for the whole
  process. Two cells in parallel threads restore each other's buffer and
  leave `sys.stdout` on a dead StringIO. That is #12's "unexplained" lost
  stdout (2026-11-02 17:05). Removed the redirect; cells already print
  through the sandbox's own `print`. It matters here: on the cluster the
  SLURM output file is stdout.
- **Consequence of the time guard, worth knowing before part 1.** #12's
  episodes took about 2.3 h with 5 in parallel. Longest × 1.5 ≈ 3.5 h must
  fit before 5 h 40 min, so after round 0 (about 2.4 h in) the next round
  will not start: **about one round per 6-hour part, so about 6 parts**, each
  using roughly half its time. The factor is `checkpoint.factor` in the
  config; I left it at the issue's 1.5.

### 2026-11-15 02:05 — Tests, local smoke, model status

- `python -m evolve.selftest`: **146 checks pass** (76 from #12, 70 new).
  - Fix 1's three tests, plus forward references and skill code.
  - Fix 2's four tests on scripted episodes of the real game.
  - Fix 4's three tests. The mid-episode one really kills the driver process
    (no cleanup, lock left behind) and resumes it.
  - Leak test: v0, the hand-written templates, a full Meta LLM input.
  - Not run here: the SIGUSR1 test (Windows has no SIGUSR1). It runs in the
    cluster smoke job.
- Local `--stage smoke` against the real endpoint: all checks pass.
- **The flash model is down** (HTTP 500 from the gateway's backend, as on
  2026-11-04/05). The user's rule ("if the flash model is down, use the
  normal one") is in the config as `fallback_model: Qwen/Qwen3.8-27B-FP8`.
  - Added: the run keeps the models its first part used, so versions are
    compared on one model. A later part falls back, and records it, only if
    those are down when it starts. Each episode records the model it used.
  - If part 1 starts on 27B, this run is a 27B run, and "this run vs #12"
    (flash for v0–v5, 27B for v6–v7) is not a same-model comparison.
- The error text quoted the start of the gateway's backend address. `redact`
  now masks every URL in printed errors.

## Open questions / risks

- **Model.** Flash is down as of 2026-11-15 02:05. Per the user's rule the
  run falls back to `Qwen/Qwen3.8-27B-FP8`, and then stays on it. That
  changes what the comparison with #12 means (see the entry above).
- **About one round per part** with the issue's factor 1.5 (see fix 4).
- **Rotation normalisation** is my choice (see fix 3). It reproduces #12's
  values exactly on Level 1.
- **Frame evidence is not a full scene description.** Lives and move counter
  are one region; cells holding objects are not listed as unvisited.
- **SIGUSR1 path is untested until the smoke job** (cannot be sent on
  Windows).
- **The skill-name check can reject a harmless backticked word** that is not
  in the allowlist (say a variable name the Meta LLM suggests). The Meta
  prompt now says how names are read; rejections are counted per round.
- **No ARC API key was given.** The game runs offline from
  `environment_files/`, so the smoke job's "ARC API reachable" check is
  reported as not applicable.

## Summary (fill in at the end)
