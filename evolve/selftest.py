"""Offline checks for the meta harness: `python -m evolve.selftest`.

No model calls. Uses a stub episode played on the real ls20 environment, then
drives Validate through every drop path it has, so a regression in the gate
that guards the evolved harness is caught before it costs a run.

#12 adds: the goal-progress score on hand-built states and on logged vs
replayed states, the cost-aware gate with its tie-break, the fact-check's
checker on known true and false ls20 claims (several are the false beliefs #9
wrote into its harness), parallel-env isolation, and the fact-check stage
inside Validate.
"""

from __future__ import annotations

import os
import tempfile
import threading

from evolve.action_loop import EpisodeAPI, read_records, run_episode
from evolve.edits import EditError, Workspace, apply_edit, normalise
from evolve.factcheck import FactChecker, check_claim, ground_truth, make_skill_runner, observed_moves
from evolve.goal_score import level1_maze, read_state, score_states, states_by_replay, states_from_records
from evolve.harness import Harness
from evolve.replay import make_env, states_along
from evolve.sandbox import Sandbox
from evolve.score import gate
from evolve.seed_v0 import build_v0
from evolve.stub import HELPER, StubExtractor, StubPlayer
from evolve.validate import validate

GAME = "ls20-9607627b"
CFG = {
    "game": GAME,
    "seeds": [1, 2],
    "budget": {"actions_per_turn": 6, "max_actions": 40, "max_turns": 25, "max_resets": 10,
               "wall_clock_s": 600, "max_tokens_per_episode": 10**9, "cell_time_limit_s": 10},
    "observation": {"max_objects": 40, "history_n": 10},
    "validate": {"max_system_chars": 14000, "max_prompt_chars": 3000, "min_steps": 3,
                 "max_steps": 10, "max_step_chars": 400, "max_skill_lines": 80,
                 "test_state_fractions": [0.0, 0.5, 0.9]},
    "score": {"weights": {"position": 0.4, "rotation": 0.4, "shape": 0.1, "colour": 0.1}},
    "gate": {"delta": 0.1, "lambda": 0.5, "epsilon": 0.05},
    "factcheck": {"enabled": True, "max_tokens": 6000},
}


def check(condition: bool, label: str) -> None:
    print(f"  {'ok  ' if condition else 'FAIL'} {label}")
    if not condition:
        raise SystemExit(f"self-test failed: {label}")


def sandbox_rules() -> None:
    print("sandbox")
    box = Sandbox(time_limit_s=1.0)
    check(box.run("while True:\n    pass").timed_out, "infinite loop is stopped")
    check(box.run("try:\n    while True: pass\nexcept Exception:\n    pass").timed_out,
          "timeout cannot be swallowed by except Exception")
    for source, label in (
        ("print(().__class__)", "dunder attribute"),
        ("g = (i for i in [1]); g.gi_frame", "generator frame"),
        ("import os", "import os"),
        ("open('x')", "open"),
        ("np.random.rand()", "unseeded randomness"),
        ("try:\n    pass\nexcept:\n    pass", "bare except"),
    ):
        check(box.run(source).violation, f"refused: {label}")


def edit_semantics() -> None:
    print("edits")
    ws = Workspace.from_parent(build_v0(), "t", 1)
    original = list(ws.harness.steps)
    # Indices are the parent's numbering even after earlier edits shift positions.
    apply_edit(ws, normalise({"op": "add", "target": "step", "index": 1, "content": "NEW FIRST"}, "meta"))
    apply_edit(ws, normalise({"op": "delete", "target": "step", "index": 2}, "meta"))
    apply_edit(ws, normalise({"op": "edit", "target": "step", "index": 6, "content": "LAST"}, "meta"))
    check(ws.harness.steps[0] == "NEW FIRST", "add step before parent step 1")
    check(original[1] not in ws.harness.steps, "delete hits parent step 2, not the shifted one")
    check(ws.harness.steps[-1] == "LAST", "edit hits parent step 6")
    for bad, label in (
        ({"op": "delete", "target": "prompt", "name": "format"}, "core prompt delete"),
        ({"op": "add", "target": "skill", "name": "action", "content": "def action(): pass"}, "reserved name"),
        ({"op": "edit", "target": "step", "index": 2, "content": "x"}, "edit of a deleted step"),
        ({"op": "frobnicate", "target": "skill"}, "unknown op"),
    ):
        try:
            apply_edit(ws.clone(), normalise(bad, "meta"))
            check(False, f"rejected: {label}")
        except EditError:
            check(True, f"rejected: {label}")


def goal_score_rules() -> None:
    print("goal-progress score (#12)")
    maze = level1_maze(GAME)
    check((maze.start_moves, maze.distances(maze.start).get((19, 30))) == (7, 6),
          "maze: start->goal 7 moves, start->switch 6")
    w = CFG["score"]["weights"]

    def state(x, y, rotation):
        return {"level": 0, "x": x, "y": y, "rotation": rotation, "shape": 5, "colour": 1, "action_index": 0,
                "goals": [{"x": 34, "y": 10, "rotation": 0, "shape": 5, "colour": 1, "done": False}]}

    cases = [
        ([state(34, 45, 3)], 0.2, "start (shape, colour already match)"),
        ([state(34, 15, 3)], 0.2 + 0.4 * 6 / 7, "under the goal, wrong rotation"),
        ([state(19, 30, 0)], 0.6, "rotated, at the switch (7 moves from the goal)"),
        ([state(34, 15, 0)], 0.6 + 0.4 * 6 / 7, "rotated, under the goal"),
    ]
    for states, want, label in cases:
        got = score_states(states, False, maze, w)["score"]
        check(abs(got - round(want, 4)) < 1e-4, f"{label}: {got:.4f}")
    # The best JOINT state counts: rotated at one time and near at another is
    # only worth the better of the two.
    split = score_states([state(34, 45, 3), state(19, 30, 0), state(34, 15, 3)], False, maze, w)
    check(abs(split["score"] - 0.6) < 1e-4 and split["failing_parts"] == ["position"],
          "rotated-then-unrotated-near scores the best single state (0.6), not a mix")
    check(score_states([state(34, 45, 3)], True, maze, w)["score"] == 1.0, "a clear scores 1.0")


def gate_rule() -> None:
    print("gate (cost-aware, #12)")
    def v(progress, cost, worst_g=None):
        g = progress - 0.5 * cost
        return {"score_mean": progress, "cost_mean": cost, "gate_mean": g,
                "gate_worst": g if worst_g is None else worst_g}
    parent = v(0.50, 0.60)
    cases = [
        (v(0.60, 0.60), "accepted", "progress gain beyond eps, same cost"),
        (v(0.60, 0.90), "rejected", "progress gain eaten by cost (g falls)"),
        (v(0.52, 0.50), "accepted", "tie on progress (within 0.05), child cheaper"),
        (v(0.52, 0.70), "rejected", "tie on progress, child dearer"),
        (v(0.50, 0.60), "rejected", "exact tie, same cost"),
        (v(0.70, 0.60, worst_g=0.0), "rejected", "gain but worst episode drops > delta"),
    ]
    for child, want, label in cases:
        got = gate(child, parent, CFG)
        check(got["decision"] == want, f"{label}: {got['decision']} ({got['reason']})")


def factcheck_rules() -> None:
    print("fact-check checker (#12; no model: the claims are hand-written)")
    truth = ground_truth(GAME)
    check(truth.moves == {1: (-5, 0), 2: (5, 0), 3: (0, -5), 4: (0, 5)}, "probe: ACTION1-4 move 5 cells u/d/l/r")
    cases = [
        ({"kind": "move", "action": None, "cells": 1, "unit": "cells"}, "false", "#9: 'Moves 1 cell per action'"),
        ({"kind": "move", "action": 1, "direction": "up", "cells": 5, "unit": "cells"}, "true", "ACTION1 = up 5 cells"),
        ({"kind": "move", "action": 2, "direction": "none"}, "false", "ACTION2 does nothing"),
        ({"kind": "move", "action": 3, "direction": "left", "cells": 1, "unit": "unclear"}, "true",
         "ACTION3 = left (size in unclear units: direction only)"),
        ({"kind": "colour_role", "colour": "lime", "role": "player"}, "false", "#9: 'the player is the lime bar'"),
        ({"kind": "colour_role", "colour": "teal", "role": "player"}, "true", "the player is teal"),
        ({"kind": "colour_role", "colour": "lime", "role": "step_counter"}, "true", "the lime bar counts moves"),
        ({"kind": "colour_role", "colour": "maroon", "role": "collectible"}, "false", "#9: 'maroon = collectible'"),
        ({"kind": "colour_role", "colour": "cyan", "role": "hazard"}, "false", "#9: 'cyan = deadly obstacles'"),
        ({"kind": "colour_role", "colour": "green", "role": "trail"}, "false", "#9: 'green = trail'"),
        ({"kind": "colour_role", "colour": "green", "role": "wall"}, "false", "#9: 'green can block movement'"),
        ({"kind": "colour_role", "colour": "grey", "role": "wall"}, "unverifiable", "grey is a wall (grey is also UI)"),
        ({"kind": "location", "object": "player", "rows": [61, 62]}, "false", "#9: 'player at rows 61-62'"),
        ({"kind": "location", "object": "goal", "region": "top"}, "true", "the goal is at the top"),
        ({"kind": "location", "object": "goal", "region": "bottom-left"}, "false", "the goal is bottom-left"),
        ({"kind": "location", "object": "collectible", "rows": [11, 13]}, "false", "#9: 'maroon items at rows 11-13'"),
        ({"kind": "goal_requirement", "requires": ["collect"]}, "false", "#9: 'goal: collect all maroon items'"),
        ({"kind": "goal_requirement", "requires": ["position", "rotation"]}, "true", "stand on the goal, rotated"),
        ({"kind": "rotation_cause", "cause": "action", "action": 5}, "false", "an action rotates the player"),
        ({"kind": "rotation_cause", "cause": "touch", "rows": [30, 34], "cols": [19, 23]}, "true",
         "touching the switch at rows 30-34, cols 19-23 rotates"),
        ({"kind": "count", "what": "lives", "value": 3}, "true", "3 lives"),
        ({"kind": "count", "what": "moves_per_life", "value": 20}, "false", "20 moves per life"),
        ({"kind": "other"}, "unverifiable", "anything else"),
    ]
    for claim, want, label in cases:
        got, evidence = check_claim(claim, truth, {})
        check(got == want, f"{label}: {got} ({evidence[:70]})")

    # skill_output runs the skill on replayed states and compares positions.
    lime = ('def where_player():\n    """Player = the lime cells (#9\'s belief)."""\n'
            '    import numpy as np\n    rs, cs = np.nonzero(grid() == 11)\n'
            '    return (float(rs.mean()), float(cs.mean()))\n')
    teal = lime.replace("== 11", "== 12").replace("the lime cells (#9\\'s belief)", "the teal cells")
    harness = Harness("t", None, 0, {"system": "s", "format": "```python"}, ["a", "b", "c"],
                      {"where_player": lime})
    states = [("start", []), ("after 3 actions", [("ACTION1", {}), ("ACTION1", {}), ("ACTION3", {})])]
    label, _ = make_skill_runner(harness, states, CFG)("where_player", "player_position")
    check(label == "false", "a skill that finds the player by lime returns the wrong place: false")
    harness.skills["where_player"] = teal
    label, _ = make_skill_runner(harness, states, CFG)("where_player", "player_position")
    check(label == "true", "the same skill looking for teal: true")


def parallel_isolation() -> None:
    print("parallel episodes share no state (#12)")
    sequences = {1: [1, 1, 3, 3, 1, 4] * 4, 2: [4, 4, 1, 1, 2, 3] * 4, 3: [1] * 10 + [3] * 5}

    def play(seed, out):
        api = EpisodeAPI(make_env(GAME, seed=seed), 10**9, 10**9, 10**9, probe=read_state)
        states = []
        for a in sequences[seed]:
            api.begin_turn(0)
            api.action(a)
            states.append(api.turn_actions[-1]["game_state"])
        out[seed] = (states, [f.tobytes() for f in api.frames])

    parallel: dict[int, list] = {}
    threads = [threading.Thread(target=play, args=(s, parallel)) for s in sequences]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    serial: dict[int, list] = {}
    for s in sequences:
        play(s, serial)
    check(all(parallel[s] == serial[s] for s in sequences), "3 envs stepped at once give the frames each gives alone")


def validation_paths() -> None:
    print("validate (stub episode on the live ls20 env)")
    v0 = build_v0()
    root = tempfile.mkdtemp(prefix="evolve_selftest_")
    outcome = run_episode(env=make_env(GAME), client=StubPlayer(seed=3), harness=v0,
                          round_index=0, episode=3, cfg=CFG,
                          traj_root=os.path.join(root, "t"), frame_root=os.path.join(root, "f"),
                          log=lambda _m: None, probe=read_state)
    records = read_records(outcome.trajectory)
    check(os.path.basename(outcome.trajectory) == "seed_3.jsonl" and records[0]["seed"] == 3,
          "trajectory is named and tagged by seed")
    check(all("llm_calls" in r and "wall_time_s" in r for r in records if r.get("type") == "tool_call"),
          "every tool call records its cost")
    logged, _ = states_from_records(records)
    replayed, _ = states_by_replay(records, GAME)
    check(logged == replayed, f"logged game states equal states rebuilt by replay ({len(logged)} states)")
    episodes = [{"episode": 3, "records": records}]
    check(sum(observed_moves(episodes).get("ACTION1", {}).values()) > 0, "observed moves read from logged states")

    dup = v0.skills["player_detector"].replace("def player_detector", "def find_player", 1)
    edits = [
        # passes: helper promotion, replay must exercise it
        {"op": "add", "target": "skill", "name": "mover_centre", "content": HELPER, "source": "rule",
         "replay_strip": [["mover_centre", None]]},
        # fails replay: player_detector is called by the stub
        {"op": "delete", "target": "skill", "name": "player_detector", "source": "rule"},
        # passes: an exact duplicate merged into the original is behaviour-equivalent
        {"op": "add", "target": "skill", "name": "find_player", "content": dup, "source": "rule"},
        {"op": "merge", "target": "skill", "names": ["player_detector", "find_player"],
         "name": "player_detector", "content": v0.skills["player_detector"], "source": "rule"},
        # fails merge-equivalence: the merged body behaves differently
        {"op": "merge", "target": "skill", "names": ["player_detector", "grid_region"],
         "name": "player_detector", "content": 'def player_detector(g=None):\n    """Broken."""\n    return []\n',
         "source": "meta", "test": "player_detector()"},
        # fails the skill test
        {"op": "add", "target": "skill", "name": "always_wrong",
         "content": 'def always_wrong():\n    """Returns 1."""\n    return 1\n',
         "test": "assert always_wrong() == 2", "source": "meta"},
        # fails: meta skill without a test
        {"op": "add", "target": "skill", "name": "untested",
         "content": 'def untested():\n    """No test."""\n    return 1\n', "source": "meta"},
        # fails replay: the edited skill now raises where the parent did not
        {"op": "edit", "target": "skill", "name": "player_detector",
         "content": 'def player_detector(g=None):\n    """Raises."""\n    raise ValueError("boom")\n',
         "test": "1", "source": "meta"},
        # fails static: no docstring
        {"op": "add", "target": "skill", "name": "nodoc", "content": "def nodoc():\n    return 1\n",
         "test": "nodoc()", "source": "meta"},
        # fails static: format prompt must keep the python block
        {"op": "edit", "target": "prompt", "name": "format", "content": "Reply in JSON.", "source": "meta"},
        # passes, flagged: the stub extractor calls its strategy line uncheckable
        {"op": "add", "target": "prompt", "name": "strategy", "content": "STRATEGY\n- Stub strategy line.",
         "source": "meta"},
        # fails the fact-check: moves are 5 cells
        {"op": "add", "target": "prompt", "name": "facts",
         "content": "FACTS\n- ACTION1 moves the player up 1 cell.", "source": "meta"},
        # passes the fact-check: true claim
        {"op": "add", "target": "prompt", "name": "facts2",
         "content": "FACTS\n- ACTION4 moves the player right 5 cells.", "source": "meta"},
    ]
    checker = FactChecker(CFG, StubExtractor(), episodes)
    _child, passed, dropped, info = validate(v0, edits, episodes, CFG, "vT", 1, log=lambda _m: None,
                                             factchecker=checker)
    passed_ids = {p["id"] for p in passed}
    by_id = {p["id"]: p for p in passed}
    reasons = {d["id"]: (d["stage"], d["reason"]) for d in dropped}
    check(info["fidelity"][3]["first_divergence"] is None, "parent replay reproduces the stub episode")
    check("r1-e1" in passed_ids, "helper promotion passes and is exercised")
    check(reasons.get("r1-e2", ("",))[0] == "replay", "deleting a used skill fails replay")
    check({"r1-e3", "r1-e4"} <= passed_ids, "merging an exact duplicate passes merge-equivalence")
    check(reasons.get("r1-e5", ("", ""))[1].startswith("merge is not behaviour-equivalent"),
          "a behaviour-changing merge fails merge-equivalence")
    check(reasons.get("r1-e6", ("",))[0] == "skill test", "a failing skill test drops the edit")
    check(reasons.get("r1-e7", ("", ""))[1] == "no test snippet provided", "an untested meta skill is dropped")
    check(reasons.get("r1-e8", ("", ""))[1].startswith("edited skill raises"), "an edit that raises is dropped")
    check(reasons.get("r1-e9", ("", ""))[1].startswith("skill has no docstring"), "missing docstring is dropped")
    check(reasons.get("r1-e10", ("",))[0] == "static tests", "breaking the reply format is dropped")
    check("r1-e11" in passed_ids and by_id["r1-e11"]["factcheck"]["verdict"] == "unverifiable",
          "an uncheckable claim keeps the edit, flagged unverifiable")
    stage, reason = reasons.get("r1-e12", ("", ""))
    check(stage == "fact-check", "a false claim drops the edit at the fact-check")
    check("5 cells" not in reason and "1 cell" in reason,
          f"the Meta-facing reason names the false claim but not the truth: {reason!r}")
    check("r1-e13" in passed_ids and by_id["r1-e13"]["factcheck"]["verdict"] == "true", "a true claim passes")


def main() -> None:
    sandbox_rules()
    edit_semantics()
    goal_score_rules()
    gate_rule()
    factcheck_rules()
    parallel_isolation()
    validation_paths()
    print("all self-tests passed")


if __name__ == "__main__":
    main()
