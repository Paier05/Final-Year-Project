# Work Log — Issue #12: Follow up issue #9 on improving gates, selection and more episodes

**Issue:** https://github.com/Paier05/Final-Year-Project/issues/12
**Branch:** `experiment/12-evo-harness-v2-ls20`
**Started:** 2026-11-02 11:50

## Understanding the issue

#9 ran 5 rounds of the evo-harness loop on ls20 Level 1 and found the loop
mechanically sound but pointed at the wrong thing (REPORT-9-architecture.md):
its score measured distance to the rotation switch, Validate could not tell a
true game fact from a false one, promotion never fired, and the gate (n=3, no
cost) tied or rewarded noise. #12 re-runs the loop with four fixes and a new
model, `qwen38-flash-next-autoround`, for both the player and the Meta LLM:

1. **Goal-progress score.** Deterministic, from game state: how close each
   episode got to *clearing* Level 1, combining every condition the game checks
   (position and rotation, plus shape and colour). Clear = 1.0. Per version =
   mean over 5 episodes. Analyze gets the parts, so it can say "right position,
   wrong rotation". #9's trajectories are rescored on the same scale.
2. **Fact-check in Validate.** Claims about the game in each edit (skills,
   prompts, knowledge) are tested against the env. false → drop the edit;
   unverifiable → keep it and flag it in the CHANGELOG. #9's checks stay.
3. **Lower promotion thresholds:** `promote_min_episodes` 2 → 1,
   `promote_min_calls` 6 → 2.
4. **Cost-aware gate, 5 seeded parallel episodes.** Seeds 1–5 for every
   version; cost (tokens, LLM calls, env steps, wall time) logged per episode;
   gate score = progress − λ·cost with λ = 0.5; cost tie-break; unused-skill
   delete threshold 6 → 10 episodes.

Then 5 rounds, and a report with pictures posted on the issue.

### What ls20 Level 1 actually checks (read from the game source and probed)

`environment_files/ls20/9607627b/ls20.py`, `bejndxqqzf` + `pbznecvnfr`: the
level clears when the player sprite's top-left equals the goal's **and** the
player's shape, colour and rotation indices equal the goal's.

| | start | goal | changed by |
|---|---|---|---|
| position (sprite top-left x, y) | (34, 45) | (34, 10) | ACTION1–4: 5 cells up/down/left/right |
| rotation index | 3 | 0 | stepping on the switch at x=19, y=30 (+1 mod 4) |
| shape index | 5 | 5 | no shape switch on Level 1 |
| colour index | 1 | 1 | no colour switch on Level 1 |

- The maze has 37 reachable squares. By BFS: start → goal is 7 moves,
  start → switch is 6, switch → goal is 7. **Optimal clear: 13 moves** (human
  baseline 22).
- If the rotation is wrong, the goal blocks the player. Walking straight up to
  the square under the goal still leaves 13 moves to go.
- On screen: the player is a 5×5 block, 2 rows teal over 3 rows maroon; the
  goal is the grey box with a maroon pattern at rows 10–14, cols 34–38; the
  lime bar at rows 61–62 counts down 42 moves per life; the three cyan blocks
  at the bottom right are the lives; floor is green, walls are yellow (the
  background).

### Facts checked before planning (2026-11-02)

- **The seeds do not change anything.** The ls20 frames are identical for
  seeds 0–5 over 16 actions (as #9 found for 0–2). The endpoint **ignores the
  sampling `seed`**: two calls with seed=1 at temperature 1.0 gave different
  text. So "seed S" names the S-th attempt; it doesn't fix a start state or a
  sample. Seeds are still passed to the env and the API, and recorded.
- **Parallel episodes share no state.** Every #9 episode (played 3 at a time)
  replays alone with 0 divergent turns (`reports/round_*/validation.json`
  fidelity).
- The model is listed as `qwen38-flash-next-autoround`. `enable_thinking: false`
  works (0 reasoning tokens), and short calls take about 1 s.

### Decisions (asked and answered by the user, 2026-11-02)

| Question | Answer |
|---|---|
| Tie-break ε (the issue says 0.5; scores are in [0, 1], and with 0.5 nearly every comparison would be a tie) | **ε = 0.05** |
| How cost is normalised to 0–1 | **mean of tokens / 1.2M, LLM calls / 200, env steps / 200** (the per-episode caps). Wall time is recorded but not penalised. |
| Goal-progress weights | **position 0.4, rotation 0.4, shape 0.1, colour 0.1** |
| What the Meta LLM is told when the fact-check drops an edit | **only that the claim is false**, not the true value. Full evidence goes to the CHANGELOG and archive. |

My question's preview had one wrong number: "rotated, 3 moves from goal" is
0.6 + 0.4·(4/7) = **0.83**, not 0.77. The ordering it showed is unchanged.

### Assumptions (small, logged rather than asked)

1. **Base branch is #9's branch** (`experiment/9-evo-harness-ls20`), not
   `main`. #12 changes #9's code, and PR #11 is not merged yet. The PR targets
   #9's branch so its diff is only #12's changes.
2. **`config_evolve.yaml` is edited in place**, as the issue says. #9's values
   remain in git history and in `results/evolve/archive.json`'s `config`.
   Output goes to a new root, `results/evolve_12/`, so #9's results are never
   touched.
3. **How the score works.** Every state gets a joint score, Σ wᵢ·partᵢ, and the
   episode scores its *best* state. Rotation, shape and colour are binary
   matches. Position = max(0, 1 − maze_moves_to_goal / 7). Taking the best
   joint state rewards "rotated *and* near the goal at the same time", which
   #9's players never managed. A per-part max would credit rotating at one time
   and being near at another.
4. **Gate.** For each episode, g = progress − 0.5·cost. If the two versions'
   mean progress differs by more than 0.05: accept iff mean-g gain > 0 and
   worst-g drop ≤ δ = 0.1 (δ unchanged). If it differs by 0.05 or less: accept
   iff the child's mean cost is lower and drop ≤ δ.
5. **Game state is logged in the trajectory.** After every action the record
   gets `game_state` (player x/y, rotation, shape, colour; the goal's
   requirements; moves and lives left), read from the env. The score is
   computed from it. The player's API never exposes it. #9's trajectories carry
   no state, so they are rescored by deterministic replay of their logged
   actions.
6. **Fact-check = extraction by the LLM, checking in code.** One extra
   meta-model call per attempt turns each edit's text into claims from a fixed,
   checkable vocabulary: what an action does, which colour is which role,
   where things are, what rotates the player, what the goal requires, counts,
   and what a skill returns. Deterministic code checks each claim against facts
   probed from the env and the logged states. Anything outside the vocabulary
   is `unverifiable`. The model never judges truth.
7. **Analyze shows goal parts.** The issue asks for it. It means the Meta LLM
   learns that the goal has a rotation condition, which #9 deliberately hid.
   Coordinates of the goal are not passed.

## Plan

1. Preconditions, branch, this log. ✅
2. **Goal-progress score** (`evolve/goal_score.py`): ls20 state probe, maze BFS,
   per-state parts, episode score from logged states, replay-based states for
   old trajectories. Log `game_state` per action in `action_loop.py`.
3. **Cost + seeds + gate** (`evolve/score.py`, `evolve/action_loop.py`,
   `evolve/loop.py`): LLM-call count and cost fields per turn and per episode,
   `seed_S.jsonl` paths, seeds 1–5 in parallel, normalised cost, gate with
   λ/ε/δ, archive and CHANGELOG fields.
4. **Fact-check** (`evolve/factcheck.py`, wired into `evolve/validate.py`):
   ground truth from the env, claim extraction, checker, drop/flag, redacted
   feedback for the Meta LLM.
5. **Analyze + Propose**: goal parts in the report; Meta prompt describes the
   new score, gate and fact-check; config changes (model, thresholds, delete
   rule).
6. **Self-tests**, offline: score on hand-built states, gate cases, the
   fact-check against #9's known-false claims (lime-bar player, 1-cell moves,
   collect maroon) and known-true ones (ACTION1 = up 5), and parallel env
   isolation. Plus a stub end-to-end run.
7. **Rescore #9** with the new score (`analysis/rescore_9.py`).
8. **Pilot**: one real episode on the new model, for cost and to check that
   logged states match replay.
9. **The run**: round 0 + 5 rounds, 5 parallel episodes each.
10. **Figures + report**: the six pictures and every table the issue lists,
    posted as one issue comment; then the PR.

## Progress log

### 2026-11-02 ~12:00 — Goal-progress score and state logging (change 1)

- **What I did:**
  - Wrote `evolve/goal_score.py`: reads ls20's state (player x/y; rotation,
    shape and colour indices; the goal's requirements; lives; moves left),
    builds the Level-1 maze from the wall sprites, and scores each state.
  - `EpisodeAPI` takes an optional `probe` and writes `game_state` into every
    action's trajectory record. The sandbox API doesn't expose it, so the
    player never sees it.
  - Trajectories are now `seed_S.jsonl`, and each turn records `llm_calls`,
    `env_steps` and `wall_time_s`.
- **Result:**
  - The self-test reproduces the ladder agreed with the user: start 0.200,
    under the goal unrotated 0.543, rotated at the switch 0.600, rotated
    under the goal 0.943, clear 1.000.
  - It also checks that "rotated at one time, near the goal at another"
    scores only the better single state, not a mix.
  - On a stub episode the logged states equal the replay-rebuilt states
    exactly (41/41). That match is what makes rescoring #9 by replay
    legitimate.

### 2026-11-02 ~12:30 — Fact-check (change 2), tested on #9's own edits

- **What I did:**
  - Wrote `evolve/factcheck.py`. Ground truth is probed from the env:
    - each action's effect on the player sprite;
    - each colour's role, found from the sprites, plus two probes: a move
      shows which cells the counter uses, and losing a life shows which are
      the lives;
    - where the player, goal, switch, counter and lives are;
    - lives = 3, moves per life = 42.
  - One meta-model call per Validate attempt extracts claims into a fixed
    vocabulary; code checks them.
  - Wired it into `validate.py` as a 6th check, after the skill test.
- **Dead end, fixed:** the first role table said yellow, grey, maroon and
  green are all walls. Some wall sprites sit under the HUD box, so their
  bounding boxes picked up its colours. The wall colour is now the most common
  colour over all wall squares (yellow). The background colour is no longer
  counted as "UI".
- **Test on real data:** I ran the real extractor (`qwen38-flash-next-autoround`,
  1 call, 6.4k tokens) on #9's 11 accepted edits. Labelled false, all
  correctly:
  - "Player: 2-row lime bar at the bottom (rows 61-62)" (twice: as a colour
    and as a location);
  - `player_position()`: running it on replayed states returned the lime bar,
    not the player;
  - "Moves 1 cell per action" and "ACTION1 = move up 1 cell" (×4);
  - "Maroon = collectible items", "Goal: collect all maroon items";
  - "Cyan = deadly obstacles", "Green = trail", "Green can block movement".

  "ACTION1–4 = move 5 cells" came out true. So with this check, all three
  of #9's round-1 edits (the source of the lime-bar belief) would have been
  dropped.
- **One miss, fixed:** "The maroon items are located at rows 11-13, …" was
  mapped by the extractor to the *goal's* location and passed, because rows
  11–13 are the goal's pattern. The vocabulary now has `collectible` and
  `other` as location objects. A `collectible` location is false on Level 1,
  since nothing on it is collected.

### 2026-11-02 ~13:00 — Gate, seeds, config, Analyze, Propose; offline tests pass

- **What I did:**
  - `score.py` now computes cost and gate score, and gates with λ/ε/δ.
  - `loop.py`:
    - seeds 1–5 run in parallel, each with its own env, sandbox and client;
    - archive fields: seed, goal parts, cost, fact-check;
    - the CHANGELOG flags UNVERIFIABLE claims;
    - the Meta LLM's feedback carries only the false claim.
  - Config: model switch, thresholds, delete after 10 episodes, root
    `results/evolve_12`.
  - Analyze reports goal parts and failures.
  - The Meta prompt describes the new score, gate and fact-check.
  - Added a stub claim extractor and extended the self-test.
- **Result:**
  - `python -m evolve.selftest`: **73 checks pass**. They cover the score,
    6 gate cases (incl. both tie-break branches), 23 hand-written claims (11
    of them #9's false beliefs), a skill that finds the player by lime
    (false) vs by teal (true), 3 envs stepped in parallel = serial, and the
    fact-check stage inside Validate.
  - The Meta-facing reason names the false claim and not the true value:
    `contradicted by the game: 'ACTION1 moves the player up 1 cell'`.
  - Stub run, 2 rounds, 1.5 min:
    - round 1 promoted the stub's helper under the new thresholds;
    - round 2 deleted v0's 3 never-called skills at 10 episodes;
    - the fact-check dropped the stub's "1 cell" edit and flagged its
      strategy line UNVERIFIABLE in the CHANGELOG;
    - both gates went through the tie-break.
- **Risk found in the stub run:** a tie-break decides on *any* cost
  difference. v2 was accepted for being cheaper by 0.0006. With real episodes,
  cost differences of that size are noise (turn counts vary), so near-ties on
  progress become coin flips on cost noise. This follows from the rule as
  agreed; I am noting it, not changing it.

### 2026-11-02 ~13:05 — #9 rescored; figures; pilot started

- **#9 on #12's scale** (`results/evolve_12/rescored_9.json`, replay-rebuilt
  states):

  | #9 version | #9 decision | #9 score | #12 progress (mean ± SD) | rotated | cost |
  |---|---|---|---|---|---|
  | v0 | baseline | 0.333 | 0.467 ± 0.150 | 1/3 | 0.545 |
  | v1 | accepted | 0.404 | 0.676 ± 0.117 | 2/3 | 0.517 |
  | v2 | accepted | 0.474 | **0.714 ± 0.081** | 3/3 | 0.546 |
  | v3 | rejected | 0.462 | 0.581 ± 0.108 | 2/3 | 0.494 |
  | v4 | rejected | 0.474 | 0.676 ± 0.027 | 3/3 | 0.852 |
  | v5 | rejected | 0.474 | 0.657 ± 0.000 | 3/3 | 0.521 |

  - v2 is still #9's best.
  - Its gain was real progress on *rotation*: every episode bumped the
    switch.
  - Closest any #9 episode got to the goal **while rotated**: 3 moves.
  - The 14/18 "rotated" count matches #9's post-hoc `subgoals.json`.
  - v4 (the `verify_move` version) has the highest cost by far (0.852):
    under #12's gate it would lose even before the tie-break.
- **Figures:** `analysis/evolution12.py`, rendered from the stub archive and
  looked at. Three layout fixes:
  - version labels on the cost scatter overlapped → fanned out;
  - the rejected-edge label sat on its arrow in the lineage → moved under the
    node;
  - "g=-0.0" → "g=0.0".
  - Palette: #8's slots 1–4, validated with the dataviz script (all hard
    checks pass; aqua and yellow are below 3:1, so the charts carry direct
    labels and the report has tables).
- **Pilot started** (seed 1, v0, `data/evolve12_pilot/`):
  - turns take 6–23 s with 3–6k tokens in, about 2× my 1 s probe calls,
    because real prompts are 5k tokens;
  - the player found within 10 turns that the teal/maroon block moves 5 cells.

### 2026-11-02 13:14 — Pilot cut short at 14 turns; full run launched; round 0 doubles as the pilot

- **Pilot, 14 turns** (`data/evolve12_pilot/`, not part of the experiment):
  - per turn: 3–6k tokens in, 180–720 out, 6.5–23 s;
  - no parse failures, no cell errors;
  - **turn 10 took 201.7 s**, but its successful call took 19.6 s. One
    request hung until the 180 s client timeout and the retry succeeded.
    The endpoint occasionally hangs.
  - `llm_calls` counts the harness's calls (format retries included), not the
    client's network retries, and wall time includes the hang.
- **Estimate:** ~6k tokens per turn. At #9's ~140 turns per episode that is
  ~0.8M per episode, so ~25M for 30 episodes (worst case 36M at the
  per-episode cap; global cap 40M). Time: ~17 s per turn, ~40–50 min per
  round, if 5 parallel episodes don't slow the endpoint.
- **Why I stopped the pilot instead of finishing it:** finishing would cost
  ~35 more minutes. Round 0 is 5 v0 episodes with the same code, so it
  answers the same questions 5 times over, and the run can be stopped after
  round 0 if the cost is off.
  - The one path no test had covered (life loss → game over → harness
    auto-reset) I tested offline first: a 200-action stub episode lost all 3
    lives, auto-reset once, and its logged states equal the replayed ones
    (202/202).
- **Memory:** 0.7 GB free of 15.7 GB at launch (Chrome 8.8 GB, Claude Code
  1.8 GB, VS Code 1.2 GB). In #9, Claude Code's low-memory guard killed the
  run's background shell. This run is therefore launched **detached**
  (`Start-Process`, PID 1800), not as a child of this session.
  - Log: `data/evolve12_run.log` (+ `.err`).
  - The loop resumes from saved state if it is stopped anyway.
- **Launched 13:14:14:** `python evolve_run.py --rounds 5`, preflight OK for
  both roles.

### 2026-11-02 14:55 — First attempt stopped after round 0: wall-clock cuts; two fact-check bugs; restarted

- **Round 0 of the first attempt** (kept in `data/evolve12_aborted_90min/`,
  not part of the results): v0 mean progress 0.589 ± 0.056, cost 0.640,
  0/5 clears.
  - 3 episodes reached the square under the goal with the wrong rotation;
  - 2 rotated, but their best state was 6 moves from the goal;
  - #9's failure, again.
- **Problem: 4 of 5 episodes ended on the 90-min wall clock**, at 123–136 of
  200 actions. With 5 episodes in parallel the endpoint gave ~38 s per turn
  (17 s alone). #9 had this cut once in 18 episodes; here it decided almost
  every episode's length, so scores and cost partly measured server speed —
  the risk #9's pilot entry named.
  - I asked; the user chose to **raise the cap to 4 h and restart from
    round 0**, so the action / turn / token budgets end episodes, as in #9.
  - This discards ~3.4M tokens of round-0 play and makes the run longer
    (~2.5 h per round).
- **Round 1 of the first attempt** (Analyze → Propose → Validate ran before
  the stop; no v1 episodes were played) exposed **two fact-check bugs**
  the offline tests had not:
  1. The real extractor nested every claim's fields under `"fields"`, so all
     5 move claims came out unverifiable ("no direction or size stated").
     My prompt's `...fields` placeholder invited it. Fixed by flattening
     `fields` before checking and putting a concrete flat example in the
     prompt. The earlier test on #9's edits had extracted flat claims, so
     this is model variance, not a one-off.
  2. Colours written as indices in code (`o['colour'] in (0, 1)`) were not
     mapped to names. That let a **promoted player helper `find_player()`,
     which takes black/blue (the rotation switch) for the player**, pass as
     unverifiable. Fixed: indices and "name(index)" are read as names.
     - Re-checked offline with the stored claims: the knowledge prompt's
       5-cell moves → true, `find_player` → **false** (it would now be
       dropped).
     - This is the risk the issue names for lower promotion thresholds
       ("one-off helpers may get promoted"), caught by the check the issue
       added for it.
  - 3 self-test cases added; all pass.
- Also seen in that round:
  - promotion fired, with 3 rule-based adds (`find`, `find_blue`,
    `find_player`) at the new thresholds;
  - the Meta LLM's analysis names the right failure ("fails to align
    rotation and position simultaneously");
  - one Meta skill was dropped by its own failing test.
- **Restarted 14:55:25** (PID 20860, detached), 1.0 GB RAM free. The monitor
  now keeps its read position in a file, so lines logged between re-arms
  are no longer skipped (the first attempt's monitor missed seeds 1–3 that
  way).

### 2026-11-02 17:05 — Round 0 done; run paused before round 1 at the user's request

- **User's instruction (~15:50):** stop after round 0; they will resume rounds
  1–5 later with the computer on. I armed a stopper to kill the run once
  round 0 was saved, before round 1 makes any model call.
- **The run's stdout log stopped receiving lines at 16:37**, while the run
  itself went on.
  - A `py-spy dump` of the live process showed nothing blocked: seeds 1–4's
    threads had returned, seed 5 was in a model call, the main thread was
    waiting for it. Their scores were in `episodes.json`; only their log
    lines never reached the redirected file. I did not find the cause.
  - Consequence: the first stopper watched that log for "round 1:" and could
    have missed it. I replaced it with a detached one watching for
    `archive.json`, which the loop writes once v0 is saved and before round
    1's first model call.
  - For the resume, `evolve_run.py` now also appends every progress line to
    `data/evolve_12_events.log`, opened and closed per write (stub-tested).
- **Seed 5 was slow** (66 turns in 75 min vs ~115 for the others). Not the
  server singling it out: every seed got ~14 output tokens/s. Seed 5 wrote
  ~805 output tokens per turn vs ~430, some hitting the 1,500 cap, and had 4
  hung calls (~3.5 min each) vs 1–2.
- **Stopped at 17:04:56**, right after round 0 was saved. Round 1 had written
  only its deterministic `analysis.json`, which the resume reuses; no model
  call was made.
- **Round 0 (v0 = baseline of this run):**

  | seed | progress | best state | rotated | ended on | actions | turns | tokens | cost |
  |---|---|---|---|---|---|---|---|---|
  | 1 | 0.429 | 3 moves from goal | no | 200 actions | 200 | 159 | 879k | 0.866 |
  | 2 | 0.543 | 1 move, wrong rotation | no | token cap | 128 | 185 | 1,208k | 0.880 |
  | 3 | 0.543 | 1 move, wrong rotation | no | token cap | 174 | 185 | 1,201k | 0.957 |
  | 4 | 0.543 | 1 move, wrong rotation | no | turn cap | 184 | 200 | 1,154k | 0.961 |
  | 5 | 0.543 | 1 move, wrong rotation | no | 200 actions | 200 | 158 | 897k | 0.856 |

  - Mean progress **0.520 ± 0.046**, cost 0.904, gate score 0.068, 0/5
    clears, **0/5 rotated**.
  - 5.34M tokens for the round; LLM calls exceed turns (164–234) because of
    10–20 format retries per episode.
  - With the 4 h cap no episode ended on wall clock: each ended on actions,
    turns or tokens, as intended.
  - #9's failure, more uniformly: walk to the goal, get blocked, never look
    for the switch. The first attempt's v0 rotated in 2/5, so 0/5 here is
    within sampling noise at n=5.
- **Projection for rounds 1–5:** ~5.3M tokens and ~2–2.5 h per round, so
  ~27M more tokens, ~32M total (cap 40M), and ~11–13 h.
- **To resume:** `.venv\Scripts\python.exe evolve_run.py --rounds 5`.

### 2026-11-02 18:10–21:12 — Resumed; round 1 done (v1 accepted on the cost tie-break); paused in round 2

- **Resumed 18:10** (user: "resume"), detached, PID 31324. 4.1 GB RAM free.
  Progress lines went to `data/evolve_12_events.log` as intended, and the
  monitor read them there.
- **Round 1, Validate** (7 proposed: 3 rule, 4 Meta; 4 passed):

  | edit | source | result |
  |---|---|---|
  | promote helper `find` | rule | dropped: replay diverges (episode 1, turn 158) |
  | promote helper `block_info` | rule | passed; 3 claims unverifiable |
  | promote helper `teal_centroid` | rule | passed; 2 claims unverifiable |
  | rewrite `knowledge` | Meta | **dropped, fact-check**: "the goal is … near the blue(1)/black(0) sprite at rows 31-33, cols 20-22" (the rotation switch) |
  | add skill `move_cluster_to` | Meta | passed; 6/6 claims true |
  | edit step 4 | Meta | passed |
  | edit step 1 | Meta | **dropped, fact-check**: "target location (grey box or blue/black sprite)" |

  - Fact-check, round 1: 33 claims, 21 true, 5 false, 7 unverifiable; 2
    edits dropped for a false claim.
  - The false belief it stopped (the switch is the target) is #9's own
    scoring error, now coming from the Meta LLM.
- **Round 1, v1's episodes:**

  | seed | progress | best state | cost | ended on |
  |---|---|---|---|---|
  | 1 | 0.543 | 1 move, wrong rotation | 0.975 | 200 actions |
  | 2 | 0.543 | 1 move, wrong rotation | 0.764 | 200 actions |
  | 3 | 0.257 | 6 moves, wrong rotation | 0.692 | 200 actions |
  | 4 | 0.543 | 1 move, wrong rotation | 0.755 | 200 actions |
  | 5 | 0.600 | **rotated**, on the switch (7 moves) | 0.782 | 200 actions |

  - Mean progress 0.497 ± 0.122, cost 0.794, gate score 0.100.
  - Every episode used its 200 actions.
  - Skill calls: `grid_region` 178, the promoted **`teal_centroid` 90**,
    `move_cluster_to` 15, `block_info` 0.
  - So one promoted helper was reused heavily and the other never.
- **Gate: v1 accepted on the tie-break.**
  - Progress −0.023 (within ε = 0.05), cost **−0.110**, worst-episode drop
    +0.085 (≤ δ = 0.1).
  - The rule as agreed: equal progress within ε, the cheaper version wins.
    Here the cost difference (12%) is well above per-episode noise.
  - The progress difference is noise at n=5 (SD 0.12).
- **Round 2, Validate** (5 proposed: 1 rule, 4 Meta; 3 passed):
  - **passed:** the rule-based delete of `bfs_to_target` (unused for 10
    episodes, the raised threshold's first firing); a Meta edit of step 4;
    a Meta `knowledge` rewrite (4 claims true, 1 unverifiable);
  - **dropped:** Meta skill `detect_orientation` (its own test raised
    IndexError on the start state) and Meta skill `rotate_cluster`
    (NameError: it calls the dropped `detect_orientation`).
  - The Meta LLM is now aiming at rotation, plausibly because Analyze reports
    "rotation WRONG" per episode, but neither tool survived the mechanical
    checks.
- **Paused 21:12 at the user's request** ("can stop for now and i will resume
  later"), during v2's evaluation:
  - v2's 5 episodes were at 58–71 turns, about 1.8M tokens of play that
    resume will redo; their trajectory files are reopened with "w";
  - saved and reused on resume: archive (v0, v1), `harnesses/v2`,
    `reports/round_2/{analysis,proposals,validation}.json`, so no Meta or
    fact-check call is repeated.
- **Tokens so far:** player 9.26M in counted episodes (v0 5.34M, v1 3.92M),
  plus Meta + fact-check ~21k. Not counted: the first attempt (~3.4M) and the
  two cut-short evaluations (~1.8M + v2's ~1.8M).

### 2026-11-02 22:27 – 2026-11-03 01:33 — Round 2 done (v2 accepted on cost again); paused in round 3

- **Resumed 22:27** (user: "can resume now"), PID 5476. Round 2 reused its
  saved analysis and Validate (no Meta call repeated) and replayed v2's 5
  episodes from the start.
  - Detail: v1's players wrote **0** inline helpers (v0's wrote 28 groups).
    They used the skills they were given instead (283 calls).
- **Round 2, v2's episodes:**

  | seed | progress | best state | cost | ended on |
  |---|---|---|---|---|
  | 1 | 0.543 | 1 move, wrong rotation | 0.690 | 200 actions |
  | 2 | 0.600 | **rotated** (action 54), on the switch | 0.865 | 200 turns |
  | 3 | 0.543 | 1 move, wrong rotation | 0.583 | 200 actions (75 turns) |
  | 4 | 0.257 | 6 moves, wrong rotation | 0.750 | 200 actions |
  | 5 | 0.657 | **rotated**, best 6 moves from goal | 0.785 | 200 actions |

  - Mean 0.520 ± 0.138, cost 0.735, gate score 0.153.
  - Skill calls: `grid_region` 437, `teal_centroid` 191, `move_cluster_to` 1,
    `block_info` 0.
- **Gate: v2 accepted on the tie-break** (progress +0.023 within ε, cost
  −0.059, drop +0.029).
- **The pattern so far:**

  | version | progress | cost | gate score |
  |---|---|---|---|
  | v0 | 0.520 | 0.904 | 0.068 |
  | v1 | 0.497 | 0.794 | 0.100 |
  | v2 | 0.520 | 0.735 | 0.153 |

  - Both acceptances came from cost. Progress has not moved beyond noise.
  - The cost-aware gate rewards reaching the same state more cheaply, but it
    does not by itself push toward "rotate, then go to the goal".
- **Round 3, Validate** (6 proposed: 2 rule, 4 Meta; 4 passed → v3):
  - passed: rule promotion of `get_cluster_centroid`; **rule delete of
    `block_info`**; Meta edit of step 4; Meta `knowledge` rewrite (5 true, 1
    unverifiable);
  - dropped: Meta `analyze_cluster_state`, **by the fact-check**, for
    "target: the nearest cyan(8) or grey(5)" (cyan is the lives display);
    Meta `try_rotate`, by the sandbox rules (bare `except:`).
  - The `block_info` delete is the issue's safeguard for one-off promotions
    working as designed: promoted in round 1 at the lowered threshold, never
    called in v1's or v2's 10 episodes, removed at the raised 10-episode
    delete rule.
- **Finding: a wrong helper got promoted, and the fact-check could not see
  it.**
  - `get_cluster_centroid(g, colors=[12, 9])` averages every teal *and maroon*
    cell. Maroon is also in the HUD box and the goal's pattern (only 15 of 45
    maroon cells are the player's).
  - Run on 4 recorded states, it returned (47.6, 22.6), (40.8, 24.8),
    (40.8, 22.6) and (34.3, 22.9) while the player was at cols 34–43. Its
    column stays near 22–25 wherever the player is. `teal_centroid` matched
    the player at all 4 states.
  - It got through because:
    1. promotion needs 1 episode or 2 calls now (it had 1 and 4);
    2. replay rightly finds it identical to the player's own copy;
    3. the extractor described its claims as "teal/maroon have role other"
       (unverifiable);
    4. the `skill_output` check calls skills with no arguments, and this one
       needs `g`, so it could not run.
  - Recommended follow-up fix (not applied mid-run, so rounds 1–5 are
    validated the same way): retry a skill with `grid()` as its argument when
    the no-argument call fails, and have the extractor emit a
    "returns the player position" claim for any locate-the-player helper.
  - Also: `teal_centroid`'s claims came out unverifiable too, though it is
    correct. "Unverifiable" here often means "the extractor was vague", not
    "doubtful".
- **Paused 01:33 at the user's request** during v3's evaluation:
  - seeds were at 78–97 turns; seeds 1 and 2 had rotated (at actions 43 and
    92); no v3 episode had finished;
  - all 5 replay on resume (~2.3M tokens of play redone); the partial
    trajectories are copied to `data/evolve12_partial_round3/` for reference;
  - saved and reused: archive (v0–v2), `harnesses/v3`,
    `reports/round_3/{analysis,proposals,validation}.json`.
- **Tokens:** player 12.84M in counted episodes; Meta + fact-check ~41k.

### 2026-11-03 09:09–16:20 — Resumed; rounds 3–5 done; run complete

- **Resumed 09:09** (user: "resume"), PID 14748. v3's 5 episodes replayed
  from scratch. Last night's cut sample had 2 early rotations; this one had
  none early. That's n=5 sampling noise in plain view.
- **Round 3 → v3 accepted on gate score** (the first acceptance on progress):
  - progress 0.589 vs 0.520 (+0.069, beyond ε);
  - cost 0.834 vs 0.735 (+0.099);
  - gate score 0.172 vs 0.153;
  - 3/5 rotated.
- **Round 4.** Validate (4 Meta edits, 3 passed):
  - the fact-check dropped a `knowledge` rewrite claiming ACTION5/7 rotates
    the player;
  - but `try_rotate`, whose docstring makes the same claim, passed as
    unverifiable, and never got called.
- **Round 4, v4's episodes:**
  - **seed 1 = 0.829**, the run's best: rotated at action 26, then at action
    33 it stood directly under the goal, rotated, with 11 counter moves left.
    It walked right instead, pressed into a wall until the counter hit 0
    (action 44), and the life loss reset the rotation;
  - the other 4 seeds stalled under the goal, unrotated.
  - **Gate: rejected.** Progress +0.011 is a tie, and v4 was not cheaper
    (+0.022). The gate judges the mean, not the best episode.
- **Round 5.** Validate (4 Meta edits, 1 passed):
  - the fact-check dropped `try_rotate_cluster` ("Try ACTION5 and ACTION7 to
    rotate the cluster", round 4's claim again, this time extracted as a
    rotation-cause claim) and a `knowledge` rewrite (ACTION5/7 rotate; cyan
    is the target);
  - its own test dropped `get_cluster_orientation`.
- **Round 5, v5's episodes:** 0.543, 0.257, 0.257, 0.714 (rotated, then 5
  moves from the goal), 0.600. Mean 0.474.
  - **Gate: rejected** (progress −0.114; gate score −0.105).
- **Final parent: v3.** The run ended normally; `archive.json` has rounds
  0–5 and no early stop.
- **While round 5 played**, I rendered the figures from the real v0–v4 data
  and fixed what they showed:
  - the replay strip now shows the move counter and the life-loss frames;
  - lineage labels no longer overlap the boxes;
  - scatter labels are placed on the clearest side;
  - overlapping seed labels were removed;
  - `|` in table cells is escaped.
  - Also added `analysis/failure_modes12.py`, which reproduces the
    failure-mode numbers from the logged states.
- **Report** posted as one issue comment
  (https://github.com/Paier05/Final-Year-Project/issues/12#issuecomment-6598830292),
  with images pinned to commit `9f4d137`. All 7 image URLs return 200. The
  same text is in `REPORT-12.md`.
  - Credential scan of `results/evolve_12/`, `analysis/`, `evolve/`, the log
    and the config: no hits.

### 2026-11-04 18:20–20:10 — Round 6 extension (user request), on Qwen3.8-27B-FP8

- **Why a different model.** The user asked for one more round to see if v6
  improves. The flash backend was down: preflight twice got HTTP 500
  "connection reset by peer" from the gateway's backend. The user chose
  `Qwen/Qwen3.8-27B-FP8` (#9's model) "for now", as player and Meta model.
- **Kept apart from the 5-round run.**
  - Config `config_evolve_round6.yaml`: identical except root, `rounds: 6`
    and the two model names.
  - Root `results/evolve_12_round6/`: `archive.json`, `CHANGELOG.md` and
    `harnesses/v0–v5` copied from `results/evolve_12/` (unchanged; v0–v5
    still point at #12's trajectories), plus a `round6_extension` note.
  - `evolve/loop.py`: each version entry now records `player_model` and
    `meta_model`, since a resumed run can switch models. Self-test passes.
  - `analysis/evolution12.py`: figure titles list any version whose model
    differs from the run's.
- **Round 6, parent v3.**
  - Analyze: 0 inline-helper groups, so the lower promotion thresholds had
    nothing to promote.
  - Propose: 0 rule edits, 4 Meta edits. Validate: 3 passed, 1 dropped. The
    fact-check dropped `find_goal` (cyan, blue, black called goal colours:
    false). It kept `check_orientation`, a rewritten step 4 (the first step
    edit in #9 or #12), and a `knowledge` rewrite (5-cell moves: true).
- **v6's episodes:** 0.543, 0.543, 0.543, 0.657, 0.543 (seeds 1–5); no clear.
  - 4/5 stalled under the goal, unrotated; seed 4 rotated but stayed far.
  - Mean progress 0.566, cost 0.642 (548k tokens per episode), gate score
    0.244.
- **Gate: accepted on the cost tie-break.** Progress −0.023 is within ε;
  cost −0.192; worst-g drop −0.106. v6 is the new parent.
- **What the acceptance does not show.**
  - v6 is not better at the game: same progress, cheaper.
  - The saving is mostly fewer turns on 4 of 5 seeds (65–133, against v3's
    109–191; seed 3 used all 200), and it
    can't be split between the model change and the edits without
    re-running v3 on 27B.
- **Two defects in the accepted text, found in the trajectories:**
  - Step 4 and `knowledge` tell the player to call `find_goal()`, the skill
    Validate dropped in the same round. Players called it in 47 cells, with
    11 NameErrors. Validate checks each edit on its own, not whether
    surviving text names a skill that no longer exists. v3's step 4 already
    named two missing skills (`analyze_cluster_state`, `try_rotate`).
  - Both say "try ACTION5 or ACTION7 to rotate"; ls20 offers ACTION1–4 only.
    Players tried ACTION5 13 times and ACTION7 5 times, and got "not
    available". The fact-check extracted no claim from this sentence or from
    the step edit, so the claim rounds 4–5 dropped got back in.
- **Tokens:** player 2.74M; Meta 26k; fact-check extraction 3k.

### 2026-11-05 15:08–17:28 — Round 7 (user request), rejected; stopped once for low memory

- **Model.** The user asked for one more round, on flash if it was back and
  on 27B if not. Flash still returned HTTP 500 from its backend (an earlier
  check failed on a connection blip, so I retried before concluding). Round 7
  ran on 27B in the same root, so **v7 vs v6 is a same-model comparison**,
  unlike v6 vs v3.
- **Redaction bug, found by that blip.** The connection error named the
  endpoint host, and `redact` only masked the full URL. The host was printed
  in this session's tool output only. `redact` now masks the host too;
  `git grep` finds it in no tracked file.
- **Round 7, parent v6.**
  - Analyze: 0 inline-helper groups again.
  - Propose: 0 rule edits, 3 Meta edits. Validate: 2 passed, 1 dropped.
  - `find_goal` was proposed again and dropped by replay (episode 1 diverges
    at turn 49).
  - `knowledge` and step 4 were rewritten. `knowledge` now says ACTION5/7 are
    not available, and suggests rotation may depend on moving elsewhere.
- **Stopped by Claude Code for low memory** with all 5 seeds unfinished
  (118–190 turns), losing ~3.15M tokens of play. I didn't restart it; the
  user said "resume now". The saved analysis, edits and v7 were reused, and
  all 5 seeds were re-run. The partial logs are in
  `data/evolve12_partial_round7/` (gitignored).
- **v7's episodes:** 0.543, 0.543, 0.257, 0.543, 0.543 (seeds 1–5); no clear.
  - Mean progress 0.486, cost 0.642 (502k tokens per episode), gate score
    0.165.
  - 0/5 episodes ever held the goal's rotation (v6: 1/5).
- **Gate: rejected.** Gate-score gain −0.080 (progress −0.080, cost −0.000),
  and the worst-g drop 0.174 is over δ too. Final parent: v6.
- **What changed in play:**
  - The ACTION5/7 fix worked: "not available" errors fell from 15 to 1.
  - The `find_goal` gap got worse: 79 cells called it, with 37 NameErrors
    (v6: 47 and 11). Text still names a skill that has now been dropped in
    two rounds running.
- **0.543 is a ceiling, not a coincidence.** 8 of the 10 v6–v7 episodes score
  exactly 0.5429: position 0.857 (just under the goal) with rotation 0. The
  goal blocks a wrongly rotated player, so that's the most an unrotated
  episode can score. Only rotating can get past it, and no accepted edit has
  taught that.
- **Tokens:** player 2.51M counted + ~3.15M lost; Meta 19k; fact-check
  extraction 2k. Counted total across v0–v7: 31.1M (cap 40M).

## Open questions / risks

- **n = 5 is still small.**
  - Per-version SD reached 0.19.
  - 3 of 5 gates fell inside ε = 0.05 and were decided on cost.
  - v1's and v2's acceptances are "same progress, cheaper", not
    improvements in play.
  - The replayed v3 (09:09) and the cut v3 sample (last night) differed
    visibly at the same turn.
- **The seeds name attempts; they don't pair them.** ls20 and the endpoint
  both ignore the seed, so "the same seeds for every version" doesn't make
  the comparison paired.
- **The fact-check depends on extraction.**
  - The same false claim was "unverifiable" in round 4 and "false" in round 5.
  - A wrong promoted helper (`get_cluster_centroid`) passed because the
    output check can't call skills that take arguments.
  - "Unverifiable" often means vaguely described, not doubtful.
- **The Meta LLM saw goal-part names** (position, rotation, …), as the issue
  asked. #9 withheld this. So #12's evolve loop ran with more evaluator
  information than #9's, which is part of the "model + harness" comparison.
- **Cost depends on server speed only through tokens and turns.** Wall time
  isn't in the cost, but a slow endpoint pushed the first attempt onto the
  wall-clock cap. The 4 h cap removed that effect from the counted run (no
  episode ended on wall clock).
- **The ε, cost normalisation, score weights and fact-check feedback** were
  chosen by the user before the run. ε differs from the issue's 0.5.
- **Unexplained:** the detached run's redirected stdout stopped receiving
  progress lines twice while the run was healthy (py-spy confirmed). Worked
  around with a separate events file; not root-caused.

## Summary

**What changed** (on top of #9's code, branch stacked on
`experiment/9-evo-harness-ls20`):

1. **Goal-progress score** (`evolve/goal_score.py`).
   - Deterministic, from ls20's state logged per action (`game_state`, not
     visible to the player).
   - Parts: position 0.4 (maze moves to the goal), rotation 0.4, shape 0.1,
     colour 0.1. An episode scores its best state; a clear = 1.0.
   - #9 rescored by replay (`analysis/rescore_9.py`).
2. **Fact-check in Validate** (`evolve/factcheck.py`).
   - One meta-model call extracts claims into a fixed vocabulary; code checks
     them against ground truth probed from the env, the logged states, and
     skills run on replayed states.
   - false → drop; unverifiable → keep and flag in the CHANGELOG. The Meta LLM
     sees only that a claim is false.
3. **Lower promotion thresholds:** ≥1 episode or ≥2 calls; delete after 10
   unused episodes.
4. **Cost-aware gate** (`evolve/score.py`): g = progress − 0.5·cost, ε = 0.05
   tie-break on cost, δ = 0.1.
   - Seeds 1–5 run in parallel, each with its own env, sandbox and client.
   - Cost and seed are recorded per turn and per episode.
5. **Config:** model `qwen38-flash-next-autoround`; wall clock 4 h (after the
   first attempt was cut by 90 min); output to `results/evolve_12/`.
6. **Report tooling:** `analysis/evolution12.py` (6 figures + GIF),
   `analysis/report12.py` (all tables), `analysis/failure_modes12.py`.

**Result** (5 rounds, 30 episodes):
- No clear.
- Lineage: v0 0.520 → v1 0.497 (tie-break) → v2 0.520 (tie-break) → v3 0.589
  (gate score); v4 0.600 rejected (tie, not cheaper); v5 0.474 rejected.
- Final parent v3.
- Best episode: v4 seed 1 at 0.829, three moves from a clear.
- The three comparisons: model change +0.053 progress / +0.359 cost; evolve
  loop +0.080; #9's best (rescored 0.714) is still above #12's best (0.600).
- Fact-check: 84 claims (50 true, 12 false, 22 unverifiable), 6 edits
  dropped.
- Promotion: 3 promotions — 1 reused heavily, 1 deleted unused, 1 wrong but
  used.
- Main failure: 55% of moves blocked; 24/30 episodes stuck under the goal
  with the wrong rotation.

**How it was verified:**
- `python -m evolve.selftest`: 76 checks pass. They cover:
  - the score ladder;
  - 6 gate cases;
  - 26 hand-written claims, incl. #9's false beliefs and the extractor's
    formatting slips;
  - a lime- vs a teal-based player helper;
  - parallel = serial envs;
  - logged = replayed states;
  - the fact-check stage inside Validate (false → dropped with a Meta-facing
    reason that hides the truth; unverifiable → kept and flagged).
- A 200-action stub episode with life losses and a game over: logged states
  = replayed (202/202).
- Stub end-to-end runs (2 rounds).
- The fact-check run on #9's 11 real accepted edits labels the known false
  beliefs false and the 5-cell moves true.
- Figures checked visually on stub and real data; image links verified
  (HTTP 200).
- No credentials in any committed file.
