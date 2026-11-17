# CHANGELOG: harness versions for issue #14 (ls20, level 1)

Append-only. One section per version, written at stage 4; the gate decision is appended when the version has been evaluated.
Fact-check flags: an accepted edit with claims the game could not confirm or refute is marked **UNVERIFIABLE**, with those claims.
Skill-name check: an edit dropped for naming a skill that does not exist lists each missing name with its file and line.

## v0 (parent -, round 0) — 2026-11-15T02:14:07
- seed: issue #8's harness ported to code-acting (see evolve/seed_v0.py); same v0 as #9
Accepted edits (0):
- (none)
Dropped at Validate (0):
- (none)

Gate for v0: baseline — mean progress 0.5314, mean cost 0.6179, mean gate score 0.2225, clear rate 0.0

## v1 (parent v0, round 1) — 2026-11-15T02:58:56
Accepted edits (1):
- `r1-e2` [meta] edit prompt knowledge — Removes the hallucinated skill name `plan_path` from the previous failed edit's context (which was in the prompt) and correctly documents the new `plan_path` skill. Also clarifies that ACTION2 might move the block down, which was a point of confusion in the episodes.
  - fact-check: 3 claims: 3 true, 0 false, 0 unverifiable
Dropped at Validate (3):
- `r1-e1` [meta] add skill plan_path — fact-check: contradicted by the game: 'Assumes the player moves 5 cells per action.'; 'the player moves through 'lime' (11) and 'green' (3).'
  - fact-check: 4 claims: 2 true, 2 false, 0 unverifiable
    - FALSE "Assumes the player moves 5 cells per action." (move): ACTION1 moves the player up 5 cells; logged: {(0, 0): 167, (-5, 0): 119}
    - FALSE "the player moves through 'lime' (11) and 'green' (3)." (colour_role): lime is step_counter
- `r1-e2` [meta] edit prompt knowledge — skill-name check: names a skill that does not exist: `plan_path` (prompts.json[knowledge] line 26)
  - missing skill name `plan_path`: prompts.json[knowledge] line 26 (prompt): 2. Use `plan_path` to calculate the moves needed to reach the goal's position.
- `r1-e1` [meta] add skill plan_path — fact-check: contradicted by the game: 'The block moves 5 cells per action.'
  - fact-check: 5 claims: 4 true, 1 false, 0 unverifiable
    - FALSE "The block moves 5 cells per action." (move): ACTION1 moves the player up 5 cells; logged: {(0, 0): 167, (-5, 0): 119}

Gate for v1 vs v0: **rejected** (tie-break on cost) — tie on progress, child cheaper, but worst-episode drop +0.1227 > delta 0.1 (progress 0.5543 vs 0.5314, cost 0.5909 vs 0.6179, gate score 0.2589 vs 0.2225, worst gate score -0.0673 vs 0.0554)

## round 2: no child (parent v0)
Every proposed edit was dropped at Validate (5).
- `r2-e1` [meta] edit prompt knowledge — fact-check: contradicted by the game: 'Goal: Cyan block (2x8 cells, colour 8) at rows 61-62, cols 56-63.'; 'Goal: Cyan block (2x8 cells, colour 8) at rows 61-62, cols 56-63.'; 'Trail: Lime cells (colour 11) appear where the player has been.'
- `r2-e2` [meta] add skill find_goal — fact-check: contradicted by the game: 'if o["colour"] == 8: return o["bbox"]'; 'Find the cyan goal block (colour 8) and return its bounding box.'
- `r2-e3` [meta] add skill find_player — skill test: test fails at state 'after 100 actions': AssertionError:  (line 3)
- `r2-e2` [meta] add skill plan_path — skill test: test fails at state 'after 0 actions': AssertionError: Expected [1], got [2] (line 6)
- `r2-e1` [meta] edit prompt knowledge — skill-name check: names a skill that does not exist: `plan_path` (prompts.json[knowledge] line 13)

## v3 (parent v0, round 3) — 2026-11-15T03:58:15
Accepted edits (3):
- `r3-e1` [meta] **UNVERIFIABLE** edit prompt knowledge — The current knowledge prompt is misleading (claims ACTION2 is a recolor, misses the 5-cell move and jump mechanic). This new prompt establishes the correct dynamics based on the frame evidence (5x5 block, 5-cell moves, lime->green trail, jumps) and provides a clear strategy to reduce exploration waste.
  - fact-check: 9 claims: 7 true, 0 false, 2 unverifiable
    - UNVERIFIABLE "Player: 5x5 block (top 2 rows: current colour, bottom 3 rows: maroon/9)." (other): outside the checkable vocabulary
    - UNVERIFIABLE "Moving onto a 'lime' (11) cell converts it to 'green' (3) and leaves a trail." (other): outside the checkable vocabulary
- `r3-e2` [meta] **UNVERIFIABLE** add skill plan_moves — Provides a direct way to calculate the required actions, reducing the need for the LLM to manually count moves and potentially make arithmetic errors or waste turns planning.
  - fact-check: 1 claims: 0 true, 0 false, 1 unverifiable
    - UNVERIFIABLE "def plan_moves(player_r, player_c, goal_r, goal_c): ... return moves" (other): outside the checkable vocabulary
- `r3-e3` [meta] edit step 3 — Directs the player to use the new skill and focus on goal identification, which is the primary bottleneck in the current episodes.
  - fact-check: 0 claims: 0 true, 0 false, 0 unverifiable
Dropped at Validate (0):
- (none)

Gate for v3 vs v0: **rejected** (gate score) — no gate-score gain (-0.2736; progress -0.3200, cost -0.0928) (progress 0.2114 vs 0.5314, cost 0.5251 vs 0.6179, gate score -0.0511 vs 0.2225, worst gate score -0.0731 vs 0.0554)

## v4 (parent v0, round 4) — 2026-11-15T04:33:47
Accepted edits (1):
- `r4-e1` [meta] **UNVERIFIABLE** edit prompt knowledge — The current knowledge prompt incorrectly states that ACTION2 is a recolor action. The frame evidence and action effects show that ACTION2 moves the block down by 5 cells. Correcting this will help the player plan its moves more effectively. Also, the goal description is updated to reflect the weighted components of the score.
  - fact-check: 6 claims: 5 true, 0 false, 1 unverifiable
    - UNVERIFIABLE "Move the player (5x5 block) to the goal square" (other): outside the checkable vocabulary
Dropped at Validate (1):
- `r4-e2` [meta] add skill plan_moves — skill test: test fails at state 'after 0 actions': AssertionError:  (line 2)

Gate for v4 vs v0: **accepted** (gate score) — gate-score gain +0.1354 > 0 and drop -0.1600 <= 0.1 (progress 0.6572 vs 0.5314, cost 0.5986 vs 0.6179, gate score 0.3579 vs 0.2225, worst gate score 0.2154 vs 0.0554)

## v5 (parent v4, round 5) — 2026-11-15T05:30:31
Accepted edits (2):
- `r5-e1` [meta] add skill plan_moves — The player wastes actions on blocked moves because it doesn't calculate the exact number of steps needed. This skill provides the exact sequence of actions to reach the goal, assuming the 5-cell step size established in the knowledge prompt and frame evidence.
  - fact-check: 5 claims: 5 true, 0 false, 0 unverifiable
- `r5-e2` [meta] **UNVERIFIABLE** edit prompt knowledge — Clarifies that the player moves in 5-cell steps and directs the player to use the new `plan_moves` skill to avoid wasted actions on blocked moves.
  - fact-check: 6 claims: 5 true, 0 false, 1 unverifiable
    - UNVERIFIABLE "The player (5x5 block)" (other): outside the checkable vocabulary
Dropped at Validate (0):
- (none)

Gate for v5 vs v4: **rejected** (tie-break on cost) — tie on progress (|-0.0458| <= eps 0.05); child not cheaper (cost +0.2005) (progress 0.6114 vs 0.6572, cost 0.7991 vs 0.5986, gate score 0.2119 vs 0.3579, worst gate score 0.0987 vs 0.2154)

## v6 (parent v4, round 6) — 2026-11-15T11:28:30
Accepted edits (1):
- `r6-e1` [meta] **UNVERIFIABLE** edit prompt knowledge — The current knowledge prompt is misleading about the player's shape and lacks critical information about the 5-cell step constraint and rotation requirement. This edit clarifies the dynamics and provides guidance on how to handle blocked moves and rotation mismatches, which are the primary causes of failure in the episodes.
  - fact-check: 6 claims: 5 true, 0 false, 1 unverifiable
    - UNVERIFIABLE "The player is a 5x5 block" (other): outside the checkable vocabulary
Dropped at Validate (2):
- `r6-e2` [meta] add skill check_move — skill test: test fails at state 'after 0 actions': AssertionError:  (line 4)
- `r6-e3` [meta] edit step 4 — skill-name check: names a skill that does not exist: `check_move` (steps.json[4] line 1)
  - missing skill name `check_move`: steps.json[4] line 1 (step): PLAN: decide the next few actions (at most {cap}) that either test a hypothesis or make progress toward the goal. Use `c

Gate for v6 vs v4: **rejected** (tie-break on cost) — tie on progress (|+0.0228| <= eps 0.05); child not cheaper (cost +0.0902) (progress 0.68 vs 0.6572, cost 0.6888 vs 0.5986, gate score 0.3356 vs 0.3579, worst gate score 0.108 vs 0.2154)

