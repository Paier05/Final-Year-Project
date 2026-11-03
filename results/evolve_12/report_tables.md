### Per round

| round | version | parent | mean progress (± SD) | clear rate | avg steps | avg cost | avg tokens | gate score | decision | reason |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | v0 | – | 0.520 ± 0.046 | 0/5 | 177 | 0.904 | 1068k | 0.068 | **baseline** | v0 is the starting parent |
| 1 | v1 | v0 | 0.497 ± 0.122 | 0/5 | 200 | 0.793 | 784k | 0.100 | **accepted** | tie on progress (\|-0.0228\| <= eps 0.05); child cheaper (cost -0.1103); drop +0.0848 <= 0.1 |
| 2 | v2 | v1 | 0.520 ± 0.138 | 0/5 | 187 | 0.735 | 717k | 0.153 | **accepted** | tie on progress (\|+0.0228\| <= eps 0.05); child cheaper (cost -0.0587); drop +0.0288 <= 0.1 |
| 3 | v3 | v2 | 0.589 ± 0.043 | 0/5 | 200 | 0.834 | 874k | 0.172 | **accepted** | gate-score gain +0.0190 > 0 and drop -0.1680 <= 0.1 |
| 4 | v4 | v3 | 0.600 ± 0.114 | 0/5 | 200 | 0.856 | 900k | 0.172 | **rejected** | tie on progress (\|+0.0114\| <= eps 0.05); child not cheaper (cost +0.0217) |
| 5 | v5 | v3 | 0.474 ± 0.186 | 0/5 | 198 | 0.815 | 831k | 0.067 | **rejected** | no gate-score gain (-0.1047; progress -0.1143, cost -0.0191) |

### Per seed (goal progress)

| version | seed 1 | seed 2 | seed 3 | seed 4 | seed 5 | mean |
|---|---|---|---|---|---|---|
| v0 (baseline) | 0.429 (pos,rot) | 0.543 (pos,rot) | 0.543 (pos,rot) | 0.543 (pos,rot) | 0.543 (pos,rot) | 0.520 |
| v1 (accepted) | 0.543 (pos,rot) | 0.543 (pos,rot) | 0.257 (pos,rot) | 0.543 (pos,rot) | 0.600 (pos) | 0.497 |
| v2 (accepted) | 0.543 (pos,rot) | 0.600 (pos) | 0.543 (pos,rot) | 0.257 (pos,rot) | 0.657 (pos) | 0.520 |
| v3 (accepted) | 0.543 (pos,rot) | 0.600 (pos) | 0.543 (pos,rot) | 0.657 (pos) | 0.600 (pos) | 0.589 |
| v4 (rejected) | 0.829 (pos) | 0.543 (pos,rot) | 0.543 (pos,rot) | 0.543 (pos,rot) | 0.543 (pos,rot) | 0.600 |
| v5 (rejected) | 0.543 (pos,rot) | 0.257 (pos,rot) | 0.257 (pos,rot) | 0.714 (pos) | 0.600 (pos) | 0.474 |

(in brackets: goal parts failing at the episode's best state; pos = position, rot = rotation)

### Edits per round

| round | child | promote | merge | delete | edit | add (other) | from Meta LLM | rule-based | dropped at Validate (stage) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | v1 (accepted) | 2 | 0 | 0 | 1 | 1 | 2 | 2 | 3 (replay 1, fact-check 2) |
| 2 | v2 (accepted) | 0 | 0 | 1 | 2 | 0 | 2 | 1 | 2 (skill test 2) |
| 3 | v3 (accepted) | 1 | 0 | 1 | 2 | 0 | 2 | 2 | 2 (fact-check 1, static tests 1) |
| 4 | v4 (rejected) | 0 | 0 | 0 | 2 | 1 | 3 | 0 | 1 (fact-check 1) |
| 5 | v5 (rejected) | 0 | 0 | 0 | 1 | 0 | 1 | 0 | 3 (skill test 1, fact-check 2) |

Accepted edits, by round:

- v1 `r1-e2` [rule] add skill block_info ⚑ unverifiable claims
- v1 `r1-e3` [rule] add skill teal_centroid ⚑ unverifiable claims
- v1 `r1-e5` [meta] add skill move_cluster_to
- v1 `r1-e6` [meta] edit step 4
- v2 `r2-e1` [rule] delete skill bfs_to_target
- v2 `r2-e4` [meta] edit step 4
- v2 `r2-e5` [meta] edit prompt knowledge ⚑ unverifiable claims
- v3 `r3-e1` [rule] add skill get_cluster_centroid ⚑ unverifiable claims
- v3 `r3-e2` [rule] delete skill block_info
- v3 `r3-e5` [meta] edit step 4
- v3 `r3-e6` [meta] edit prompt knowledge ⚑ unverifiable claims
- v4 `r4-e1` [meta] edit skill move_cluster_to ⚑ unverifiable claims
- v4 `r4-e2` [meta] add skill try_rotate ⚑ unverifiable claims
- v4 `r4-e4` [meta] edit step 4
- v5 `r5-e3` [meta] edit skill move_cluster_to ⚑ unverifiable claims

### Helpers

| version | helper groups written (distinct bodies) | episodes that wrote one | helper calls | promoted into this version | promoted skills called by its players |
|---|---|---|---|---|---|
| v0 | 28 | 4/5 | 92 | – | – |
| v1 | 1 | 1/5 | 0 | block_info, teal_centroid | block_info (0 calls), teal_centroid (90 calls) |
| v2 | 1 | 1/5 | 4 | – | block_info (0 calls), teal_centroid (191 calls) |
| v3 | 1 | 1/5 | 0 | get_cluster_centroid | teal_centroid (258 calls), get_cluster_centroid (94 calls) |
| v4 | 2 | 1/5 | 6 | – | teal_centroid (118 calls), get_cluster_centroid (135 calls) |
| v5 | 5 | 3/5 | 8 | – | teal_centroid (156 calls), get_cluster_centroid (107 calls) |

### Fact-check

| round | claims tested | true | false | unverifiable | edits dropped for a false claim | extraction calls / tokens |
|---|---|---|---|---|---|---|
| 1 | 33 | 21 | 5 | 7 | 2 (r1-e4, r1-e7) | 1 / 5.2k |
| 2 | 5 | 4 | 0 | 1 | 0 (–) | 1 / 3.5k |
| 3 | 12 | 6 | 1 | 5 | 1 (r3-e3) | 1 / 3.8k |
| 4 | 15 | 9 | 1 | 5 | 1 (r4-e3) | 1 / 2.7k |
| 5 | 19 | 10 | 5 | 4 | 2 (r5-e2, r5-e4) | 1 / 4.0k |
| **all** | **84** | **50** | **12** | **22** | **6** | 5 / 19.3k |

Claims labelled false (the evidence is the game's ground truth; the Meta LLM was told only that the claim is false):

- round 1 `r1-e4` (edit prompt knowledge): "The goal is to move the cluster into a target region (often a grey(5) box or near the blue(1)/black(0) sprite at rows 31-33, cols 20-22)." → blue is rotation_switch; black is rotation_switch; goal at rows 10-14, cols 34-38
- round 1 `r1-e7` (edit step 1): "Identify the teal/maroon cluster centroid and the target location (grey box or blue/black sprite)." → blue is rotation_switch; black is rotation_switch
- round 3 `r3-e3` (add skill analyze_cluster_state): "'target': (row, col) of the nearest cyan(8) or grey(5) target" → cyan is lives
- round 4 `r4-e3` (edit prompt knowledge): "try_rotate() to find the action that flips it (likely ACTION5 or ACTION7)" → no action rotates the player directly; rotation switch at rows 30-34, cols 19-23
- round 5 `r5-e2` (add skill try_rotate_cluster): "Try ACTION5 and ACTION7 to rotate the cluster" → no action rotates the player directly; rotation switch at rows 30-34, cols 19-23
- round 5 `r5-e4` (edit prompt knowledge): "likely ACTION5 or ACTION7" → no action rotates the player directly; rotation switch at rows 30-34, cols 19-23
- round 5 `r5-e4` (edit prompt knowledge): "Identify target location (cyan/grey box)" → cyan is lives

### The three comparisons

| comparison | from | to | Δ progress | Δ cost | what it measures |
|---|---|---|---|---|---|
| #9 v0 (rescored) → #12 v0 | 0.467 ± 0.150 (cost 0.545, g 0.194) | 0.520 ± 0.046 (cost 0.904, g 0.068) | +0.053 | +0.359 | the model change alone (same v0 harness; 3 vs 5 episodes) |
| #12 v0 → #12 best (v4) | 0.520 ± 0.046 (cost 0.904, g 0.068) | 0.600 ± 0.114 (cost 0.856, g 0.172) | +0.080 | -0.048 | the evolve loop on the new model |
| #9 best (rescored, v2) → #12 best (v4) | 0.714 ± 0.081 (cost 0.546, g 0.441) | 0.600 ± 0.114 (cost 0.856, g 0.172) | -0.114 | +0.309 | model + harness changes together |

"Best" = highest mean goal progress (ties → higher gate score). #12's final parent (what the gate kept) is v3; #9's was v2.
