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

