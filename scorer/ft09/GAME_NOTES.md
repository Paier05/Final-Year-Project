# ft09 — game notes (issue #15)

**For the scorer, the fact-check and the tests only.** Nothing in this file may
appear in v0, in hand-written harness text, in the Analyze report, or in
anything sent to the player or the Meta LLM. The leak test
(`scorer/tests.py`, `leak_test`) scans for the facts below.

Source: `environment_files/ft09/0d8bbf25/ft09.py` (game id `ft09-0d8bbf25`,
6 levels, human baseline 43 actions for Level 1). Inspected 2026-11-25 by
reading the source and stepping the game offline.

## What the SDK exposes

| | |
|---|---|
| Actions | `available_actions = [6]` only: **ACTION6, a click with x, y** in 0..63. No ACTION1-5/7. RESET (0) always works. |
| Frame | 64x64. Level 1's grid is 32x32 drawn at 2 display cells per grid cell (`display_to_grid`: grid = display // 2). |
| Frame data | `state` (NOT_FINISHED / GAME_OVER / WIN), `levels_completed`, `available_actions`. **No score or progress field.** |
| Game state (internal) | `level_index`; pattern sprites (tag `bsT`); tiles (tags `Hkx`, `NTi`); the palette `gqb`; the click budget `lpw` (`dzy` left, `oro` per level). |

## Level 1

- Background grey (5); the play area (bottom right of the display) is
  yellow (4) inside a red (2) bracket (`UEq`, tag `Ycb`).
- **8 clickable tiles** (`Hkx`), 3x3 grid cells each, maroon (9) at the start,
  in a ring around one **pattern sprite** (`wmW`, tag `bsT`) at grid (22, 22):
  tiles at grid x, y in {18, 22, 26} except the centre. Display: rows/cols
  36-41, 44-49, 52-57 (centre 44-49 is the pattern).
- Pattern pixels `[[0,2,2],[0,8,0],[0,2,2]]`, centre colour 8 (cyan).
- Clicking a tile cycles its colour through `gqb = [9, 8]`. On Level 1 the
  click pattern `elp` is `[[0,0,0],[0,1,0],[0,0,0]]`: only the clicked tile
  changes.
- **Win check** (`cgj`): for each neighbour of the pattern that holds a tile,
  where the pattern's pixel is 0 the tile's centre must equal the pattern's
  centre (8); elsewhere it must differ. Level 1: the tiles at grid
  (18,18), (18,22), (18,26) and (26,22) must be 8, the other four must stay
  not-8. **Shortest solution: 4 clicks**, display (37,37), (37,45), (37,53),
  (53,45) as (x, y). At the start 4 of 8 checks fail.
- Three reference pictures (top left, top right, bottom left; `wCl`, `TOK`,
  `vxk`) show a ring of tiles with a small pattern in the middle (`sxj`,
  `MEF`, `qqX`). They are not clickable.
- **Click budget**: 32 tile clicks (`kCv`), drawn as the bottom row (row 63):
  teal (12) for clicks left, lime (11) for clicks used (2 of the 64 cells per
  click). A click on a tile uses one; when none is left the game is lost
  (GAME_OVER; the harness resets the level). On a clear the budget refills.
- **A click that hits no tile** (and not the pattern) on Level 1 makes the red
  bracket flash 4 frames and ends unchanged: no budget used, no state change.
  A click on the pattern does nothing.

## Goal-progress score (scorer/ft09/score.py)

| part | weight | definition |
|---|---|---|
| tiles | 1.0 | max(0, 1 − checks failing / checks failing at the start) |

The win check has no other condition, so there is one part. A state with no
failing check is the clear. Each right click +0.25, each wrong click −0.25 on
Level 1. An episode scores its best Level-1 state; a clear = 1.0. What the
state exposes for partial progress is exactly the per-tile checks of the win
test, so nothing is guessed.

## Fact-check ground truth (scorer/ft09/score.py, `ground_truth`)

- No action moves a sprite; ACTION6 claims are unverifiable (depends on where).
- Colour roles: teal and lime = step counter; every other colour on screen is
  "ui" (claims unverifiable). Absent roles (claim false): lives, rotation
  switch, collectible, hazard, trail, enemy.
- Count `moves_per_life` = 32.
- Goal requirement: colour = true; position, rotation, collect, avoid = false.
- Nothing rotates. There is no player sprite.
