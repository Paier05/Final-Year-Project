"""Offline checks for the meta harness: `python -m evolve.selftest`.

No model calls. Uses a stub episode played on the real ls20 environment, then
drives Validate through every drop path it has, so a regression in the gate
that guards the evolved harness is caught before it costs a run.
"""

from __future__ import annotations

import os
import tempfile

from evolve.action_loop import read_records, run_episode
from evolve.edits import EditError, Workspace, apply_edit, normalise
from evolve.replay import make_env
from evolve.sandbox import Sandbox
from evolve.score import gate
from evolve.seed_v0 import build_v0
from evolve.stub import HELPER, StubPlayer
from evolve.validate import validate

CFG = {
    "game": "ls20-9607627b",
    "budget": {"actions_per_turn": 6, "max_actions": 40, "max_turns": 25, "max_resets": 10,
               "wall_clock_s": 600, "max_tokens_per_episode": 10**9, "cell_time_limit_s": 10},
    "observation": {"max_objects": 40, "history_n": 10},
    "validate": {"max_system_chars": 14000, "max_prompt_chars": 3000, "min_steps": 3,
                 "max_steps": 10, "max_step_chars": 400, "max_skill_lines": 80,
                 "test_state_fractions": [0.0, 0.5, 0.9]},
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


def gate_rule() -> None:
    print("gate")
    parent = {"score_mean": 0.20, "score_worst": 0.10}
    check(gate({"score_mean": 0.25, "score_worst": 0.05}, parent, 0.1)["decision"] == "accepted",
          "gain with a drop inside delta is accepted")
    check(gate({"score_mean": 0.25, "score_worst": -0.05}, parent, 0.1)["decision"] == "rejected",
          "gain with a drop beyond delta is rejected")
    check(gate({"score_mean": 0.20, "score_worst": 0.30}, parent, 0.1)["decision"] == "rejected",
          "zero gain is rejected")


def validation_paths() -> None:
    print("validate (stub episode on the live ls20 env)")
    v0 = build_v0()
    root = tempfile.mkdtemp(prefix="evolve_selftest_")
    outcome = run_episode(env=make_env(CFG["game"]), client=StubPlayer(seed=3), harness=v0,
                          round_index=0, episode=0, cfg=CFG,
                          traj_root=os.path.join(root, "t"), frame_root=os.path.join(root, "f"),
                          log=lambda _m: None)
    episodes = [{"episode": 0, "records": read_records(outcome.trajectory)}]
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
        # passes: plain text edit
        {"op": "add", "target": "prompt", "name": "strategy", "content": "STRATEGY\n- be brief.",
         "source": "meta"},
    ]
    _child, passed, dropped, info = validate(v0, edits, episodes, CFG, "vT", 1, log=lambda _m: None)
    passed_ids = {p["id"] for p in passed}
    reasons = {d["id"]: (d["stage"], d["reason"]) for d in dropped}
    check(info["fidelity"][0]["first_divergence"] is None, "parent replay reproduces the stub episode")
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
    check("r1-e11" in passed_ids, "a plain prompt add passes")


def main() -> None:
    sandbox_rules()
    edit_semantics()
    gate_rule()
    validation_paths()
    print("all self-tests passed")


if __name__ == "__main__":
    main()
