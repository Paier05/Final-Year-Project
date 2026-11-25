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

### 2026-11-25 14:40 — The games inspected; v0 audit posted and answered

- **ft09** (`scorer/ft09/GAME_NOTES.md`): only ACTION6 (click). Level 1 is
  a ring of 8 tiles around a pattern; a click toggles one tile's colour; the
  win check compares each tile with the pattern. 4 clicks solve it. A click
  that hits no tile changes nothing and costs nothing. 32-click budget bar.
- **vc33** (`scorer/vc33/GAME_NOTES.md`): only ACTION6. Two buttons move
  width between two columns; an object standing on one column must line up
  with a mark. 3 clicks on the right button solve it; every click costs one
  of 50 steps.
- Both confirmed by playing the solutions offline (clears on the last click).
- **v0 audit** posted (comment 7154981120): the `knowledge` prompt is all
  LS20; the rest is generic; skill-name check 0 on v0 and #14's v4. Also
  flagged: the Meta prompt's SCORE paragraph and Analyze's goal parts
  describe ls20's score.
- **The user answered in chat** (recorded on the issue, comment 7155007628):
  v0 for ft09/vc33 = v0 **without the `knowledge` prompt**; Meta prompt and
  Analyze get a **neutral score paragraph, parts not disclosed**.

### 2026-11-25 14:52 — Scorers, game-aware loop, click frame evidence, tests

- What I did:
  - `scorer/` package: `scorer/<game>/score.py` (read_state, score,
    fact-check ground truth) and `GAME_NOTES.md` for ft09 and vc33; ls20 is
    routed to #14's `evolve/goal_score.py`, unchanged.
    - ft09: one part, `tiles` = 1 − win checks failing / failing at the
      start (4 of 8 at the start). Weight 1.0.
    - vc33: one part, `alignment` = 1 − distance to the mark / distance at
      the start (6 grid cells). The win check's other two conditions never
      change on Level 1: recorded per state, no weight. Weight 1.0.
    - Both are the win checks' own comparisons, so nothing is guessed; and
      neither game's frame data has a score or progress field.
  - Wired by game, with ls20's output kept identical:
    `evolve/score.py`, `evolve/loop.py` (probe), `evolve/analyze.py` (no goal
    parts or failure line when the scorer does not disclose them),
    `evolve/propose.py` (the SCORE paragraph split out:
    `SCORE_DISCLOSED` for ls20, byte-identical rendered Meta input checked;
    `SCORE_UNDISCLOSED` for ft09/vc33), `evolve/factcheck.py` (GroundTruth
    gets per-game fields whose defaults are ls20's; other games' ground truth
    comes from `scorer/<game>/`), `evolve/seed_v0.py` (`drop_prompts`, set by
    `v0_drop_prompts` in the config).
  - Frame evidence click mode (`evolve/frame_evidence.py`): when at least
    half the actions are clicks, or no block is found, Part A lists actions
    and click coordinates, Part B groups every changed cell, Part C links
    each rare change to the click before it. The region code was moved into
    a helper both modes use. **Checked on #14's real round-4 episodes:
    ls20's evidence data, text and per-step table are identical** to before.
  - Fact-check ground truth for the new games: no action moves a sprite
    (ACTION6 claims unverifiable); absent roles false (lives, rotation
    switch, collectible, hazard, trail, enemy); budgets as counts; goal
    requirement colour (ft09) / position (vc33) true, rotation/collect/avoid
    false; nothing rotates; no player sprite. Colours not explained by a
    known object are "ui" (claims unverifiable), the background included.
  - `evolve_run.py`: `--game`, `--stage baseline --harness DIR` (baseline
    B), `--elapsed-min`. `config_evolve_15.yaml`: #14's settings except 3
    seeds, per-game weights, `v0_drop_prompts: [knowledge]`.
    `baselines/issue14_v4/` = #14's v4, copied unchanged from `runs/v3`.
  - `evolve/smoke.py`: its "game steps" check clicked (0, 0), which changes
    nothing in ft09; it now tries a coarse grid of spots for ACTION6.
- **Bug found by the leak test**: Analyze still called ls20's
  `describe_failure` on ft09 episodes (KeyError) before throwing the result
  away. Fixed: nothing is computed when parts are not disclosed.
- **Limit worth knowing (vc33)**: the step bar (row 0) touches the top
  column, so frame evidence groups the bar and both columns into one
  "regular" region; the button's effect does not stand out as rare. Added,
  generically: per clicked cell, the median number of cells a click there
  changed (a button click changes ~265 cells, a miss 1-2). No game code.
- Tests (`scorer/tests.py`, also run by `python -m evolve.selftest`):
  - scorers: a win scores 1.0; 40 random clicks (seed 7) score below; same
    trajectory twice and a replay of its clicks score the same; 2 right
    clicks score strictly between; the start scores 0; no state before the
    clear reaches 1.0.
  - frame evidence: runs on saved ft09/vc33 trajectories; same output twice;
    a click game and a no-block keyboard episode both report actions instead
    of a position; Part C links ft09's 8 tile regions to clicks inside them.
  - fact-check labels per game; v0 without `knowledge` (rest identical,
    skill-name check 0); the sandbox cannot import `scorer` or open files.
  - **leak test**: patterns for each game's notes (internal names, win rule,
    solution, budgets), each shown to fire on a sample; none in v0, the Meta
    prompt and its neutral score text, the API text, the frame-evidence and
    Analyze code, a full Meta LLM input built from round 0 of the #15 config,
    or the stored Analyze report. The part names are not in the Meta input.
- Result: **`python -m evolve.selftest`: 224 checks pass locally** (all of
  #12's and #14's plus #15's). The SIGUSR1 test runs only on Linux (smoke).
- Baseline stage tried with the stub player on vc33: summary, harness copy,
  trajectories written; exit 0.

### 2026-11-25 14:57 — TC1: login, upload, smoke check submitted

- Credentials: the user gave the cluster login and the model URL/key in chat.
  They go to `cluster/tc1.py` as environment variables per call and are
  stored nowhere on this machine or in the repo. The model URL and key are
  the same as the local `.env`.
- `MyTCinfo`: QoS `normal`, MaxTRESPU cpu=20, gpu=1, mem=64G, **MaxSubmit
  2**, MaxWall 6 h, partition `UGGPU-TC1`. No jobs of mine queued. Home 4.5 GB
  used.
- MaxSubmit counts queued jobs too, so with one job per game nothing else
  can be queued: **baseline B moved into each game's part-1 job** (before the
  run), rather than a separate pair of jobs I would have to wait out.
- `conda` needs `module load anaconda` in a login shell; the `evo-harness`
  env from #14 is there (Python 3.12.16, numpy 2.5.4, arc-agi 0.9.9,
  arcengine 0.9.3). Reused unchanged.
- `~/.evo_harness_env` from #14 was still there (its deletion was owed when
  the head node stopped answering on 2026-11-17). Rewritten over SFTP with
  the same two variables, mode 600; to be deleted when #15 finishes.
- Upload: commit `b0a0955` + `environment_files/{ls20,ft09,vc33}`;
  `file cluster/*.sh`: plain shell scripts, Unix line endings; `cat` of
  both #15 scripts checked on the cluster.
- **Smoke check submitted, both games at once: job 75152 (ft09), job 75153
  (vc33)**, `cluster/job_smoke15.sh`, 15 min, 10 CPUs / 30 GB each.
- Model still down at 14:55 (both models HTTP 500). Expected: the smoke
  check's model test fails. Posted the preparation summary on the issue
  (comment 7155338451).

### 2026-11-25 15:08 — Smoke check failed on the model endpoint; stopped

- Waited with a local timer (checking only the model gateway once a minute,
  not the cluster), then one connection.
- **Jobs 75152 (ft09, TC1N02) and 75153 (vc33, TC1N04): FAILED 1:0**, both
  14:57:19–14:58:48. Error logs empty.
  - Test suite: **pass on both nodes, 229 checks** (224 + 5 SIGUSR1).
  - Game loads and steps from the offline files: pass on both (the smoke
    test's new click spots work for ft09).
  - Both ran at the same time without clashing: separate run directories
    and logs.
  - **Model endpoint: FAIL** on both: HTTP 500, connection refused behind
    the gateway, flash and the 27B fallback alike. So the short episode,
    the checkpoint and the resume checks were not reached.
- Local check: still down at 15:06.
- As the issue says: stopped and reported (comment 7155500811). Nothing
  queued. Baseline B and part 1 not submitted.

### 2026-11-25 16:04 — Model back (27B only); smoke check resubmitted

- The user said the model is up. Local preflight at 16:04: **flash still
  HTTP 500; `Qwen/Qwen3.8-27B-FP8` answers.** Per the user's rule from #14
  (in the config as `fallback_model`), both roles fall back to 27B. #14's
  whole run was on 27B too, so the player and Meta model match #14's run.
  The run pins the model its first part uses.
- **Smoke check resubmitted: job 75181 (ft09), job 75182 (vc33)**, same
  commit `b0a0955` on the cluster (only the work log changed since).

### 2026-11-25 16:10 — Smoke check passed; part 1 submitted

- **Jobs 75181 (ft09, TC1N03, 2 min 18 s) and 75182 (vc33, TC1N04,
  2 min 13 s): COMPLETED 0:0.** Error logs empty.
  - Test suite: 229 checks pass on both nodes (224 + 5 SIGUSR1).
  - Game loads and steps: pass. Model endpoint: pass, both roles on
    `Qwen/Qwen3.8-27B-FP8` (flash still 500).
  - One short episode per game (ft09: 2 turns, 12 clicks, 10.3k tokens,
    26 s; vc33: 3 turns, 2 clicks, 10.9k tokens, 24 s), the run stopped on
    request, `run_state.json` paused with seeds done [1], the resume
    replayed only the cut-off seed 2 and finished, lock gone.
  - Both games at once: same 2 minutes, separate nodes, run dirs
    (`runs/smoke_ft09_75181`, `runs/smoke_vc33_75182`) and logs.
  - `seff`: 69 s CPU, ~230 MB memory each (of 10 CPUs / 30 GB asked).
- **Part 1 submitted at 16:10: job 75186 (ft09), job 75187 (vc33)**
  (`cluster/job_api.sh`, 6 h, 10 CPUs / 30 GB each, 20 CPUs / 60 GB in
  all, no GPU). Each plays baseline B (#14's v4, seeds 1–3) first, then
  starts the 5-round run with `--resume`.
- One check at 16:14: both RUNNING (TC1N03, TC1N04), baseline B playing on
  both games (12–16 turns per seed), error logs empty. Disconnected.
  Job ids posted on the issue. Next: wait for the user's "continue".

## Open questions / risks

- **Model availability (was blocking 14:33–~16:00).** Both models are down at the provider
  since at least 14:33. Using a different model would break "same setup as
  #14"; that is the user's decision.
- **Script A, not B**: #14 called the model over an API (no GPU), so each
  game is its own job (10 CPUs, 30 GB; 20 CPUs and 60 GB in all).
- **Baseline B runs inside part 1's job**, before the run, because the QoS
  allows 2 jobs at a time and both are needed for the two games. The run's
  time guard is moved back by the minutes baseline B used (`--elapsed-min`).
  If baseline B fails, the job stops before the run.
- **Delete rule**: kept at 10 evaluated episodes (#14's value), which is
  3–4 rounds at 3 episodes instead of 2 at 5.
- **The fact-check vocabulary is ls20's** (player, goal, rotation switch,
  ...). For click games most claims will come out unverifiable (kept,
  flagged). That is conservative by design: false only where the game
  clearly contradicts the claim.

## Summary (fill in at the end)
