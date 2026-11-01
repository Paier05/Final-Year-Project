# Work Log — Issue #9: 5-generation evo-harness run on ls20 (level 1 only) with Qwen3.8-27B

**Issue:** https://github.com/Paier05/Final-Year-Project/issues/9
**Branch:** `experiment/9-evo-harness-ls20` (renamed from `experiment/9-evo-harness-ls20-5-rounds` on 2026-11-01; see the progress log)
**Started:** 2026-11-01

## Understanding the issue

Run a self-evolving harness loop on ARC-AGI-3 game `ls20`, **Level 1 only**, with
Qwen3.8-27B as the player, for 5 evolution rounds. Report how the harness and the
score change across rounds.

Two halves, following the issue's diagram:

- **Action harness (plays).** Harness vN = `steps · prompts · skills/`. Each turn the
  player LLM writes Python that runs in a sandbox with the episode state and the
  harness's skills preloaded; the code acts on the game via `action()`. Every tool
  call (code execution) is logged, one JSONL per episode at
  `trajectories/round_N/episode_K.jsonl`.
- **Meta harness (evolves).** 1 Analyze (skill stats, inline-helper usage) →
  2 Propose (add / merge / delete / edit on skills, prompts, steps; rule-based plus an
  optional Meta LLM) → 3 Validate (tests, replay, merge-equivalence; drop failures) →
  4 Write vN+1 (+ `CHANGELOG`) → 5 Gate (dev gain > 0 and drop ≤ δ). Every version and
  its score, parent and gate decision go into `archive.json`.

### Decisions on the issue's TBDs (asked and answered by the user, 2026-11-01)

| Param | Value | Note |
|---|---|---|
| Episodes per round | **3** | each version is evaluated on 3 episodes (seeds 0, 1, 2) |
| Step budget per episode | **200 game actions** | same as #8, so v0 compares with #8 |
| Gate | **gain = mean score(child) − mean score(parent) > 0; drop = worst-episode score(parent) − worst-episode score(child) ≤ δ = 0.1** | |
| "6-step turn" | **a 6-item step procedure + an action cap** | v0's `steps` is a 6-item procedure the model follows each turn; one LLM call per turn returns one code cell, which may call `action()` at most 6 times |

**Per-episode score** (needed because #8 cleared Level 1 0/6 times, so a clear-rate-only
gate could never fire): a clear scores `0.5 + 0.5·min(1, 22/actions)²` (22 = the human
level-1 baseline, the same term as #8's level score); an unsolved episode scores
`0.5·progress`, with `progress = max(0, 1 − closest_approach / start_distance)` measured
from saved frames by #8's approach-distance code. A clear therefore always beats a
non-clear.

### Assumptions I am making (small, logged rather than asked)

1. **Base branch is #8's branch, not `main`.** #9 needs #8's harness, perception, model
   client and figure code, and #8 has not been merged (no PR open). Branching from
   `main` would mean re-creating all of it. When #8 merges, this branch rebases cleanly
   because it only adds files on top.
   *Superseded 2026-11-01 at the user's request: the branch was rebuilt on `main`
   with only the #8 code #9 imports. See the progress entry "Branch rebuilt on main".*
2. **v0 = the current harness, ported to code-acting.** #8's harness emits one JSON
   action per turn; #9's loop runs code. v0 therefore keeps #8's rules, its observation
   format, its 4 validated code modules (as Python skill functions) and its mined
   ls20 action-effect rules (as a `knowledge` prompt). Nothing new is added to v0 that
   was not in #8's Round 1 harness, other than what code-acting itself needs (the
   sandbox API and the 6-step procedure).
3. **Seeds are not level variants.** Verified: `ls20`'s first frame is identical for
   seeds 0, 1, 2, and replaying #8's logged actions under seed 7 reproduces all 200
   frame hashes. Episodes differ only by model sampling (temperature 0.2). "3
   episodes" is therefore 3 samples of one level, and the report must say so.
4. **Meta LLM is on** (Qwen3.8-27B-FP8, same endpoint). The issue marks it optional,
   but the report has to split edits by Meta LLM vs rule-based, which needs both.
5. **Credentials** are read from `QWEN_API_KEY` / `QWEN_BASE_URL` (env or the
   gitignored `.env`), never written to config, logs or `archive.json`.
6. **Round numbering.** Round 0 evaluates v0. Round N (1..5) analyses the current
   parent's trajectories, proposes, validates, writes vN, evaluates it, and gates it
   against the parent. vN exists for every round, accepted or not.

## Plan

1. Preconditions, branch, this log. ✅
2. **Sandbox + code-acting action loop** (`evolve/sandbox.py`, `evolve/action_loop.py`):
   restricted `exec` with an AST filter (no dunder access, imports limited to
   `math/collections/itertools/numpy`, no `open/eval/exec`), a per-cell time limit, a
   persistent namespace, `action()` capped at 6 per turn and 200 per episode, and
   skill calls wrapped so their use and errors are counted. Log every code execution.
3. **Harness versions** (`evolve/harness.py`): load/save `steps.json`, `prompts.json`,
   `skills/*.py`; render the system prompt; build v0 from #8.
4. **Meta harness**: `analyze.py`, `propose.py` (rule-based + Meta LLM), `validate.py`
   (AST/compile tests, replay of real recorded states on a live env,
   merge-equivalence, reference checks for deletes, prompt-size/format checks),
   write vN+1 + `CHANGELOG.md`, `gate.py`, `archive.json`.
5. **Offline self-test** with a stub player and stub Meta LLM: run 2 rounds end to end
   with no model calls before spending anything.
6. **Pilot**: one real v0 episode to measure cost per episode with code-acting.
7. **The run**: round 0 + 5 rounds, 3 episodes each, episodes in parallel.
8. **Figures** with #8's figure code (`analysis/figures.py` styling, `analysis/approach.py`,
   `analysis/movement.py`), plus the score-per-round / accepted-vs-rejected figure.
9. Report comment on the issue with every checklist item, then the PR.

## Progress log

### 2026-11-01 — Preconditions, decisions, and a determinism check

- **What I did:** Checked remote, `gh auth`, working tree; read issue #9 and its
  architecture diagram; read #8's code, work log and report; asked the user to settle
  the four open parameters; created the branch; stored the credentials in the
  gitignored `.env` under the names the issue specifies.
- **Why:** Workflow step 0-3, and the TBDs decide how many hours the run takes.
- **Result / what I found:**
  - Working tree is not clean, but only with untracked files that are not this
    issue's: `.vscode/`, `experiments/` (issue #4's artefacts), and #8's run logs
    (`results/round*_ls20.log`, `results/run_info.json`). Untouched, left untracked.
    #9 writes under `results/evolve/` so it cannot collide with #8's files.
  - The endpoint lists `Qwen/Qwen3.8-27B-FP8` and the supplied key is the same one
    #8 used.
  - **ls20 is deterministic and seed-independent** (see assumption 3). That makes
    replay-based validation sound: any recorded game state can be rebuilt exactly
    by replaying the logged actions.
- **Next step:** Build the sandbox and the code-acting action loop.

### 2026-11-01 — Action harness: sandbox, code-acting loop, v0, replay

- **What I did:** Built `evolve/sandbox.py`, `evolve/harness.py`, `evolve/seed_v0.py`,
  `evolve/action_loop.py`, `evolve/replay.py`, `evolve/score.py` and an offline
  `evolve/stub.py`; ran a stub episode on the live ls20 env and replayed it.
- **Why:** The action loop is the thing being evolved, and replay is what makes
  Validate's "replay" and "merge-equivalence" checks real rather than nominal.
- **Result / what I found:**
  - **The first sandbox draft was escapable**, found by reading the stdlib rather
    than by testing: `statistics.sys`, `re.enum.sys` and `collections._sys` all
    reach `sys`, and a generator's `gi_frame.f_back.f_globals` reaches the real
    builtins. Fixed by refusing every attribute that starts with `_` plus a named
    list (`gi_frame`, `f_globals`, `sys`, `os`, numpy file I/O, `random`, ...) and
    dropping `re`/`statistics` from the import allow-list. 15 hand cases pass,
    including `while True` inside `try/except Exception` (the timeout is a
    `BaseException`, so it cannot be swallowed) and a bare `except:` (rejected).
  - **v0 is a faithful port with one deliberate correction.** #8's skill header
    said the rules were mined "from a *different* set of games"; for ls20 they
    were mined from ls20 itself, so v0 says "from previous play on this game".
    v0's system prompt is 7.2k chars (#8's was 2.9k + the library).
  - **Replay works as the validation basis** (stub episode, 20 turns):
    parent harness reproduces 20/20; deleting a *called* skill diverges at turn 1
    (15/20); deleting an unused skill reproduces 20/20; promoting the stub's inline
    helper to a skill (with its inline `def` stripped from the cells) reproduces
    20/20 **and** the skill really ran (15 calls), so the check is not vacuous.
- **Next step:** Meta harness: Analyze, Propose, Validate, Write, Gate, archive.

### 2026-11-01 — Meta harness built; offline end-to-end run; a merge-check hole found and closed

- **What I did:** Built `evolve/edits.py`, `analyze.py`, `propose.py` (rules + Meta
  LLM), `validate.py`, `loop.py` (Write, Gate, `archive.json`, `CHANGELOG.md`,
  parallel evaluation, resume), `config_evolve.yaml`, `evolve_run.py`, and an
  offline self-test `python -m evolve.selftest`. Ran the full loop with the stub
  player + stub Meta LLM for 2 rounds (`evolve_run.py --stub`).
- **Why:** Everything except the model can be verified for free; a bug found here
  does not cost an 18-episode run.
- **Result / what I found:**
  - Stub run, 2 rounds, 0.9 min: v0 evaluated, then each round analyzed →
    proposed (rule + meta) → validated → wrote vN → evaluated in parallel → gated.
    Round 2's rules deleted the three skills never called in 6 episodes (v0's 3 +
    rejected v1's 3), and promoted the stub's inline helper. The skill that calls
    `open()` was dropped at the AST stage. Both children were rejected with gain
    0.0000, which is correct: the stub ignores the prompt, so nothing changed.
  - **The self-test caught a real hole in merge-equivalence.** A merge that
    replaced `player_detector` with `return []` *passed*, because the stub stores
    that skill's result without acting on it, and I was comparing only actions.
    Same actions is not same behaviour. Fixed: every skill call's return value is
    now fingerprinted during replay, and a merge must reproduce the originals'
    return values call by call on the recorded inputs. Re-run: the bad merge is
    dropped ("call 0 of 3 returns a different value"); the exact-duplicate merge
    still passes.
  - Step indices in edits refer to the parent's numbering and are resolved through
    stable step ids. The Meta LLM will mis-count shifting indices, and a dropped
    edit would otherwise silently re-target every later one.
- **Next step:** Real pilot: one v0 episode with Qwen3.8-27B, to measure cost and
  see whether it handles code-acting at all.

### 2026-11-01 — Blocked: the model backend is down; figures built meanwhile

- **What I did:** Ran `evolve_run.py --stage preflight`. Started a background probe
  of `chat/completions` once a minute for up to an hour. Meanwhile built
  `analysis/evolution.py` (score per round, approach curves per version, movement
  traces per version) on top of #8's figure code, rendered it from the stub archive
  and looked at it. Added credential redaction to `evolve_run.py`.
- **Why:** Nothing can be measured until inference works; the figures and the
  redaction do not need it.
- **Result / what I found:**
  - **Blocker:** the gateway lists `Qwen/Qwen3.8-27B-FP8` and accepts the key, but
    every chat call returns `500 ... dial tcp 127.0.0.1:1086: connect: connection
    refused`: the provider's upstream model server is not running. This is the
    same failure mode #8 hit. #8's preflight hardening caught it in seconds, before
    any episode could be recorded.
  - **The endpoint URL was being printed.** `harness.model`'s abort messages embed
    the base URL, and the issue treats `QWEN_BASE_URL` as a credential. #9's driver
    now redacts both the URL and the key from everything it prints. Nothing in
    `results/evolve/` ever contained them.
  - Figures: the score chart's legend first collided with the "clear ≥ 0.5" line;
    moved it below the plot. Gate decision is encoded by colour **and** marker
    shape, with every mean direct-labelled, because the green slot is below 3:1
    contrast (palette validator WARN, all other checks pass).
- **Next step:** Wait for the backend; then the pilot.

### 2026-11-01 — One name for the model key (user request)

- **What I did:** At the user's request, pointed #8's code at `QWEN_API_KEY` instead
  of `ARC_MODEL_API_KEY`: the default in `harness/model.py` `load_api_key()`, its
  error message, the comment in `config.yaml`, and the reproduce line in
  `REPORT.md`. Removed the now-duplicate `ARC_MODEL_API_KEY` line from the
  gitignored `.env`.
- **Why:** Both names held the same key; `.env` had it twice. One name now serves
  #8's `run.py` and #9's `evolve_run.py`.
- **Result:** No reference to `ARC_MODEL_API_KEY` remains. `run.py --stage
  preflight` loads the key and the gateway accepts it (it then stops on the same
  backend outage as #9). The base URL for #8 still comes from `config.yaml`, which
  was not part of the request.
- **Next step:** Still waiting for the backend.

### 2026-11-01 — Branch rebuilt on main with only what #9 needs; PR #10 opened for #8

- **What I did:** At the user's request ("leave only the files #9 needs ... the result
  of #8 is not needed, just leave the function"):
  1. Committed the `QWEN_API_KEY` rename on **#8's** branch, where those files live,
     and opened **PR #10** for issue #8 with all of #8's results.
  2. Rebuilt this branch from `main`: this work log's first commit, then one commit
     bringing in the **14 #8 modules #9 imports** (6 in `harness/`, 3 in `learning/`,
     5 in `analysis/`, plus #8's `.gitignore`), byte-identical to PR #10, then #9's
     own commits cherry-picked unchanged. The old branch is kept locally as
     `backup/9-before-clean`.
  3. Froze v0's `knowledge` prompt into `evolve/seed_v0.py` (`KNOWLEDGE_V0`) instead
     of reading #8's `skills/index.json` at run time.
- **Why rebuild rather than delete:** deleting #8's results in a new commit on this
  branch would have deleted them from `main` too, once #8 merged and then #9 did.
  Rebuilding means #8's results never enter this branch's history, so merging it
  in either order cannot remove them; the shared modules are identical on both
  sides, so they merge without conflict.
- **Result / what I found:**
  - Left out of this branch (all still in PR #10): `run.py`, `config.yaml`,
    `REPORT.md`, `WORK_LOG-8.md`, `docs/`, `results/` (#8's episodes, summary,
    figures, game list), `skills/`, and the three #8 modules #9 never imports
    (`harness/games.py`, `harness/stub_model.py`, `learning/skill_library.py`).
  - **Freezing the knowledge text mattered beyond tidiness:** the old loader returned
    `""` when `skills/index.json` was missing, so on a branch without #8's results
    v0 would have silently lost its `knowledge` prompt rather than failing.
  - Verified on the rebuilt branch: v0's rendered system prompt has the **same SHA-1**
    as before (7,228 chars); `python -m evolve.selftest` passes; a fresh 2-round stub
    run gives the same numbers as before the rebuild (v0 mean 0.1579, worst 0.0877)
    and exercises all three drop paths (AST violation, core prompt delete, over-cap);
    the figures render.
- **Next step:** Still waiting for the model backend.

### 2026-11-01 — Clean history pushed under a new branch name

- **What I did:** Pushed the rebuilt history as **`experiment/9-evo-harness-ls20`**
  instead of overwriting `experiment/9-evo-harness-ls20-5-rounds`.
- **Why:** Replacing the old remote branch needs a force-push, which the session's
  permission check blocked. Of the two options I gave, the user chose a new name,
  which overwrites nothing.
- **Result:** The old remote branch `experiment/9-evo-harness-ls20-5-rounds` still
  holds the pre-cleanup history (#8's commits plus #9's, head `4f34a55`). It is
  superseded and is left for the user to delete. All #9 work continues on the new
  branch.
- **Next step:** Still waiting for the model backend.

### 2026-11-01 — Backend back; pilot started

- **What I did:** The user reported the model is up. `--stage preflight` now passes
  for both roles (`player: Qwen/Qwen3.8-27B-FP8 OK`, `meta: Qwen/Qwen3.8-27B-FP8 OK`).
  Started the pilot, one real v0 episode written to `data/evolve_pilot/` (gitignored,
  outside the experiment tree). Also made the pilot's error path redact the endpoint
  like the main run already does.
- **Why:** The pilot measures tokens and wall time per episode before 18 episodes
  are committed to, and shows whether Qwen handles code-acting at all.
- **Result: the pilot found an API bug, so I stopped it after 2 turns.** Qwen does
  write code blocks (no parse failures; about 3k tokens in, 300–500 out, 8–12 s
  per turn). But both cells died with `KeyError: 'id'`. The observation lists
  objects as `id=N ...` (#8's `describe_grid`), and v0's system prompt talks about
  ids, but `objects()` removed the `id` field. So the model was told about a field
  the API didn't give it. Because the error came before its `notes = ...` line,
  its notes were lost as well.
- **Fix:** `objects()` now keeps `id`, and the API doc lists it. This is the fixed
  action loop, not the harness under evolution, so it applies to every version
  equally. v0's prompts, steps and skills are unchanged, but the rendered system
  prompt grows by one line of API doc. Checked that `objects()`'s ids equal the
  observation's ids on the start frame and after 1 and 3 actions. The self-test
  still passes.
- **Next step:** Re-run the pilot from scratch (the 2 aborted turns don't count).

### 2026-11-01 — Pilot: v0 plays sensibly, nearly clears; cost measured

- **What I did:** Re-ran the pilot after the `id` fix: one v0 episode, written to
  `data/evolve_pilot/` (not part of the experiment).
- **Result:**
  - **Outcome:** not cleared. It used the full 200-action budget over 141 turns,
    with 1 reset. Its closest approach was 1.5 cells, against a start distance
    of 28.5, so progress was 0.947 and the score 0.474.
  - **Cost:** 596k tokens in, 106k out, 44.8 min. That is about 5k tokens and
    19 s per turn.
  - **Clean:** no parse failures and no time-outs.
  - **Cell errors (13), none of which cost actions:**
    - 10 calls to actions this game doesn't offer (`ACTION6` ×9, `ACTION7` ×1);
      the API raises an error and the call is free;
    - 3 syntax errors.
  - **Actions:** 15 of the 200 changed nothing.
  - **Skills:** `grid_region` 39 calls, `player_detector` 3; `obstacle_map` and
    `bfs_to_target` were never called. No inline helpers were defined.
  - **Turn shape:** most turns took 1 action (79 turns) or none (29). Only 7
    used all 6.
  - **Learning:** within 2 turns it corrected v0's mined rule that ACTION2
    "recolours lime" to "ACTION2 = down 5".
- **What it means for the run:**
  - **Tokens:** 18 episodes at about 0.7M each is about 13M, plus the Meta calls,
    which is under the 25M global cap. Each episode is under its own 1.2M cap.
  - **Time:** about 45 min per episode on its own, so about 6 batches of 3
    parallel episodes, roughly 5 h if parallel play doesn't slow the endpoint.
  - **Untouched skills:** two of v0's skills went unused. If that holds across
    round 0, the rule-based delete will start to fire once they have 6 episodes
    of lifetime non-use.
- **Risk noted:** the 5400 s per-episode wall-time cap is 2× the pilot's time. If
  3 parallel episodes slow the endpoint enough, episodes could be cut by wall time
  rather than actions. That would make results depend on server load, so I'll
  check `end_reason` after round 0.
- **Next step:** `python evolve_run.py --rounds 5`.

### 2026-11-01 — Full run: rounds 0 and 1

- **Round 0 (v0):** scores 0.088, 0.474, 0.439, so mean 0.333 and worst 0.088.
  No clears. All 3 ran out of actions (none hit the wall-time cap); episodes took
  22–30 min with 3 in parallel, and about 1.0M tokens in total.
- **Round 1 (v1, 3 Meta edits, all passed Validate):**
  - The edits: add `collect_items` and `player_position`, and rewrite the
    `knowledge` prompt.
  - Scores 0.263, 0.474, 0.474, so mean 0.404 and worst 0.263. No clears.
  - **Accepted:** gain +0.070, and the worst episode improved rather than dropped.
- **Finding: v1 is built on a wrong belief, and the gate accepted it anyway.**
  - **What the Meta LLM wrote:** its rewritten `knowledge` prompt says the player
    is "the 2-row lime bar at the bottom (rows 61-62)" and the goal is to "collect
    all maroon items". `player_position()` looks for lime cells.
  - **Why it's wrong:** the lime bar is most likely ls20's action counter, which
    turns lime to green on every action. That would also explain #8's
    ACTION2 "lime→green" rule with support 398. The mover is the teal block, which
    #8's analysis tracks and the pilot player found on turn 1.
  - **The players believed it:** their notes call the lime bar the player in 7,
    18 and 53 turns of the three episodes, and none mentions teal.
    `player_position` got 75–118 calls per episode.
  - **Why the score rose anyway:** the error didn't change what they did. They
    aimed at the maroon block at rows 11–13, which is near the real target, and
    pressed ACTION1 to "raise the bar", which raises the real mover.
  - **The lesson:** Validate checks mechanics only (does it apply, run, replay).
    It cannot tell a true claim about the game from a false one, so only the gate
    stands in the way, and at n=3 the gate scores outcomes, not understanding.
    This goes in the report's failure modes.

### 2026-11-01 — Rounds 2–3; the progress term measures the wrong object

- **Round 2 (v2):**
  - Edits: a rule-based delete of `bfs_to_target` (unused for 6 episodes), a Meta
    rewrite of `knowledge` (refining the lime-bar belief), and a Meta add of
    `plan_route`.
  - Scores 0.474 ×3, so mean and worst are both 0.474. **Accepted** (+0.070).
- **Round 3:**
  - **Validate:** dropped the Meta rewrite of `plan_route`, which was a genuine
    bug (`len(c)` on an int raises `TypeError`). It passed the one `knowledge`
    edit.
  - **Network:** one connection to `three.arcprize.org` was refused at 19:58:29
    during Validate. `arc_agi` then loads the locally cached ls20, which is the
    same game file, so nothing was affected.
- **Finding: the 0.474 plateau is "touched the rotator", not "nearly at the goal".**
  - **How I checked:** I replayed every finished episode through `EpisodeAPI` and
    read ls20's internal state after each action. This was analysis only;
    nothing from the game's code goes into any harness. The script is
    `ls20_state_trace.py` in the session scratchpad.
  - **ls20's win condition (`pbznecvnfr`):** the player sprite must stand on the
    goal sprite *and* match its required shape, colour and rotation.
    - Level 1's goal is at (row 10, col 34): the grey box at the top with the
      maroon pattern.
    - The player starts with rotation index 3, and the goal needs 0.
    - The blue/black object near (32, 21) changes rotation when bumped. That is
      the object #8's `analysis/approach.py` calls "the target".
  - **So my gate's progress term measures distance to the rotator.** It reuses
    #8's metric (`1 − closest/28.5`), which saturates at 0.947 when the player
    touches the rotator. That gives score 0.474.
  - **What the players actually did** (12 finished episodes):
    - 8 reached the correct rotation at least once (3 → 0), often late, around
      action 180 of 200;
    - **none** spent a single action on the goal square.
  - **Whose mistake:** the user agreed to "0.5 · (progress toward the goal)" in
    the gate question. The error is in my implementation of "the goal": I took
    #8's "target" object without checking it against the game's rules.
    (Corrected: an earlier version of this entry wrongly called the formula
    my own assumption.)
- **Decision:** let the run finish under the metric it started with. Changing it
  now would make the gate decisions already taken incomparable with later ones.
  Afterwards, re-score every saved episode against the true goal (deterministic
  replay makes this exact) and report both, with the second clearly labelled as
  computed afterwards.
- **Follow-up: `analysis/ls20_subgoals.py`** (post hoc, not used by the gate).
  - **What it does:** replays each saved episode and reports the two real
    sub-goals separately: whether the player got the goal's rotation, and how
    close it got to the goal square, overall and while correctly rotated. It
    also draws `real_goal_by_version.png`. I chose not to invent a composite
    score after seeing the results.
  - **Rounds 0–3 (12 episodes):**
    - 8 episodes reached the right rotation;
    - none ever stood on the goal;
    - 5 got within 5 cells of it (one move), all with the wrong rotation;
    - when correctly rotated, the closest any episode came was 15.
- **Why "one move away" and still stuck: the goal is a wall to a wrongly rotated
  player.**
  - **Test:** from the start, press ACTION1 repeatedly. Six presses move the
    player to (34, 15). The seventh changes nothing (`n_changed=0`).
  - **What the players saw:** the goal looks like an obstacle. They found it,
    were blocked, read it as a wall, and never linked "blocked here" to "change
    state first". When they did rotate, mostly late and by bumping the switch
    while wandering, none went back.
  - **The gate's metric points the wrong way here:** v0 ep2 and v1 ep2 came
    within one move of the goal, yet scored 0.439 and 0.263 because they were
    far from the switch.

### 2026-11-01 — Round 3 rejected; round 4 interrupted (machine low on memory)

- **Round 3:** v3 scored 0.439, 0.474, 0.474, so mean 0.462. **Rejected**
  (gain −0.012); v2 stays the parent.
- **Round 4:**
  - **Edits:** the Meta LLM proposed 3. Two passed: add `verify_move`, and a
    `knowledge` rewrite that now wrongly claims moves are 1 cell, not 5. The
    third, deleting `plan_route`, was dropped because v2's episodes call it and
    replay diverges at turn 0.
  - **Play:** v4's players took about 1 action per turn (earlier versions: about
    3), so they will likely hit the 200-turn or 90-minute cap before 200 actions.
- **Interrupted at about 21:05:** Claude Code stopped the run's background shell
  because the machine was critically low on memory. Free RAM was 2.2 / 15.7 GB
  afterwards, and no single process stood out. v4's episodes were at turns 81–86
  (59–86 actions); none had finished. No run process was left behind.
- **State on disk:**
  - Rounds 0–3 are complete in `archive.json`.
  - For round 4, `analysis.json`, `validation.json` and `harnesses/v4/` are
    saved.
- **Resuming** (`--rounds 5`) reuses all of that, including the Meta LLM's
  edits, and restarts v4's 3 episodes from scratch. Their trajectory files are
  opened with `"w"`, so partial lines are overwritten, not mixed in. About 255
  turns, roughly 1.2M tokens, of v4 play are lost.
- **Next step:** waiting for the user to restart; I don't restart after a
  memory stop on my own.

## Open questions / risks

- **3 episodes are 3 samples of one level.** Gate decisions on n=3 are noisy; a lucky
  sample can get a child accepted. Reported per episode, not only as means.
- **The sandbox guards against accidents, not adversaries.** A restricted `exec` with
  an AST filter is not a security boundary against a determined attacker. The threat
  model here is a 27B model playing a game; this is noted, not solved.
- **The progress term uses ls20-specific colour roles** (mover = teal, target =
  blue/black, from #8's `analysis/approach.py`). The player never sees it; only the
  gate uses it. It is evaluation knowledge, not harness knowledge.

## Summary (fill in at the end)
