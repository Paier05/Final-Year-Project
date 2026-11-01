# Work Log — Issue #9: 5-generation evo-harness run on ls20 (level 1 only) with Qwen3.8-27B

**Issue:** https://github.com/Paier05/Final-Year-Project/issues/9
**Branch:** `experiment/9-evo-harness-ls20-5-rounds`
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
