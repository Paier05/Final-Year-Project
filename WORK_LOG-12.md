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
<Append a dated entry every time you make meaningful progress, hit a decision point, or change direction. Do not overwrite earlier entries — this is a running history, not a status snapshot.>

## Open questions / risks
<Anything uncertain, anything you're unsure is the right call, anything that should be double-checked by a human.>

## Summary (fill in at the end)
<What changed, why, how it was verified.>
