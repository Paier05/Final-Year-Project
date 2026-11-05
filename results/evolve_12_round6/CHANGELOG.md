# CHANGELOG: harness versions for issue #12 (ls20, level 1)

Append-only. One section per version, written at stage 4; the gate decision is appended when the version has been evaluated.
Fact-check flags: an accepted edit with claims the game could not confirm or refute is marked **UNVERIFIABLE**, with those claims.

## v0 (parent -, round 0) — 2026-11-02T14:55:26
- seed: issue #8's harness ported to code-acting (see evolve/seed_v0.py); same v0 as #9
Accepted edits (0):
- (none)
Dropped at Validate (0):
- (none)

Gate for v0: baseline — mean progress 0.52, mean cost 0.9038, mean gate score 0.0682, clear rate 0.0

## v1 (parent v0, round 1) — 2026-11-02T18:14:11
Accepted edits (4):
- `r1-e2` [rule] **UNVERIFIABLE** add skill block_info — inline helper defined in 1 episode(s), 1 turn(s), called 5 times
  - fact-check: 3 claims: 0 true, 0 false, 3 unverifiable
    - UNVERIFIABLE "teal = [(r, c) for r in range(64) for c in range(64) if g[r, c] == 12]" (colour_role): role 'other' is not checkable
    - UNVERIFIABLE "mar = [(r, c) for r in range(64) for c in range(64) if g[r, c] == 9]" (colour_role): role 'other' is not checkable
    - UNVERIFIABLE "return (bb(teal), bb(mar), len(teal), len(mar))" (other): outside the checkable vocabulary
- `r1-e3` [rule] **UNVERIFIABLE** add skill teal_centroid — inline helper defined in 1 episode(s), 1 turn(s), called 5 times
  - fact-check: 2 claims: 0 true, 0 false, 2 unverifiable
    - UNVERIFIABLE "cells = [(r, c) for r in range(64) for c in range(64) if g[r, c] == 12]" (colour_role): role 'other' is not checkable
    - UNVERIFIABLE "return (sum((r for r, c in cells)) / len(cells), sum((c for r, c in cells)) / len(cells))" (other): outside the checkable vocabulary
- `r1-e5` [meta] add skill move_cluster_to — The player oscillates because it decides one action per turn and re-tests. This skill batches up to 6 movement actions in one turn, driving the cluster toward the target directly.
  - fact-check: 6 claims: 6 true, 0 false, 0 unverifiable
- `r1-e6` [meta] edit step 4 — The player wastes 44-114 turns with no action and re-tests known actions. This step forces it to use the batch-move skill once dynamics are known.
  - fact-check: 0 claims: 0 true, 0 false, 0 unverifiable
Dropped at Validate (3):
- `r1-e1` [rule] add skill find — replay: behaviour changed: episode 1 diverges at turn 158
- `r1-e4` [meta] edit prompt knowledge — fact-check: contradicted by the game: 'The goal is to move the cluster into a target region (often a grey(5) box or near the blue(1)/black(0) sprite at rows 31-33, cols 20-22).'; 'The goal is to move the cluster into a target region (often a grey(5) box or near the blue(1)/black(0) sprite at rows 31-33, cols 20-22).'; 'The goal is to move the cluster into a target region (often a grey(5) box or near the blue(1)/black(0) sprite at rows 31-33, cols 20-22).'
  - fact-check: 17 claims: 12 true, 3 false, 2 unverifiable
    - UNVERIFIABLE "In game LS20, ACTION2 usually causes a tiny change, mostly lime -> green cells." (other): outside the checkable vocabulary
    - UNVERIFIABLE "ACTION2 also converts some lime->green cells in the bottom rows; this is a side effect, not the main effect." (other): outside the checkable vocabulary
    - FALSE "The goal is to move the cluster into a target region (often a grey(5) box or near the blue(1)/black(0) sprite at rows 31-33, cols 20-22)." (colour_role): blue is rotation_switch
    - FALSE "The goal is to move the cluster into a target region (often a grey(5) box or near the blue(1)/black(0) sprite at rows 31-33, cols 20-22)." (colour_role): black is rotation_switch
    - FALSE "The goal is to move the cluster into a target region (often a grey(5) box or near the blue(1)/black(0) sprite at rows 31-33, cols 20-22)." (location): goal at rows 10-14, cols 34-38
- `r1-e7` [meta] edit step 1 — fact-check: contradicted by the game: 'Identify the teal/maroon cluster centroid and the target location (grey box or blue/black sprite).'; 'Identify the teal/maroon cluster centroid and the target location (grey box or blue/black sprite).'
  - fact-check: 5 claims: 3 true, 2 false, 0 unverifiable
    - FALSE "Identify the teal/maroon cluster centroid and the target location (grey box or blue/black sprite)." (colour_role): blue is rotation_switch
    - FALSE "Identify the teal/maroon cluster centroid and the target location (grey box or blue/black sprite)." (colour_role): black is rotation_switch

Gate for v1 vs v0: **accepted** (tie-break on cost) — tie on progress (|-0.0228| <= eps 0.05); child cheaper (cost -0.1103); drop +0.0848 <= 0.1 (progress 0.4972 vs 0.52, cost 0.7935 vs 0.9038, gate score 0.1004 vs 0.0682, worst gate score -0.0891 vs -0.0043)

## v2 (parent v1, round 2) — 2026-11-02T20:20:41
Accepted edits (3):
- `r2-e1` [rule] delete skill bfs_to_target — never called in 10 evaluated episodes
- `r2-e4` [meta] edit step 4 — Prioritize rotation discovery since it's a major failing component. Only move once rotation is aligned.
  - fact-check: 0 claims: 0 true, 0 false, 0 unverifiable
- `r2-e5` [meta] **UNVERIFIABLE** edit prompt knowledge — Update knowledge to include rotation hypothesis and skills.
  - fact-check: 5 claims: 4 true, 0 false, 1 unverifiable
    - UNVERIFIABLE "In game LS20, ACTION2 usually causes a tiny change, mostly lime -> green cells." (other): outside the checkable vocabulary
Dropped at Validate (2):
- `r2-e2` [meta] add skill detect_orientation — skill test: test fails at state 'after 0 actions': IndexError: index 2 is out of bounds for axis 1 with size 2 (line 1)
- `r2-e3` [meta] add skill rotate_cluster — skill test: test fails at state 'after 0 actions': NameError: name 'detect_orientation' is not defined (line 1)

Gate for v2 vs v1: **accepted** (tie-break on cost) — tie on progress (|+0.0228| <= eps 0.05); child cheaper (cost -0.0587); drop +0.0288 <= 0.1 (progress 0.52 vs 0.4972, cost 0.7348 vs 0.7935, gate score 0.1526 vs 0.1004, worst gate score -0.1179 vs -0.0891)

## v3 (parent v2, round 3) — 2026-11-03T00:14:46
Accepted edits (4):
- `r3-e1` [rule] **UNVERIFIABLE** add skill get_cluster_centroid — inline helper defined in 1 episode(s), 1 turn(s), called 4 times
  - fact-check: 2 claims: 0 true, 0 false, 2 unverifiable
    - UNVERIFIABLE "def get_cluster_centroid(g, colors=[12, 9]):" (colour_role): role 'other' is not checkable
    - UNVERIFIABLE "def get_cluster_centroid(g, colors=[12, 9]):" (colour_role): role 'other' is not checkable
- `r3-e2` [rule] delete skill block_info — never called in 10 evaluated episodes
- `r3-e5` [meta] edit step 4 — Forces the use of the new skills to handle rotation and movement efficiently, reducing exploration loops.
  - fact-check: 0 claims: 0 true, 0 false, 0 unverifiable
- `r3-e6` [meta] **UNVERIFIABLE** edit prompt knowledge — Updates knowledge to include the new skills and the rotation hypothesis, guiding the player to use them.
  - fact-check: 6 claims: 5 true, 0 false, 1 unverifiable
    - UNVERIFIABLE "ACTION2 usually causes a tiny change, mostly lime -> green cells." (other): outside the checkable vocabulary
Dropped at Validate (2):
- `r3-e3` [meta] add skill analyze_cluster_state — fact-check: contradicted by the game: ''target': (row, col) of the nearest cyan(8) or grey(5) target'
  - fact-check: 4 claims: 1 true, 1 false, 2 unverifiable
    - UNVERIFIABLE "Analyze the teal/maroon cluster: position, orientation, and target distance." (colour_role): role 'other' is not checkable
    - UNVERIFIABLE "Analyze the teal/maroon cluster: position, orientation, and target distance." (colour_role): role 'other' is not checkable
    - FALSE "'target': (row, col) of the nearest cyan(8) or grey(5) target" (colour_role): cyan is lives
- `r3-e4` [meta] add skill try_rotate — static tests: sandbox rules: line 45: bare 'except:' is not allowed; catch Exception

Gate for v3 vs v2: **accepted** (gate score) — gate-score gain +0.0190 > 0 and drop -0.1680 <= 0.1 (progress 0.5886 vs 0.52, cost 0.834 vs 0.7348, gate score 0.1716 vs 0.1526, worst gate score 0.0501 vs -0.1179)

## v4 (parent v3, round 4) — 2026-11-03T11:38:57
Accepted edits (3):
- `r4-e1` [meta] **UNVERIFIABLE** edit skill move_cluster_to — The previous version could oscillate if the target was close but not within tolerance. This version is identical but I will ensure the step logic is robust. Actually, the main issue was likely the player not using it enough or the target being wrong. I will keep the logic but ensure it's used. Wait, the previous rejection was for `analyze_cluster_state`. `move_cluster_to` was accepted. I will refine it to be more robust against 'no change' loops by breaking immediately.
  - fact-check: 6 claims: 4 true, 0 false, 2 unverifiable
    - UNVERIFIABLE "teal = [(r, c) for r in range(64) for c in range(64) if g[r, c] == 12]" (colour_role): role 'other' is not checkable
    - UNVERIFIABLE "mar = [(r, c) for r in range(64) for c in range(64) if g[r, c] == 9]" (colour_role): role 'other' is not checkable
- `r4-e2` [meta] **UNVERIFIABLE** add skill try_rotate — The player needs to know which action rotates the cluster. This skill systematically tests the remaining simple actions (5 and 7) and returns the one that works, saving the player from manual trial and error.
  - fact-check: 1 claims: 0 true, 0 false, 1 unverifiable
    - UNVERIFIABLE "Try ACTION5 and ACTION7 to find which one rotates the cluster." (other): outside the checkable vocabulary
- `r4-e4` [meta] edit step 4 — Reinforces the use of `try_rotate` and `move_cluster_to` to minimize manual action selection and reduce token usage from verbose planning.
  - fact-check: 0 claims: 0 true, 0 false, 0 unverifiable
Dropped at Validate (1):
- `r4-e3` [meta] edit prompt knowledge — fact-check: contradicted by the game: 'try_rotate() to find the action that flips it (likely ACTION5 or ACTION7)'
  - fact-check: 8 claims: 5 true, 1 false, 2 unverifiable
    - UNVERIFIABLE "ACTION2 usually causes a tiny change, mostly lime -> green cells" (other): outside the checkable vocabulary
    - UNVERIFIABLE "The teal/maroon cluster may have an orientation (horizontal/vertical)" (other): outside the checkable vocabulary
    - FALSE "try_rotate() to find the action that flips it (likely ACTION5 or ACTION7)" (rotation_cause): no action rotates the player directly; rotation switch at rows 30-34, cols 19-23

Gate for v4 vs v3: **rejected** (tie-break on cost) — tie on progress (|+0.0114| <= eps 0.05); child not cheaper (cost +0.0217) (progress 0.6 vs 0.5886, cost 0.8557 vs 0.834, gate score 0.1722 vs 0.1716, worst gate score 0.0571 vs 0.0501)

## v5 (parent v3, round 5) — 2026-11-03T14:01:04
Accepted edits (1):
- `r5-e3` [meta] **UNVERIFIABLE** edit skill move_cluster_to — The previous version was fine, but I'm keeping it to ensure it's present and correct. The main issue was the player not using it effectively due to lack of rotation handling.
  - fact-check: 6 claims: 4 true, 0 false, 2 unverifiable
    - UNVERIFIABLE "teal = [(r, c) for r in range(64) for c in range(64) if g[r, c] == 12]" (colour_role): role 'other' is not checkable
    - UNVERIFIABLE "mar = [(r, c) for r in range(64) for c in range(64) if g[r, c] == 9]" (colour_role): role 'other' is not checkable
Dropped at Validate (3):
- `r5-e1` [meta] add skill get_cluster_orientation — skill test: test fails at state 'after 0 actions': IndexError: index 3 is out of bounds for axis 1 with size 3 (line 1)
- `r5-e2` [meta] add skill try_rotate_cluster — fact-check: contradicted by the game: 'Try ACTION5 and ACTION7 to rotate the cluster'; 'Try ACTION5 and ACTION7 to rotate the cluster'
  - fact-check: 2 claims: 0 true, 2 false, 0 unverifiable
    - FALSE "Try ACTION5 and ACTION7 to rotate the cluster" (rotation_cause): no action rotates the player directly; rotation switch at rows 30-34, cols 19-23
    - FALSE "Try ACTION5 and ACTION7 to rotate the cluster" (rotation_cause): no action rotates the player directly; rotation switch at rows 30-34, cols 19-23
- `r5-e4` [meta] edit prompt knowledge — fact-check: contradicted by the game: 'likely ACTION5 or ACTION7'; 'likely ACTION5 or ACTION7'; 'Identify target location (cyan/grey box)'
  - fact-check: 11 claims: 6 true, 3 false, 2 unverifiable
    - UNVERIFIABLE "ACTION2 usually causes a tiny change, mostly lime -> green cells" (other): outside the checkable vocabulary
    - UNVERIFIABLE "The teal/maroon cluster may have an orientation" (other): outside the checkable vocabulary
    - FALSE "likely ACTION5 or ACTION7" (rotation_cause): no action rotates the player directly; rotation switch at rows 30-34, cols 19-23
    - FALSE "likely ACTION5 or ACTION7" (rotation_cause): no action rotates the player directly; rotation switch at rows 30-34, cols 19-23
    - FALSE "Identify target location (cyan/grey box)" (colour_role): cyan is lives

Gate for v5 vs v3: **rejected** (gate score) — no gate-score gain (-0.1047; progress -0.1143, cost -0.0191) (progress 0.4743 vs 0.5886, cost 0.8149 vs 0.834, gate score 0.0669 vs 0.1716, worst gate score -0.1444 vs 0.0501)

## v6 (parent v3, round 6) — 2026-11-04T19:15:15
Accepted edits (3):
- `r6-e2` [meta] add skill check_orientation — The player needs to know its current orientation to compare it against the goal's orientation. This skill provides a simple way to determine the player's current orientation.
  - fact-check: 2 claims: 2 true, 0 false, 0 unverifiable
- `r6-e3` [meta] edit step 4 — This step now explicitly instructs the player to use the new skills to determine the goal and orientation, and to take appropriate actions based on that information.
  - fact-check: 0 claims: 0 true, 0 false, 0 unverifiable
- `r6-e4` [meta] **UNVERIFIABLE** edit prompt knowledge — Updates the knowledge prompt to include the new skills and their usage, guiding the player to use them effectively.
  - fact-check: 6 claims: 5 true, 0 false, 1 unverifiable
    - UNVERIFIABLE "ACTION2 usually causes a tiny change, mostly lime -> green cells." (other): outside the checkable vocabulary
Dropped at Validate (1):
- `r6-e1` [meta] add skill find_goal — fact-check: contradicted by the game: 'goal_colors = [8, 5, 1, 0]'; 'goal_colors = [8, 5, 1, 0]'; 'goal_colors = [8, 5, 1, 0]'
  - fact-check: 7 claims: 3 true, 3 false, 1 unverifiable
    - FALSE "goal_colors = [8, 5, 1, 0]" (colour_role): cyan is lives
    - FALSE "goal_colors = [8, 5, 1, 0]" (colour_role): blue is rotation_switch
    - FALSE "goal_colors = [8, 5, 1, 0]" (colour_role): black is rotation_switch
    - UNVERIFIABLE "Returns a dict with 'target' (row, col) and 'orientation' ('horizontal' or 'vertical')." (skill_output): after 0 actions: real rows 10-14, cols 34-38 -> returned nothing usable; after 100 actions: real rows 10-14, cols 34-38 -> returned nothing usable; after 180 actions: real rows 10-14, cols 34-38 -> returned nothing usable

Gate for v6 vs v3: **accepted** (tie-break on cost) — tie on progress (|-0.0229| <= eps 0.05); child cheaper (cost -0.1915); drop -0.1055 <= 0.1 (progress 0.5657 vs 0.5886, cost 0.6425 vs 0.834, gate score 0.2445 vs 0.1716, worst gate score 0.1556 vs 0.0501)

## v7 (parent v6, round 7) — 2026-11-05T15:09:30
Accepted edits (2):
- `r7-e2` [meta] **UNVERIFIABLE** edit prompt knowledge — The current knowledge prompt references non-existent skills and unavailable actions. This edit corrects the facts: ACTION5/7 are unavailable, and `find_goal` is now a real skill. It also clarifies the 'noise' issue.
  - fact-check: 6 claims: 5 true, 0 false, 1 unverifiable
    - UNVERIFIABLE "ACTION2 usually causes a tiny change, mostly lime -> green cells." (other): outside the checkable vocabulary
- `r7-e3` [meta] edit step 4 — Step 4 previously instructed to use ACTION5/7 for rotation, which causes errors. This edit removes that instruction and focuses on using the new `find_goal` skill and `move_cluster_to`.
  - fact-check: 0 claims: 0 true, 0 false, 0 unverifiable
Dropped at Validate (1):
- `r7-e1` [meta] add skill find_goal — replay: behaviour changed: episode 1 diverges at turn 49

Gate for v7 vs v6: **rejected** (gate score) — no gate-score gain (-0.0799; progress -0.0800, cost -0.0003) (progress 0.4857 vs 0.5657, cost 0.6422 vs 0.6425, gate score 0.1646 vs 0.2445, worst gate score -0.0179 vs 0.1556)

