# vc33 — game notes (issue #15)

**For the scorer, the fact-check and the tests only.** Nothing in this file may
appear in v0, in hand-written harness text, in the Analyze report, or in
anything sent to the player or the Meta LLM. The leak test
(`scorer/tests.py`, `leak_test`) scans for the facts below.

Source: `environment_files/vc33/5430563c/vc33.py` (game id `vc33-5430563c`,
tag "click", 7 levels, human baseline 7 actions for Level 1). Inspected
2026-11-25 by reading the source and stepping the game offline.

## What the SDK exposes

| | |
|---|---|
| Actions | `available_actions = [6]` only: **ACTION6, a click with x, y** in 0..63. RESET (0) always works. |
| Frame | 64x64. Level 1's grid is 32x32 drawn at 2 display cells per grid cell. |
| Frame data | `state`, `levels_completed`, `available_actions`. **No score or progress field.** |
| Game state (internal) | `level_index`; gravity `dwwmpxqsza` ([2, 0] on Level 1: horizontal); objects to deliver (tag `0016uciqlhjlom`); target marks (`0010gnulkywfpz`); columns (`0043nzrtobajqi`); walls (`0025yfyiswdvoh`); buttons (`0022jvmlspyigc`, also `sys_click`); the step bar `heczcoeosi` (`current_steps`, `dmesyeowwd`). |

## Level 1

- Background green (3). Gravity points right (+x): columns "stand" on the
  right edge and grow leftward.
- Two black (0) **columns**: `0042` at grid x 16-31, y 0-13; `0044` at grid
  x 26-31, y 16-31. A grey (5) **wall** at grid y 14-15, x 10-31.
- One **object** (`0015`, 3x3, colours yellow 4 and lime 11) standing on
  column `0044`, at grid (23, 22).
- One **target mark** (`0009`, lime 11) in the wall at grid x 17-19, y 14-15;
  visible lime at display rows 28-31, cols 38-39.
- Two maroon (9) **buttons** at the right edge: grid (30, 12) and (30, 16),
  display rows 24-27 and 32-35, cols 60-63.
- A click on a button moves 2 grid cells of width from one column to the other
  (`xowbpvmzbd`); the object on a column moves with it. **Button (30, 16)**
  (display x 60-63, y 32-35) grows column `0044` and moves the object 2 cells
  left; button (30, 12) does the opposite, until the column is empty.
- **Win check** (`ielczunthe`): every object must, for some mark, (a) have its
  colour (bottom-right pixel, lime 11) among the mark's colours, (b) have the
  same cross-gravity coordinate (x on Level 1) as the mark, (c) stand on a
  column touched by the mark's wall. On Level 1 (a) and (c) always hold; the
  object must go from x 23 to x 17. **Shortest solution: 3 clicks on button
  (30, 16)**, e.g. display (61, 33) as (x, y).
- **Step bar**: 50 steps, row 0, orange (7) left, yellow (4) used. **Every
  click uses a step**, on a button or not. At 0 the game is lost.

## Goal-progress score (scorer/vc33/score.py)

| part | weight | definition |
|---|---|---|
| alignment | 1.0 | mean over objects of max(0, 1 − d / d at the start); d = cross-axis distance to the nearest mark meeting (a) and (c) |

(a) and (c) are recorded per state but carry no weight: they never change on
Level 1. Alignment 1 is the clear. Level 1: each click on the right button
+1/3, on the wrong one −1/3 (floored at 0). An episode scores its best
Level-1 state; a clear = 1.0. Nothing is guessed: the parts are the win
test's own comparisons.

## Fact-check ground truth (scorer/vc33/score.py, `ground_truth`)

- No action moves a sprite by itself; ACTION6 claims are unverifiable.
- Colour roles: orange = step counter; yellow = step counter + ui; lime =
  goal (target mark) + ui; other colours "ui". Absent roles (false): lives,
  rotation switch, collectible, hazard, trail, enemy.
- Location: goal (mark) at display rows 28-31, cols 34-39; step counter row 0.
- Count `moves_per_life` = 50.
- Goal requirement: position = true; rotation, collect, avoid = false; colour
  and shape unverifiable.
- Nothing rotates. There is no player sprite (the object moves only through
  the columns).
