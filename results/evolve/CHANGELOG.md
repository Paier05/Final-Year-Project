# CHANGELOG: harness versions for issue #9 (ls20, level 1)

Append-only. One section per version, written at stage 4; the gate decision is appended when the version has been evaluated.

## v0 (parent -, round 0) — 2026-11-01T18:27:26
- seed: issue #8's harness ported to code-acting (see evolve/seed_v0.py)
Accepted edits (0):
- (none)
Dropped at Validate (0):
- (none)

Gate for v0: baseline — mean score 0.3333, worst 0.0877, clear rate 0.0

## v1 (parent v0, round 1) — 2026-11-01T18:58:54
Accepted edits (3):
- `r1-e1` [meta] add skill collect_items — The player needs to know where the maroon collectibles are to plan an efficient route. This skill groups nearby maroon cells so the player can target them.
- `r1-e2` [meta] add skill player_position — The player keeps getting confused about its own position. This skill gives a clear, consistent way to find where the player is.
- `r1-e3` [meta] edit prompt knowledge — The player is confused about the game dynamics and keeps wasting actions. This prompt clearly states what has been established and gives a clear strategy.
Dropped at Validate (0):
- (none)

Gate for v1 vs v0: **accepted** — gain +0.0702 > 0 and drop -0.1755 <= 0.1 (mean 0.4035 vs 0.3333, worst 0.2632 vs 0.0877)

## v2 (parent v1, round 2) — 2026-11-01T19:23:53
Accepted edits (3):
- `r2-e1` [rule] delete skill bfs_to_target — never called in 6 evaluated episodes
- `r2-e2` [meta] edit prompt knowledge — The player's current strategy is flawed because it tries to reach the bottom-left maroon cluster by moving left, but this cluster is still 1-6 rows above the player. The player needs to move up first to align with the maroon items' rows, then move horizontally to collect them. This edit explicitly states that moving left/right at rows 61-62 is useless and that the player must move up first.
- `r2-e3` [meta] add skill plan_route — This skill helps the player plan an efficient route by first moving up/down to align with the maroon items' rows, then moving horizontally to collect them. It addresses the player's current flaw of wasting actions moving left/right without first moving up.
Dropped at Validate (0):
- (none)

Gate for v2 vs v1: **accepted** — gain +0.0702 > 0 and drop -0.2105 <= 0.1 (mean 0.4737 vs 0.4035, worst 0.4737 vs 0.2632)

## v3 (parent v2, round 3) — 2026-11-01T19:58:37
Accepted edits (1):
- `r3-e1` [meta] edit prompt knowledge — The player is confused about the movement mechanics and is wasting actions. The 'knowledge' prompt incorrectly states that actions move 5 cells, which is not supported by the action effects data. The player is also not accounting for the fact that it is a 2-row bar, which affects its position and movement. This edit corrects the movement mechanics and provides a clearer strategy.
Dropped at Validate (1):
- `r3-e2` [meta] edit skill plan_route — replay: edited skill raises where the parent did not: episode 0 turn 0

Gate for v3 vs v2: **rejected** — no dev gain (-0.0117) (mean 0.462 vs 0.4737, worst 0.4386 vs 0.4737)

## v4 (parent v2, round 4) — 2026-11-01T20:25:23
Accepted edits (2):
- `r4-e1` [meta] add skill verify_move — The player is repeating actions that don't work (e.g., ACTION3 when blocked). This skill forces the player to check if the action actually moved the player before deciding to repeat it or change strategy. It addresses the 'oscillation' problem seen in the episodes.
- `r4-e2` [meta] edit prompt knowledge — The previous knowledge prompt was too vague about obstacles and encouraged blind movement. This version explicitly states that actions can be blocked and instructs the player to use verify_move() and check for walls. It also corrects the movement distance to 1 cell per action, which is supported by the 'rigid move' data (drow=5 is likely a misinterpretation of the grid scale or a specific game mechanic, but the 'other change' dominance suggests blocking is the main issue).
Dropped at Validate (1):
- `r4-e3` [meta] delete skill plan_route — replay: behaviour changed: episode 0 diverges at turn 0

Gate for v4 vs v2: **rejected** — no dev gain (+0.0000) (mean 0.4737 vs 0.4737, worst 0.4737 vs 0.4737)

## v5 (parent v2, round 5) — 2026-11-01T22:54:12
Accepted edits (3):
- `r5-e1` [meta] edit prompt knowledge — The previous prompt incorrectly stated that actions move 5 cells and that green is a static wall. The evidence shows actions move 1 cell and that green causes 'other change' effects (swaps). This correction is crucial for the player to understand that it must navigate through gaps in the green structure rather than trying to push through it or move around it at the bottom.
- `r5-e2` [meta] edit skill plan_route — The previous plan_route skill assumed 5-cell moves, which is incorrect. This edit corrects it to 1-cell moves, ensuring the planned route is accurate and the player doesn't overshoot or undershoot targets.
- `r5-e3` [meta] add skill find_gaps — The player is struggling to navigate the green structure. This skill helps the player identify gaps in the green cells, which are the only paths through the structure to reach the maroon items.
Dropped at Validate (0):
- (none)

Gate for v5 vs v2: **rejected** — no dev gain (+0.0000) (mean 0.4737 vs 0.4737, worst 0.4737 vs 0.4737)

