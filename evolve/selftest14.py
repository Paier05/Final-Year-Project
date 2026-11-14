"""Offline checks for issue #14, run by `python -m evolve.selftest`.

No model calls: scripted and stub players on the real ls20 environment.

1. skill-name check in Validate: a prompt naming a missing skill is rejected;
   a delete or a rename (merge) that leaves the old name behind is rejected;
   an edit naming only existing skills passes.
2. frame evidence in Analyze: the reported path equals the known positions
   and blocked moves are reported; stepping on the switch gives one rare
   change in the bottom-left corner linked to the switch cell; without it,
   movement is reported and no rare change; the regular per-step change is
   summarised, not listed as events.
3. rotation part of the score: held vs goal rotation by cyclic distance.
4. checkpoint and resume: a run killed in the middle of an episode resumes
   with every seed exactly once; a run cut in the middle of a meta stage
   completes that stage once; resuming a finished run does nothing. Plus the
   time guard, the lock and (on POSIX) SIGUSR1.
5. leak test: none of the ground-truth facts appear in v0, in the hand-written
   prompt and report templates, or in a full Meta LLM input.
6. trajectories hold one frame per step.

The ground-truth facts used here (where the switch is, where the icon is, the
rotation values) are read from the game at test time or written below. Tests
are one of the three places the issue allows them.
"""

from __future__ import annotations

import copy
import inspect
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from typing import Any

import yaml

from evolve import analyze as analyze_mod
from evolve import frame_evidence, loop, skill_names
from evolve.action_loop import load_frames, read_records, run_episode
from evolve.checkpoint import STATE_FILE, Checkpoint, LockError, RunLock, StopRun, read_json
from evolve.goal_score import (
    GOAL_ROTATION, ROTATION, level1_maze, read_state, score_states, states_from_records, touches_needed,
)
from evolve.harness import API_DOC
from evolve.propose import META_SYSTEM, meta_messages
from evolve.replay import make_env
from evolve.seed_v0 import build_v0
from evolve.stub import ScriptedPlayer, StubExtractor, StubMeta, StubPlayer
from evolve.validate import validate

GAME = "ls20-9607627b"

# Ground truth for the tests (ls20 Level 1). Positions are (row, col) of the
# block's top-left cell.
SWITCH_CELL = (30, 19)
ICON_AROUND = (55, 3)           # the issue: "around row 55, column 3"
START_ROTATION, GOAL_ROTATION_VALUE = 3, 0
# From the start: up x4, left x3, down x1 lands on the switch at step 8.
TO_SWITCH = [1, 1, 1, 1, 3, 3, 3, 2]
# Up x3, a left into a wall (blocked), up x3 to under the goal, an up into
# the goal (blocked). Never near the switch.
NO_SWITCH = [1, 1, 1, 3, 1, 1, 1, 1]


def check(condition: bool, label: str) -> None:
    print(f"  {'ok  ' if condition else 'FAIL'} {label}")
    if not condition:
        raise SystemExit(f"self-test failed: {label}")


def base_cfg() -> dict[str, Any]:
    """The run's config with the stub run's small budgets."""
    with open("config_evolve.yaml", encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle)
    cfg["budget"] |= {"max_actions": 40, "max_turns": 30}
    cfg["meta"]["max_edits"] = 8
    return cfg


def scripted_episode(actions: list[int], root: str, seed: int = 1) -> dict[str, Any]:
    cfg = base_cfg()
    cfg["budget"] |= {"max_actions": len(actions) + 6, "max_turns": -(-len(actions) // 6)}
    outcome = run_episode(
        env=make_env(GAME, seed=seed), client=ScriptedPlayer(actions), harness=build_v0(), round_index=0,
        episode=seed, seed=seed, cfg=cfg, traj_root=os.path.join(root, "t"),
        frame_root=os.path.join(root, "f"), log=lambda _m: None, probe=read_state,
    )
    records = read_records(outcome.trajectory)
    return {"seed": seed, "episode": seed, "records": records, "frames": load_frames(outcome.frames),
            "trajectory": outcome.trajectory, "frames_path": outcome.frames,
            "actions": [a for r in records if r.get("type") == "tool_call" for a in r.get("actions") or []]}


# ---------------------------------------------------------------------------
# 1. skill-name check
# ---------------------------------------------------------------------------


def skill_name_check() -> None:
    print("skill-name check in Validate (#14, fix 1)")
    v0 = build_v0()
    check(skill_names.check_harness(v0) == [], "audit: v0 names no missing skill")
    refs = skill_names.prose_references("Use `find_goal` or call scan(g); see objects() and skill(s). `x = foo(1)`")
    check([name for name, _l in refs] == ["find_goal", "foo", "scan", "objects"],
          f"prose references: backticked identifiers and call-like text, not 'skill(s)': {refs}")

    cfg = base_cfg()
    cfg["budget"] |= {"max_turns": 25}
    root = tempfile.mkdtemp(prefix="evolve_names_")
    outcome = run_episode(env=make_env(GAME), client=StubPlayer(seed=3), harness=v0, round_index=0, episode=3,
                          cfg=cfg, traj_root=os.path.join(root, "t"), frame_root=os.path.join(root, "f"),
                          log=lambda _m: None, probe=read_state)
    episodes = [{"episode": 3, "records": read_records(outcome.trajectory)}]
    dup = v0.skills["player_detector"].replace("def player_detector", "def find_player", 1)
    count_cells = ('def count_cells(c, g=None):\n    """Number of cells of colour c."""\n'
                   '    g = grid() if g is None else np.asarray(g)\n    return int((g == c).sum())\n')
    edits = [
        # 1 rejected: a step that names a skill that does not exist
        {"op": "edit", "target": "step", "index": 4, "source": "meta",
         "content": "PLAN: call find_goal() to get the target, then move toward it."},
        # 2 passes: names only existing skills and API functions
        {"op": "add", "target": "prompt", "name": "tips", "source": "meta",
         "content": "TIPS\n- Use bfs_to_target() to measure distances.\n- `grid_region` shows raw cells; objects() lists them."},
        # 3 rejected: a delete that leaves the old name in the prompt of edit 2
        {"op": "delete", "target": "skill", "name": "bfs_to_target", "source": "rule"},
        # 4, 5 pass: a duplicate skill, and a prompt naming it
        {"op": "add", "target": "skill", "name": "find_player", "content": dup, "source": "rule"},
        {"op": "add", "target": "prompt", "name": "tips2", "source": "meta",
         "content": "MORE TIPS\n- Start with `find_player`."},
        # 6 rejected: a rename (merge into player_detector) that leaves `find_player` in tips2
        {"op": "merge", "target": "skill", "names": ["player_detector", "find_player"],
         "name": "player_detector", "content": v0.skills["player_detector"], "source": "rule"},
        # 7 passes on the retry: names a skill that edit 8 of the same set adds
        {"op": "add", "target": "prompt", "name": "tips3", "source": "meta",
         "content": "COUNTING\n- count_cells(c) counts the cells of one colour."},
        {"op": "add", "target": "skill", "name": "count_cells", "content": count_cells, "source": "meta",
         "test": "assert count_cells(4) >= 0"},
        # 9 rejected: skill code that calls a skill that does not exist
        {"op": "add", "target": "skill", "name": "uses_missing", "source": "meta", "test": "1",
         "content": 'def uses_missing():\n    """Calls a helper nobody defined."""\n    return locate_target()\n'},
    ]
    _child, passed, dropped, info = validate(v0, edits, episodes, cfg, "vT", 1, log=lambda _m: None)
    passed_ids = [p["id"] for p in passed]
    reasons = {d["id"]: d for d in dropped}

    first = reasons.get("r1-e1", {})
    check(first.get("stage") == "skill-name check", "a step that names a missing skill is rejected")
    check("`find_goal`" in first.get("reason", "") and "steps.json[4] line 1" in first.get("reason", ""),
          f"the reason gives the missing name, the file and the line: {first.get('reason')!r}")
    third = reasons.get("r1-e3", {})
    check(third.get("stage") == "skill-name check"
          and third["missing_names"][0] | {"text": ""} == {"name": "bfs_to_target", "file": "prompts.json[tips]",
                                                           "line": 2, "where": "prompt", "text": ""},
          "a delete that leaves the skill's name in a prompt is rejected, with file and line")
    sixth = reasons.get("r1-e6", {})
    check(sixth.get("stage") == "skill-name check" and sixth["missing_names"][0]["name"] == "find_player"
          and sixth["missing_names"][0]["file"] == "prompts.json[tips2]",
          "a rename (merge) that leaves the old name in a prompt is rejected")
    check({"r1-e2", "r1-e4", "r1-e5"} <= set(passed_ids), "edits that name only existing skills pass")
    check({"r1-e7", "r1-e8"} <= set(passed_ids) and passed_ids.index("r1-e8") < passed_ids.index("r1-e7"),
          "text may name a skill added later in the same edit set (held, then passed)")
    ninth = reasons.get("r1-e9", {})
    check(ninth.get("stage") == "skill-name check" and ninth["missing_names"][0]["where"] == "skill code",
          "skill code that calls a missing skill is rejected (found by parsing the code)")
    names = info["skill_names"]
    check(names["edits_checked"] == 9 and names["edits_rejected"] == 4 and names["missing_in_child"] == [],
          f"the round's record: {names['edits_checked']} checked, {names['edits_rejected']} rejected, "
          "child harness clean")


# ---------------------------------------------------------------------------
# 2. frame evidence   3. rotation score   6. frames per step
# ---------------------------------------------------------------------------


def _known_positions(episode: dict[str, Any]) -> list[list[int]]:
    return [[a["game_state"]["y"], a["game_state"]["x"]] for a in episode["actions"]]


def frame_evidence_checks() -> tuple[dict[str, Any], dict[str, Any]]:
    print("frame evidence in Analyze (#14, fix 2)")
    root = tempfile.mkdtemp(prefix="evolve_frames_")
    plain = scripted_episode(NO_SWITCH, os.path.join(root, "plain"))
    switch = scripted_episode(TO_SWITCH, os.path.join(root, "switch"))

    # -- known positions; blocked moves ------------------------------------
    evidence = frame_evidence.build([plain])
    steps = evidence["per_step"]
    check([s["block_after"] for s in steps] == _known_positions(plain),
          f"the block's position after every step equals the game's own ({len(steps)} steps)")
    start = plain["records"][0]["start_state"]
    known_path = [[start["y"], start["x"]]]
    for position in _known_positions(plain):
        if position != known_path[-1]:
            known_path.append(position)
    check(evidence["episodes"][0]["path"] == known_path, f"the reported path matches: {known_path}")
    check([s["move"] for s in steps] == ["moved"] * 3 + ["blocked"] + ["moved"] * 3 + ["blocked"],
          "the two moves that changed no position are reported as blocked")
    check(evidence["episodes"][0]["blocked"] == 2 and evidence["episodes"][0]["final"] == known_path[-1],
          "per episode: blocked count and final position")

    # -- no switch: movement, no rare change; the regular change is summarised --
    check(evidence["episodes"][0]["moved"] == 6 and evidence["rare_events"] == []
          and evidence["moved_without_rare_change"] == [1],
          "never on the switch: movement is reported and there is no rare change")
    regular = [r for r in evidence["regions"] if r["kind"] == "regular"]
    text = frame_evidence.render(evidence, "vT")
    check(len(regular) == 1 and regular[0]["steps_changed"] == 7 and "- regular: rows" in text
          and "- rare: none" in text,
          f"the per-step change (rows {regular[0]['rows']}, cols {regular[0]['cols']}, on 7 of 7 changing "
          "steps) is one summary line, not events")

    # -- on the switch: one rare change, bottom-left, linked to the switch cell --
    touched = frame_evidence.build([switch])
    events = touched["rare_events"]
    check(len(events) == 1 and events[0]["step"] == len(TO_SWITCH),
          f"stepping on the switch gives one rare change, at that step (step {events[0]['step'] if events else '-'})")
    event = events[0]
    rows, cols = event["rows"], event["cols"]
    check(abs((rows[0] + rows[1]) / 2 - ICON_AROUND[0]) <= 4 and abs(cols[0] - ICON_AROUND[1]) <= 2
          and rows[0] >= 48 and cols[1] <= 15,
          f"it is in the bottom-left corner, around row 55, column 3 (rows {rows}, cols {cols})")
    link = touched["links"][0]["after_block_entered_cell"]
    check(event["block_after"] == list(SWITCH_CELL) and event["block_move"] == "moved"
          and link == [{"cell": list(SWITCH_CELL), "times_entered": 1, "times_change_followed": 1}],
          f"it is linked to the block's position on the switch cell {SWITCH_CELL}: entered once, followed once")
    check(event["values_before"] != event["values_after"] and "cell_stepped_onto_before" in event,
          "the event carries the region's cell values before and after, and what the stepped-on cell held")

    # -- rules: observations only -------------------------------------------
    for label, section in (("no rare change", text), ("with a rare change", frame_evidence.render(touched, "vT"))):
        words = re.findall(r"\b(rotat\w*|switch\w*|goal\w*|should|must|try|recommend\w*)\b", section, re.IGNORECASE)
        check(not words, f"the section ({label}) has none of the words rotation / switch / goal and no advice")
    both = frame_evidence.build([dict(plain, seed=1), dict(switch, seed=2)])
    check(both["moved_without_rare_change"] == [1] and [e["seed"] for e in both["rare_events"]] == [2],
          "across episodes: the episode with no rare change is listed, the event keeps its seed")
    section = analyze_mod.frame_evidence_section("vT", [
        {"seed": 1, "episode": 1, "records": plain["records"], "frames": plain["frames_path"],
         "trajectory": plain["trajectory"]}])
    table = section["per_step_files"][0]
    with open(table, encoding="utf-8") as handle:
        lines = handle.read().splitlines()
    check(os.path.dirname(table) == os.path.dirname(plain["trajectory"]) and len(lines) == 1 + len(NO_SWITCH)
          and "per_step" not in section and section["text"].startswith("FRAME EVIDENCE"),
          "the full per-step table is a file next to the trajectory; the report keeps the summaries")
    return plain, switch


def rotation_score_checks(plain: dict[str, Any], switch: dict[str, Any]) -> None:
    print("rotation part of the score (#14, fix 3)")
    check([touches_needed(h, GOAL_ROTATION_VALUE) for h in (3, 0, 1, 2)] == [1, 0, 3, 2],
          "touches still needed = (goal - held) mod 4: held 3 -> 1, 0 -> 0, 1 -> 3, 2 -> 2")
    env = make_env(GAME)
    env.reset()
    game = env._game
    state = read_state(env)
    check(state["rotation"] == getattr(game, ROTATION) == START_ROTATION
          and state["goals"][0]["rotation"] == getattr(game, GOAL_ROTATION)[0] == GOAL_ROTATION_VALUE,
          "the scorer reads the two values the win check compares: held 3, goal 0 at the start")
    maze = level1_maze(GAME)
    check(maze.start_touches == 1, "Level 1 needs one touch from the start")
    weights = base_cfg()["score"]["weights"]

    def at(rotation: int) -> dict[str, Any]:
        return {"level": 0, "x": 19, "y": 30, "rotation": rotation, "shape": 5, "colour": 1, "action_index": 0,
                "goals": [{"x": 34, "y": 10, "rotation": 0, "shape": 5, "colour": 1, "done": False}]}

    scores = {r: score_states([at(r)], False, maze, weights) for r in (3, 0, 1)}
    check(scores[3]["parts"]["rotation"] == 0.0 and scores[0]["parts"]["rotation"] == 1.0,
          "rotation part: 0 with one touch needed, 1 with none")
    check(scores[1]["parts"]["rotation"] == 0.0 and scores[1]["score"] < scores[0]["score"]
          and scores[1]["ever"]["rotation_overshot"] and not scores[0]["ever"]["rotation_overshot"],
          f"a second touch overshoots (3 touches needed) and lowers the state's score: "
          f"{scores[0]['score']} -> {scores[1]['score']}")

    # On the live game: touch once, step off, touch again.
    root = tempfile.mkdtemp(prefix="evolve_rotation_")
    twice = scripted_episode(TO_SWITCH + [1, 2], root)
    held = [a["game_state"]["rotation"] for a in twice["actions"]]
    check(held[:7] == [3] * 7 and held[7] == 0 and held[9] == 1,
          f"live: the held index goes 3 -> 0 on the first touch and 0 -> 1 on the second ({held})")
    states, cleared = states_from_records(twice["records"])
    result = score_states(states, cleared, maze, weights)
    check(result["ever"]["first_rotation_match_action"] == 8 and result["ever"]["rotation_overshot"]
          and result["ever"]["first_rotation_overshoot_action"] == 10,
          "the episode record says when the rotation first matched and when it overshot")

    # The scorer must not depend on how the moving block looks: it never changes.
    patterns = {tuple(frame_evidence.build([e])["block"]["pattern"]) for e in (plain, switch, twice)}
    check(len(patterns) == 1, "the moving block looks the same before and after a touch (so it cannot be the signal)")
    # The corner icon does change with the held rotation: it is the on-screen copy of the value the scorer reads.
    events = frame_evidence.build([twice])["rare_events"]
    check([e["step"] for e in events] == [8, 10], "the corner icon changes exactly when the held index changes")


def frames_per_step(plain: dict[str, Any], switch: dict[str, Any]) -> None:
    print("trajectories hold one frame per step (#14)")
    for episode in (plain, switch):
        actions = episode["actions"]
        resets = sum(1 for a in actions if a.get("auto_reset_frame") is not None)
        ok = (len(episode["frames"]) == 1 + len(actions) + resets
              and all(a["frame_after"] == a["frame_before"] + 1 for a in actions))
        check(ok, f"{len(actions)} steps -> {len(episode['frames'])} frames (the start frame + one per step)")


# ---------------------------------------------------------------------------
# 5. leak test
# ---------------------------------------------------------------------------

# How the facts would look in text. Coordinates in either order and the usual
# spellings; the rotation values next to a word that says what they are.
LEAK_PATTERNS = {
    "the switch cell": [
        rf"\(?\b{SWITCH_CELL[0]}\s*,\s*{SWITCH_CELL[1]}\b\)?", rf"\(?\b{SWITCH_CELL[1]}\s*,\s*{SWITCH_CELL[0]}\b\)?",
        rf"row\s*{SWITCH_CELL[0]}\D{{1,12}}col(umn)?\s*{SWITCH_CELL[1]}\b",
        rf"rows\s*{SWITCH_CELL[0]}\s*-\s*{SWITCH_CELL[0] + 4}", rf"x\s*=\s*{SWITCH_CELL[1]}\b\D{{1,6}}y\s*=\s*{SWITCH_CELL[0]}\b",
    ],
    "the corner icon's coordinates": [
        rf"\(?\b{ICON_AROUND[0]}\s*,\s*{ICON_AROUND[1]}\b\)?", rf"row\s*{ICON_AROUND[0]}\D{{1,12}}col(umn)?\s*{ICON_AROUND[1]}\b",
        r"rows\s*5[0-9]\s*-\s*5[0-9]\s*,\s*cols\s*[0-9]\s*-\s*1?[0-9]\b", r"bottom[- ]left corner",
    ],
    "the start and goal rotation values": [
        r"(start|initial|held|current)\w*\s+(pattern\s+)?rotation\s*(index|value|step)?\s*(is|=|:|of)?\s*3\b(?![./\d])",
        r"(goal|target|required)\w*('s)?\s+(required\s+)?rotation\s*(index|value|step)?\s*(is|=|:|of)?\s*0\b(?![./\d])",
        r"rotation\s*(index|value)\s*(is|=|:|of)?\s*[0-3]\b(?![./\d])", r"\b3\s*(->|→|to)\s*0\b",
        r"touches?\s+(still\s+)?needed", r"rotation_touches", r"held_ind", r"\(goal\s*[-−]\s*held\)",
        r"cklxociuu|ehwheiwsk",
    ],
}


def _leaks(text: str) -> list[str]:
    found = []
    for fact, patterns in LEAK_PATTERNS.items():
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                found.append(f"{fact}: {match.group(0)!r}")
    return found


def leak_test() -> None:
    print("leak test: ground-truth facts stay out of v0, the templates and the Meta LLM's input (#14)")
    check(bool(_leaks("the switch is at (30, 19)")) and bool(_leaks("icon at rows 53-58, cols 1-6"))
          and bool(_leaks("the player starts at rotation index 3")) and bool(_leaks("goal rotation is 0")),
          "the scanner itself finds each kind of fact when it is there")
    v0 = build_v0()
    cfg = base_cfg()
    v0_text = "\n".join([v0.render_system(int(cfg["budget"]["actions_per_turn"])),
                         *v0.prompts.values(), *v0.steps, *v0.skills.values()])
    check(_leaks(v0_text) == [], "v0 (prompts, steps, skills, rendered system prompt): none")
    templates = {
        "Meta LLM system prompt (evolve/propose.py)": META_SYSTEM,
        "sandbox API text (evolve/harness.py)": API_DOC,
        "frame-evidence report code (evolve/frame_evidence.py)": inspect.getsource(frame_evidence),
        "Analyze (evolve/analyze.py)": inspect.getsource(analyze_mod),
        "skill-name check (evolve/skill_names.py)": inspect.getsource(skill_names),
    }
    for name, text in templates.items():
        check(_leaks(text) == [], f"{name}: none {_leaks(text) or ''}")

    # One full Meta LLM input, built the way the run builds it: evaluate v0
    # (scripted episodes that never touch the switch), Analyze, Propose's messages.
    root = tempfile.mkdtemp(prefix="evolve_leak_")
    cfg["seeds"] = [1, 2]
    cfg["budget"] |= {"max_actions": 20, "max_turns": 3}
    scripts = {1: NO_SWITCH, 2: [1, 4, 4, 3, 3, 3, 2, 2]}
    paths = loop.Paths(root, title="leak test")
    archive = loop.run(cfg, paths, 0, lambda seed: ScriptedPlayer(scripts[seed]), None, log=lambda _m: None)
    entry = archive["versions"][0]
    report = analyze_mod.analyze(v0, entry, archive["versions"])
    messages = meta_messages(report, v0, cfg)
    full = "\n\n".join(m["content"] for m in messages)
    check("FRAME EVIDENCE for v0" in full and "A. PLAYER MOVEMENT" in full,
          f"the Meta LLM's input carries the Frame evidence section ({len(full)} chars in all)")
    check(_leaks(full) == [], f"a full Meta LLM input: none {_leaks(full) or ''}")
    stored = json.dumps(report["frame_evidence"])
    check(_leaks(stored) == [], "the Analyze report's stored frame evidence: none")
    # The episode's scorer output holds the rotation values; it must stay out of what the Meta LLM reads.
    check("rotation_touches_needed" in json.dumps(entry["episodes"][0]["goal"]),
          "(the scorer's own record does hold the rotation values, so the scan above is not vacuous)")


# ---------------------------------------------------------------------------
# 4. checkpoint and resume
# ---------------------------------------------------------------------------


class _Killed(BaseException):
    """Stands in for the process being killed in the middle of a model call."""


def _stub_run(root: str, cfg: dict[str, Any], rounds: int, meta: Any = StubMeta, fact: Any = StubExtractor,
              ckpt: Checkpoint | None = None) -> dict[str, Any]:
    ckpt = ckpt or Checkpoint(root, cfg, log=lambda _m: None)
    try:
        archive = loop.run(cfg, loop.Paths(root, title="self-test"), rounds, lambda k: StubPlayer(seed=k),
                           meta, log=lambda _m: None, fact_factory=fact, ckpt=ckpt)
        ckpt.finish("finished", "all rounds done")
        return archive
    finally:
        ckpt.disarm()


def _units(state: dict[str, Any]) -> dict[tuple[int, str], int]:
    counts: dict[tuple[int, str], int] = {}
    for unit in state["completed"]:
        key = (unit["round"], unit.get("stage") or f"seed {unit['seed']}")
        counts[key] = counts.get(key, 0) + 1
    return counts


def _changelog_sections(root: str) -> list[str]:
    with open(os.path.join(root, "CHANGELOG.md"), encoding="utf-8") as handle:
        return [line.split(" (")[0] for line in handle if line.startswith("## ")]


def checkpoint_units() -> None:
    print("checkpoint: time guard and lock (#14, fix 4)")
    cfg = base_cfg()
    root = tempfile.mkdtemp(prefix="evolve_guard_")
    saved = os.environ.pop("SLURM_JOB_START_TIME", None)  # the fake clock below is the only clock
    try:
        now = [0.0]
        ckpt = Checkpoint(root, cfg, time_limit_s=360 * 60, stop_by_s=340 * 60, factor=1.5,
                          log=lambda _m: None, clock=lambda: now[0])
        ckpt.check_start("episode", "the first episodes")  # nothing seen yet: allowed
        ckpt.episode_done(0, 1, 100 * 60, [1])
        now[0] = 185 * 60
        ckpt.check_start("episode", "episodes")  # 155 min left >= 150 needed
        now[0] = 195 * 60
        try:
            ckpt.check_start("episode", "episodes")
            check(False, "an episode that will not fit is not started")
        except StopRun as stop:
            check("150 min" in stop.reason and "145 min left" in stop.reason,
                  f"an episode needing 100 min x 1.5 is not started with 145 min left: {stop.reason}")
        ckpt.check_start("analyze", "a stage")  # a short stage still fits
        now[0] = 340 * 60
        try:
            ckpt.check_start("analyze", "a stage")
            check(False, "nothing starts at the stop time")
        except StopRun:
            check(True, "nothing starts at the stop time (5 h 40 min)")
        ckpt.save()
        state = read_json(os.path.join(root, STATE_FILE))
        want = {"round", "stage", "seeds_done", "parent_version", "git_commit", "config_hash", "slurm_job_ids",
                "time_used_s"}
        check(want <= set(state) and state["time_used_s"] == 340 * 60 and state["seeds_done"] == [1],
              "run_state.json holds round, stage, seeds done, parent, commit, config hash, job ids, time used")
        check(not [f for f in os.listdir(root) if ".tmp" in f], "the state file is written to a temp file and renamed")
        ckpt.disarm()
    finally:
        if saved is not None:
            os.environ["SLURM_JOB_START_TIME"] = saved

    first, second = RunLock(root), RunLock(root)
    first.acquire()
    try:
        second.acquire()
        check(False, "a second writer is refused")
    except LockError:
        check(True, "a second writer is refused while the first holds the lock")
    first.release()
    with open(first.path, "w", encoding="utf-8") as handle:
        json.dump({"host": __import__("socket").gethostname(), "pid": 2 ** 22 + 12345}, handle)
    note = second.acquire()
    check(bool(note) and second.held, f"a lock left by a dead process is taken over: {note}")
    second.release()
    check(not os.path.exists(second.path), "the lock file is removed on release")


def checkpoint_meta_stage() -> None:
    print("checkpoint: a meta stage cut off in the middle completes once after resume (#14)")
    cfg = base_cfg()
    root = tempfile.mkdtemp(prefix="evolve_stage_")
    calls = {"meta": 0, "extract": 0}

    class CountingMeta(StubMeta):
        def complete(self, messages, max_tokens=None):
            calls["meta"] += 1
            return super().complete(messages, max_tokens)

    class KilledMeta(StubMeta):
        def complete(self, messages, max_tokens=None):
            calls["meta"] += 1
            raise _Killed()

    class KilledExtractor(StubExtractor):
        def complete(self, messages, max_tokens=None):
            calls["extract"] += 1
            raise _Killed()

    _stub_run(root, cfg, 0)  # round 0
    try:  # round 1, killed inside Propose
        _stub_run(root, cfg, 1, meta=KilledMeta)
        check(False, "the run is cut in Propose")
    except _Killed:
        state = read_json(os.path.join(root, STATE_FILE))
        check((state["round"], state["stage"], state["stage_status"]) == (1, "propose.1", "running")
              and not os.path.exists(os.path.join(root, "reports", "round_1", "attempts.json")),
              "cut inside Propose: the state says round 1, propose, running; no proposals were saved")
    try:  # resumed, killed inside Validate (the fact-check's model call)
        _stub_run(root, cfg, 1, meta=CountingMeta, fact=KilledExtractor)
        check(False, "the run is cut in Validate")
    except _Killed:
        state = read_json(os.path.join(root, STATE_FILE))
        attempts = read_json(os.path.join(root, "reports", "round_1", "attempts.json"))
        check((state["stage"], state["stage_status"]) == ("validate.1", "running") and "passed" not in attempts[0]
              and _units(state).get((1, "propose.1")) == 1,
              "cut inside Validate: Propose is recorded once, its proposals are saved, Validate is not")
    meta_calls = calls["meta"]
    archive = _stub_run(root, cfg, 1, meta=CountingMeta)  # resumed, runs to the end
    state = read_json(os.path.join(root, STATE_FILE))
    counts = _units(state)
    check(calls["meta"] == meta_calls, "after the cut in Validate the Meta LLM is not called again")
    stages = ["analyze", "propose.1", "validate.1", "write", "evaluate", "gate"]
    check(all(counts.get((1, s)) == 1 for s in stages) and max(counts.values()) == 1,
          f"every stage of round 1 is recorded exactly once: {[counts.get((1, s)) for s in stages]}")
    sections = _changelog_sections(root)
    versions = [v["version"] for v in archive["versions"]]
    check(sections == ["## v0", "## v1"] and versions == ["v0", "v1"]
          and [r["round"] for r in archive["rounds"]] == [0, 1],
          "CHANGELOG has one section per version and archive.json has no duplicates")
    check(state["status"] == "finished" and len(state["segments"]) == 4,
          f"the state file ends finished after {len(state['segments'])} parts")


def _driver(root: str, *extra: str, delay: float | None = None) -> subprocess.Popen:
    env = dict(os.environ, OPERATION_MODE="offline", PYTHONUNBUFFERED="1")
    env.pop("EVO_STUB_DELAY_S", None)
    if delay:
        env["EVO_STUB_DELAY_S"] = str(delay)
    return subprocess.Popen(
        [sys.executable, "evolve_run.py", "--stub", "--rounds", "1", "--run-dir", root, "--resume", *extra],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env,
    )


def _episodes_done(root: str, round_index: int = 0) -> list[int]:
    path = os.path.join(root, "reports", f"round_{round_index}", "episodes.json")
    try:
        return sorted(e["seed"] for e in read_json(path, []))
    except (json.JSONDecodeError, OSError):  # caught between the write and the rename
        return []


def _wait_mid_round(root: str, proc: subprocess.Popen) -> None:
    """Until round 0 has at least one finished episode and others still running."""
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline and proc.poll() is None:
        done = _episodes_done(root)
        if 1 <= len(done) < 5:
            return
        if len(done) == 5:
            break
        time.sleep(0.01)
    raise SystemExit("self-test failed: could not catch the stub run in the middle of round 0")


def _check_finished_run(root: str, label: str) -> dict[str, Any]:
    state = read_json(os.path.join(root, STATE_FILE))
    archive = read_json(os.path.join(root, "archive.json"))
    seeds = {v["version"]: [e["seed"] for e in v["episodes"]] for v in archive["versions"]}
    check(state["status"] == "finished" and all(s == [1, 2, 3, 4, 5] for s in seeds.values()),
          f"{label}: the resumed run finishes and every seed appears exactly once per version: {seeds}")
    versions = [v["version"] for v in archive["versions"]]
    rounds = [r["round"] for r in archive["rounds"]]
    check(len(versions) == len(set(versions)) and rounds == sorted(set(rounds)),
          f"{label}: archive.json has no duplicates (versions {versions}, rounds {rounds})")
    counts = _units(state)
    check(max(counts.values()) == 1, f"{label}: no episode or stage is recorded twice")
    check(not os.path.exists(os.path.join(root, "run.lock")), f"{label}: the lock file is gone")
    return state


def checkpoint_kill_and_resume() -> None:
    print("checkpoint: a run killed in the middle of an episode resumes without losing or repeating work (#14)")
    root = os.path.join(tempfile.mkdtemp(prefix="evolve_kill_"), "run")
    proc = _driver(root, delay=0.3)
    _wait_mid_round(root, proc)
    proc.kill()  # no warning, no cleanup: the lock file stays behind
    proc.communicate()
    state = read_json(os.path.join(root, STATE_FILE))
    done_before = _episodes_done(root)
    check(state["status"] == "running" and state["stage"] == "evaluate" and len(done_before) < 5
          and os.path.exists(os.path.join(root, "run.lock")),
          f"killed in round 0 with seeds {done_before} done: the state file is whole, the lock is left behind")

    out, _ = _driver(root).communicate(timeout=600)
    check("replaced a stale lock" in out, "the resume takes over the dead job's lock")
    state = _check_finished_run(root, "after the kill")
    replayed = sorted(r["seed"] for r in state["replayed_after_cutoff"])
    check(replayed == sorted(set(range(1, 6)) - set(done_before)) and replayed,
          f"the cut-off seeds {replayed} were replayed from the start; the finished ones {done_before} were not")
    partial = os.path.join(root, "partial", "round_0")
    kept = sorted(os.listdir(partial)) if os.path.isdir(partial) else []
    check(all(f"seed_{s}.jsonl" in kept for s in replayed),
          f"their partial trajectories were moved to partial/: {kept}")
    played = sorted(c["seed"] for c in state["completed"] if c.get("unit") == "episode" and c["round"] == 0)
    check(played == [1, 2, 3, 4, 5] and len(state["segments"]) == 2, "round 0: five episodes counted, over two parts")

    # -- resume a finished run: nothing happens ------------------------------
    watched = [os.path.join(root, name) for name in ("archive.json", STATE_FILE, "CHANGELOG.md", "events.log")]
    before = {path: (os.path.getmtime(path), os.path.getsize(path)) for path in watched}
    proc = _driver(root)
    out, _ = proc.communicate(timeout=120)
    after = {path: (os.path.getmtime(path), os.path.getsize(path)) for path in watched}
    check(proc.returncode == 0 and "Nothing to do" in out and before == after,
          "resuming a finished run does nothing: exit 0, no file touched")

    # -- a run directory is not reused without --resume ----------------------
    env = dict(os.environ, OPERATION_MODE="offline")
    refused = subprocess.run([sys.executable, "evolve_run.py", "--stub", "--rounds", "1", "--run-dir", root],
                             capture_output=True, text=True, env=env)
    check(refused.returncode == 3, "without --resume an existing run directory is refused")


def checkpoint_sigusr1() -> None:
    print("checkpoint: SIGUSR1 saves and exits at once (#14)")
    if not hasattr(signal, "SIGUSR1"):
        print("  skip (no SIGUSR1 on this platform; runs in the cluster smoke job)")
        return
    root = os.path.join(tempfile.mkdtemp(prefix="evolve_usr1_"), "run")
    proc = _driver(root, delay=0.3)
    _wait_mid_round(root, proc)
    sent = time.monotonic()
    proc.send_signal(signal.SIGUSR1)
    out, _ = proc.communicate(timeout=60)
    took = time.monotonic() - sent
    state = read_json(os.path.join(root, STATE_FILE))
    check(proc.returncode == 0 and state["status"] == "paused" and "SIGUSR1" in (state["segments"][-1]["stop_reason"] or "")
          and took < 30 and not os.path.exists(os.path.join(root, "run.lock")),
          f"exit code 0 in {took:.1f}s, state paused ({state['segments'][-1]['stop_reason']}), lock released")
    _driver(root).communicate(timeout=600)
    _check_finished_run(root, "after SIGUSR1")


def main() -> None:
    skill_name_check()
    plain, switch = frame_evidence_checks()
    rotation_score_checks(plain, switch)
    frames_per_step(plain, switch)
    leak_test()
    checkpoint_units()
    checkpoint_meta_stage()
    checkpoint_kill_and_resume()
    checkpoint_sigusr1()


if __name__ == "__main__":
    os.environ.setdefault("OPERATION_MODE", "offline")
    main()
    print("all #14 self-tests passed")
