"""Self-tests for issue #16: the action record, the state-change check, the
repeat check, "Rejected since current parent", and the leak test extended to
the new Meta input section and the player's action record.

Some tests click known places (a tile in ft09, a button in vc33: see each
game's GAME_NOTES.md), so they live under scorer/, next to the notes, as #15's
do. Run with `python -m scorer.tests16` or through `python -m evolve.selftest`.
"""

from __future__ import annotations

import copy
import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import yaml

os.environ.setdefault("OPERATION_MODE", "offline")

from harness.model import ModelResponse, Usage  # noqa: E402
from evolve import loop  # noqa: E402
from evolve.action_loop import EpisodeAPI, build_sandbox, load_frames, read_records, run_episode, user_message  # noqa: E402
from evolve.edits import EditError, Workspace, apply_edit, normalise  # noqa: E402
from evolve.frame_diff import ActionRecorder, record_line, render  # noqa: E402
from evolve.harness import API_DOC_ACTION_LOG, load_harness  # noqa: E402
from evolve.propose import META_SYSTEM, REPEAT_TEXT, STATE_CHANGE_TEXT, meta_messages  # noqa: E402
from evolve.rejected import RejectedStore, canonical_code, make_entry, render_section, rejected_since_parent  # noqa: E402
from evolve.replay import make_env  # noqa: E402
from evolve.seed_v0 import build_v0  # noqa: E402
from evolve.skill_names import check_harness  # noqa: E402
from evolve.state_change import StateChangeChecker  # noqa: E402
from evolve.stub import ScriptedPlayer, StubPlayer  # noqa: E402
from evolve.validate import validate  # noqa: E402
from scorer import for_game  # noqa: E402
from scorer.tests import LEAK_PATTERNS, NO_SOLUTION, leaks  # noqa: E402

GAMES = ("ft09", "vc33")
TILE = {"ft09": (37, 37)}                 # (x, y) of a tile: a click toggles it
BUTTON = {"vc33": (61, 33)}               # (x, y) of a button: a click moves the columns
INERT = (5, 5)                            # changes nothing in either game (the bar aside, in vc33)
# Words that interpret rather than observe (#16: "no words like rotation,
# switch or goal, no advice").
RECORD_KEYS = {"step", "action", "x", "y", "value_at_click", "changed", "n_changed", "regions", "every_step_cells",
               "block_before", "block_after", "game_over", "level_restarted", "frame_size_changed"}
INTERPRETIVE = re.compile(r"\b(rotat\w*|switch\w*|goal\w*|target\w*|win\w*|should|try|button\w*|tile\w*|"
                          r"solv\w*|progress|correct|wrong|useful|useless)\b", re.IGNORECASE)


def check(condition: bool, label: str) -> None:
    print(f"  {'ok  ' if condition else 'FAIL'} {label}")
    if not condition:
        raise SystemExit(f"self-test failed: {label}")


def game_cfg(game: str) -> dict[str, Any]:
    from evolve_run import apply_game

    with open("config_evolve_16.yaml", encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle)
    apply_game(cfg, game)
    cfg["budget"] |= {"max_actions": 40, "max_turns": 30}
    return cfg


def play(game: str, actions: list[Any], root: str, seed: int = 1, cfg: dict[str, Any] | None = None,
         player: Any = None) -> dict[str, Any]:
    cfg = copy.deepcopy(cfg or game_cfg(game))
    cfg["budget"] |= {"max_actions": len(actions) + 6, "max_turns": -(-len(actions) // 6) + 1}
    outcome = run_episode(
        env=make_env(cfg["game"], seed=seed), client=player or ScriptedPlayer(list(actions)),
        harness=build_v0(cfg["v0_drop_prompts"]), round_index=0, episode=seed, seed=seed, cfg=cfg,
        traj_root=os.path.join(root, "t"), frame_root=os.path.join(root, "f"), log=lambda _m: None,
        probe=for_game(cfg["game"]).read_state,
    )
    return {"cfg": cfg, "outcome": outcome, "seed": seed, "episode": seed, "trajectory": outcome.trajectory,
            "frames": outcome.frames, "records": read_records(outcome.trajectory)}


def logged_records(episode: dict[str, Any]) -> list[dict[str, Any]]:
    return [a["record"] for r in episode["records"] if r.get("type") == "tool_call" for a in r["actions"]]


@dataclass
class CapturePlayer(ScriptedPlayer):
    """A scripted player that keeps the turn messages it was sent."""

    seen: list[str] = field(default_factory=list)

    def complete(self, messages, max_tokens=None) -> ModelResponse:
        self.seen.append(messages[-1]["content"])
        return super().complete(messages, max_tokens)


# ---------------------------------------------------------------------------
# 1. the action record (change 5)
# ---------------------------------------------------------------------------


def action_record_checks() -> None:
    print("action record: what each action changed, in the player's context and in action_log (#16)")
    root = tempfile.mkdtemp(prefix="rec16_")
    tx, ty = TILE["ft09"]
    player = CapturePlayer([(6, tx, ty), (6, *INERT), (6, tx, ty), (6, *INERT), (6, 10, 60), (6, 20, 30),
                            (6, 50, 10)])
    ft = play("ft09", player.actions, os.path.join(root, "ft09"), player=player)
    records = logged_records(ft)
    first = ft["records"][1]["actions"][0]
    frames = load_frames(ft["frames"])
    tile = records[0]
    check(tile["changed"] and tile["x"] == tx and tile["y"] == ty and tile["n_changed"] > 0
          and any(r["rows"][0] <= ty <= r["rows"][1] and r["cols"][0] <= tx <= r["cols"][1] for r in tile["regions"])
          and all(len(v) == 3 and v[0] != v[1] for r in tile["regions"] for v in r["values"]),
          f"a click that changes cells: coordinates, changed region, values before -> after: {record_line(tile)}")
    miss = records[1]
    check(not miss["changed"] and miss["n_changed"] == 0 and record_line(miss).endswith("no change"),
          f"a click with no effect is recorded as 'no change': {record_line(miss)}")
    check(all(r["x"] == a["args"]["x"] and r["y"] == a["args"]["y"]
              for r, a in zip(records, [a for t in ft["records"] if t.get("type") == "tool_call" for a in t["actions"]]))
          and tile["value_at_click"] == int(np.asarray(frames[first["frame_before"]])[ty, tx])
          and f"click ({tx}, {ty})" in record_line(tile),
          "the record's coordinates are the click's own (x, y), in the order action() takes them; "
          "'on N' is the value at row y, col x before the click")

    # Every-step regions: vc33's step bar changes on every click.
    bx, by = BUTTON["vc33"]
    clicks = [(6, *INERT), (6, 10, 60), (6, 40, 10), (6, bx, by), (6, 20, 50), (6, *INERT), (6, 30, 30),
              (6, bx, by), (6, 12, 12)]
    vc = play("vc33", clicks, os.path.join(root, "vc33"))
    vc_records = logged_records(vc)
    recorder = ActionRecorder()
    vc_frames = load_frames(vc["frames"])
    for item in [a for t in vc["records"] if t.get("type") == "tool_call" for a in t["actions"]]:
        recorder.add(item["action_index"], item["action"], item["args"], np.asarray(vc_frames[item["frame_before"]]),
                     np.asarray(vc_frames[item["frame_after"]]), game_over="auto_reset_frame" in item,
                     level_restarted="auto_reset_frame" in item)
    text = render(recorder)
    every = recorder.every_step()
    late = vc_records[3:]
    check(len(every) == 1 and every[0][0] == every[0][2] == 0
          and text.count("Changes every step (left out below): row 0") == 1
          and all(r["every_step_cells"] > 0 and all(reg["rows"][0] > 0 for reg in r["regions"]) for r in late)
          and not late[2]["changed"] and late[0]["changed"],
          f"a region that changes every step is listed once and left out of the lines ({every})")
    again = play("vc33", clicks, os.path.join(root, "vc33_again"))
    check(logged_records(again) == vc_records and recorder.records == vc_records,
          "the same episode gives the same record twice (and rebuilt from the saved frames, the same again)")

    # In the player's context: the block, before each turn.
    check(all("ACTION RECORD" in m for m in player.seen) and "Last 6 of 6 actions" in player.seen[1]
          and f"step 1 · click ({tx}, {ty})" in player.seen[1] and "Clicks this episode: 6 on 4 locations" in player.seen[1],
          "the record is in the player's turn message: the last actions one line each, then the click summary")
    long_episode = play("vc33", [(6, x, 50) for x in range(0, 60, 2)], os.path.join(root, "long"),
                        player=CapturePlayer([(6, x, 50) for x in range(0, 60, 2)]))
    final = ActionRecorder()
    lfr = load_frames(long_episode["frames"])
    for item in [a for t in long_episode["records"] if t.get("type") == "tool_call" for a in t["actions"]]:
        final.add(item["action_index"], item["action"], item["args"], np.asarray(lfr[item["frame_before"]]),
                  np.asarray(lfr[item["frame_after"]]))
    shown = render(final, last_n=20)
    check("Last 20 of 30 actions" in shown and "step 10 ·" not in shown and "step 11 ·" in shown
          and "Clicks this episode: 30 on 30 locations" in shown,
          "after 30 actions: the last 20 in full, the older ones only in the summary")
    chars = [r.get("action_record_chars") for r in long_episode["records"] if r.get("type") == "tool_call"]
    check(all(isinstance(c, int) and c > 0 for c in chars), f"each turn logs the record's size (chars: {chars})")

    # In the sandbox: action_log, read-only.
    api = EpisodeAPI(make_env(vc["cfg"]["game"], seed=1), 6, 100, 10, action_record=True)
    sandbox, _c, failed = build_sandbox(api, build_v0(["knowledge"]), 5)
    api.begin_turn(0)
    # Three clicks that change only the bar (so it is known as every-step),
    # the button, then one more click on nothing.
    first_cell = sandbox.run(f"action(6, x=5, y=5)\naction(6, x=12, y=12)\naction(6, x=40, y=10)\n"
                             f"action(6, x={bx}, y={by})\naction(6, x=5, y=5)\n"
                             "print(len(action_log), action_log[3]['x'], action_log[3]['changed'], "
                             "action_log[-1]['changed'])")
    check(not failed and first_cell.stdout.strip() == f"5 {bx} True False",
          f"action_log in the sandbox holds the same records: {first_cell.stdout.strip() or first_cell.error}")
    tamper = sandbox.run("e = action_log[3]\ne['changed'] = False\naction_log.append(1)")
    check(tamper.error is not None and "append" in tamper.error and api.recorder.records[3]["changed"] is True,
          f"action_log is read-only: no append, and changing an entry changes a copy ({tamper.error})")
    sandbox.run("action_log = []")
    api.restore(sandbox.namespace)
    check(sandbox.run("print(len(action_log))").stdout.strip() == "5",
          "a cell that rebinds action_log gets it back before the next cell")
    v0 = build_v0(["knowledge"])
    v0.prompts["system"] += "\nRead `action_log` to see what each click did."
    check(check_harness(v0) == [], "`action_log` is a sandbox built-in for the skill-name check")
    try:
        apply_edit(Workspace.from_parent(build_v0(["knowledge"]), "t", 1),
                   normalise({"op": "add", "target": "skill", "name": "action_log",
                              "content": 'def action_log():\n    """x"""\n    return 1\n'}, "meta"))
        check(False, "a skill may not be named action_log")
    except EditError:
        check(True, "a skill may not be named action_log")

    # Observations only.
    lines = [record_line(r) for r in records + vc_records + final.records] + [render(final), API_DOC_ACTION_LOG]
    words = sorted({m.group(0).lower() for t in lines for m in INTERPRETIVE.finditer(t)})
    check(words == [], f"the record's text reports changes only: no interpretive words {words or ''}")


# ---------------------------------------------------------------------------
# 2. the state-change check (change 2)
# ---------------------------------------------------------------------------


def _skill(name: str, body: str, doc: str) -> str:
    return f'def {name}():\n    """{doc}"""\n' + "".join(f"    {line}\n" for line in body.splitlines())


def _parent_episodes(game: str, root: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    cfg = game_cfg(game)
    episodes = []
    for seed in (1, 2):
        script = NO_SOLUTION[game] * 2 if seed == 1 else list(reversed(NO_SOLUTION[game])) * 2
        played = play(game, script, os.path.join(root, f"s{seed}"), seed=seed, cfg=cfg)
        episodes.append({"episode": seed, "seed": seed, "records": played["records"], "frames": played["frames"],
                         "trajectory": played["trajectory"]})
    return cfg, episodes


def _validate(game: str, cfg: dict[str, Any], episodes: list[dict[str, Any]], edits: list[dict[str, Any]],
              store: RejectedStore | None = None, state: bool = True):
    checker = StateChangeChecker(cfg, episodes, for_game(cfg["game"]).read_state) if state else None
    return validate(build_v0(cfg["v0_drop_prompts"]), edits, episodes, cfg, "v1", 1, log=lambda _m: None,
                    rejected=store, state_checker=checker)


def state_change_checks() -> None:
    print("state-change check in Validate: skills whose actions change nothing are dropped (#16)")
    root = tempfile.mkdtemp(prefix="sc16_")
    for game in GAMES:
        cfg, episodes = _parent_episodes(game, os.path.join(root, game))
        x, y = TILE.get(game) or BUTTON[game]
        edits = [
            {"op": "add", "target": "skill", "name": "press_corner", "source": "meta", "test": "press_corner()",
             "content": _skill("press_corner", f"action(6, x={INERT[0]}, y={INERT[1]})", "Clicks one cell once.")},
            {"op": "add", "target": "skill", "name": "press_place", "source": "meta", "test": "press_place()",
             "content": _skill("press_place", f"action(6, x={x}, y={y})", "Clicks one cell once.")},
            {"op": "add", "target": "skill", "name": "count_cells", "source": "meta",
             "test": "assert count_cells() >= 0",
             "content": _skill("count_cells", "return int((grid() > 0).sum())", "Number of non-zero cells.")},
        ]
        _child, passed, dropped, info = _validate(game, cfg, episodes, edits)
        by_name = {d["edit"]["name"]: d for d in passed + dropped}
        corner = by_name["press_corner"]
        check(corner.get("stage") == "state-change" and corner["state_change"]["verdict"] == "no change"
              and len(corner["state_change"]["states"]) == 5
              and len({s["seed"] for s in corner["state_change"]["states"]}) == 2,
              f"{game}: a skill whose actions have no effect from any test state is dropped "
              f"({len(corner['state_change']['states'])} states, seeds "
              f"{sorted({s['seed'] for s in corner['state_change']['states']})})")
        place = by_name["press_place"]
        check("stage" not in place and place["state_change"]["verdict"] == "changed",
              f"{game}: a skill that changes the state passes ({place['state_change']['summary']})")
        helper = by_name["count_cells"]
        check("stage" not in helper and "state_change" not in helper
              and all(c["check"] != "state-change" for c in helper["checks"]),
              f"{game}: a read-only helper is not checked")
        if game == "vc33":
            check(info["state_change"]["every_step_regions"] and info["state_change"]["every_step_fields"] == ["steps_left"],
                  f"vc33: the step bar and the step count are left out ({info['state_change']['every_step_regions']}, "
                  f"{info['state_change']['every_step_fields']})")
        check(info["state_change"]["env_steps"] > 0 and info["state_change"]["skills_checked"] == 2,
              f"{game}: its env steps are counted on their own ({info['state_change']['env_steps']})")

        # A replay that does not reproduce the logged frame: unverifiable.
        bad = copy.deepcopy(episodes)
        for episode in bad:
            for record in episode["records"]:
                if record.get("type") == "tool_call":
                    record["frame_hash_before"] = "0" * 16
        _child, passed, dropped, _info = _validate(game, cfg, bad, edits[:1])
        kept = passed[0] if passed else {}
        section = loop.changelog_section(build_v0(), passed, dropped)
        check(not dropped and kept.get("state_change", {}).get("verdict") == "unverifiable"
              and all(s["verdict"] == "unverifiable" for s in kept["state_change"]["states"])
              and "STATE-CHANGE UNVERIFIABLE" in section,
              f"{game}: a replay that does not reproduce the logged frame: unverifiable, kept and flagged in CHANGELOG")


def audit_v0(game: str, root: str) -> dict[str, Any]:
    """The state-change check on v0's action-taking skills (#16 step 3)."""
    from evolve.state_change import applies_to, takes_actions

    cfg, episodes = _parent_episodes(game, root)
    v0 = build_v0(cfg["v0_drop_prompts"])
    checker = StateChangeChecker(cfg, episodes, for_game(cfg["game"]).read_state)
    results = {}
    for name in sorted(v0.skills):
        edit = {"op": "edit", "target": "skill", "name": name, "content": v0.skills[name], "source": "audit"}
        results[name] = checker.check(edit, v0) if applies_to(edit, v0) else {"verdict": "not checked",
                                                                              "takes_actions": takes_actions(v0, name)}
    return results


# ---------------------------------------------------------------------------
# 3. the repeat check (change 3)
# ---------------------------------------------------------------------------


def repeat_checks() -> None:
    print("repeat check in Validate: edits that repeat a rejected one are dropped first (#16)")
    root = tempfile.mkdtemp(prefix="rep16_")
    cfg, episodes = _parent_episodes("vc33", os.path.join(root, "parent"))
    parent = build_v0(cfg["v0_drop_prompts"])
    store = RejectedStore(os.path.join(root, "rejected_edits.jsonl"))
    tips = "TIPS\n- Click each coloured area once and note which cells change."
    clicker = ('def click_all(colour=9):\n    """Clicks every cell of one colour, once each."""\n'
               '    g = grid()\n    rows, cols = np.nonzero(g == colour)\n    taken = 0\n'
               '    for r, c in zip(rows, cols):\n        action(6, x=int(c), y=int(r))\n        taken += 1\n'
               '    return taken\n')
    renamed = ('def press_every(col=9):\n    """Another docstring."""\n'
               '    board = grid()\n    ys, xs = np.nonzero(board == col)\n    n = 0\n'
               '    for yy, xx in zip(ys, xs):\n        action(6, x=int(xx), y=int(yy))  # same thing\n        n += 1\n'
               '    return n\n')
    store.add(make_entry("r1-gate-e1", 1, "v1", normalise({"op": "add", "target": "prompt", "name": "tips",
                                                            "content": tips}, "meta"), parent, "gate: rejected"))
    store.add(make_entry("r1-a1-e2", 1, "v1", normalise({"op": "add", "target": "skill", "name": "click_all",
                                                          "content": clicker, "test": "click_all()"}, "meta"),
                         parent, "validate: state-change"))
    check(canonical_code(clicker) == canonical_code(renamed) and canonical_code(clicker) != canonical_code(
        clicker.replace("== colour", "!= colour")), "code identity ignores docstring, comments and bound names only")
    edits = [
        {"op": "add", "target": "prompt", "name": "tips", "content": tips, "source": "meta"},
        {"op": "add", "target": "prompt", "name": "tips", "source": "meta",
         "content": "tips\n  -   CLICK each coloured   area once and note which cells change. "},
        {"op": "add", "target": "skill", "name": "press_every", "content": renamed, "test": "press_every()",
         "source": "meta"},
        {"op": "add", "target": "prompt", "name": "advice", "content": tips, "source": "meta"},
        {"op": "add", "target": "prompt", "name": "tips", "source": "meta",
         "content": "TIPS\n- Write down the rows and columns that changed after each action."},
    ]
    _child, passed, dropped, info = _validate("vc33", cfg, episodes, edits, store=store, state=False)
    stage = {d["id"]: d for d in dropped}
    ok = {p["id"] for p in passed}
    check(stage.get("r1-e1", {}).get("stage") == "repeat" and stage["r1-e1"]["repeat_of"] == "r1-gate-e1"
          and stage["r1-e1"]["similarity"] == 1.0, f"an exact repeat is dropped: {stage.get('r1-e1', {}).get('reason')}")
    check(stage.get("r1-e2", {}).get("stage") == "repeat" and stage["r1-e2"]["repeat_of"] == "r1-gate-e1",
          f"the same text with different case and whitespace is dropped: {stage.get('r1-e2', {}).get('reason')}")
    check(stage.get("r1-e3", {}).get("stage") == "repeat" and stage["r1-e3"]["repeat_of"] == "r1-a1-e2",
          f"the same skill code with renamed variables (and name) is dropped: {stage.get('r1-e3', {}).get('reason')}")
    check("r1-e4" in ok, "the same text on a different target passes")
    check("r1-e5" in ok, "clearly different text on the same target passes")
    check(info["repeat"]["edits_dropped"] == 3 and all(d["checks"][0]["check"] == "repeat" for d in dropped),
          "repeats are dropped before any other check runs")


# ---------------------------------------------------------------------------
# 4. "Rejected since current parent" (change 4), and the store over a run
# ---------------------------------------------------------------------------


@dataclass
class ScriptMeta:
    """Returns a fixed list of edits per call and keeps what it was sent."""

    script: list[list[dict[str, Any]]]
    seen: list[list[dict[str, str]]]
    model: str = "script-meta"
    usage: Usage = field(default_factory=Usage)

    def complete(self, messages, max_tokens=None) -> ModelResponse:
        self.seen.append(messages)
        edits = self.script[min(len(self.seen) - 1, len(self.script) - 1)]
        text = json.dumps({"analysis": "scripted", "edits": edits})
        return ModelResponse(text=text, tokens_in=100, tokens_out=100, latency_ms=1)


@dataclass
class LivesExtractor:
    """Fact-check extractor stand-in: a "LIVES" line claims a colour counts
    lives, which neither ft09 nor vc33 has (false)."""

    model: str = "lives-extractor"
    usage: Usage = field(default_factory=Usage)

    def complete(self, messages, max_tokens=None) -> ModelResponse:
        text = messages[-1]["content"]
        claims = []
        for match in re.finditer(r"^=== edit (\S+):", text, re.MULTILINE):
            body = text[match.end():text.find("=== edit", match.end()) if "=== edit" in text[match.end():] else len(text)]
            if "LIVES" in body:
                claims.append({"edit": match.group(1), "quote": "the maroon bar counts lives", "kind": "colour_role",
                               "colour": "maroon", "role": "lives"})
        return ModelResponse(text=json.dumps({"claims": claims}), tokens_in=10, tokens_out=10, latency_ms=1)


SECTION_SCRIPT = [
    # round 1: a prompt line (dearer: rejected at the Gate), and a false claim (fact-check)
    [{"op": "add", "target": "prompt", "name": "tips", "rationale": "r",
      "content": "TIPS\n- Note which cells each click changes before clicking again."},
     {"op": "add", "target": "prompt", "name": "facts", "rationale": "r",
      "content": "FACTS\n- LIVES: the maroon bar counts lives."}],
    # round 2: delete the last step (cheaper: accepted)
    [{"op": "delete", "target": "step", "index": 6, "rationale": "r"}],
    # round 3: anything
    [{"op": "add", "target": "prompt", "name": "more", "rationale": "r", "content": "MORE\n- Keep notes short."}],
]


def section_checks() -> dict[str, Any]:
    print("\"Rejected since current parent\" in the Meta LLM's input (#16)")
    out = {}
    for game in GAMES:
        root = tempfile.mkdtemp(prefix=f"sec16_{game}_")
        cfg = game_cfg(game)
        cfg["meta"]["max_edits"] = 4
        seen: list[list[dict[str, str]]] = []
        archive = loop.run(cfg, loop.Paths(root, title="self-test"), 3, lambda k: StubPlayer(seed=k),
                           lambda: ScriptMeta(SECTION_SCRIPT, seen), log=lambda _m: None, fact_factory=LivesExtractor)
        decisions = [r["decision"] for r in archive["rounds"]]
        check(decisions == ["baseline", "rejected", "accepted", decisions[3]],
              f"{game}: the scripted run gives a Gate rejection, then an accept ({decisions})")
        round2 = seen[1][-1]["content"]
        v1 = next(v for v in archive["versions"] if v["version"] == "v1")
        scores = ", ".join(f"{e['score']:.3f}".rstrip("0").rstrip(".") for e in v1["episodes"])
        check("REJECTED SINCE CURRENT PARENT (v0)" in round2 and "- v1 (round 1): rejected at the Gate:" in round2
              and v1["gate"]["reason"] in round2 and f"seeds 1, 2, 3, 4, 5: {scores} vs" in round2
              and "+- Note which cells each click changes before clicking again." in round2
              and "add prompt tips (type edit, from meta)" in round2,
              f"{game}: after a Gate rejection, the next Meta input lists that version with its edits, "
              "per-seed scores and the gate reason")
        section = round2[round2.index("REJECTED SINCE CURRENT PARENT"):]
        drop_line = next((line for line in section.splitlines() if "add prompt facts" in line), "")
        fact_item = next(d for d in json.load(open(os.path.join(root, "reports", "round_1", "validation.json"),
                                                    encoding="utf-8"))["attempts"][0]["dropped"]
                         if d["stage"] == "fact-check")
        evidence = fact_item["factcheck"]["claims"][0]["evidence"]
        check(drop_line.endswith("dropped by fact-check (false)") and evidence not in round2
              and fact_item["reason"] not in section,
              f"{game}: a fact-check drop is shown with its label only (the claim's evidence is nowhere in the "
              f"Meta input): {drop_line.strip()!r}")
        round3 = seen[2][-1]["content"]
        check("REJECTED SINCE CURRENT PARENT (v2)" in round3 and "None so far." in round3
              and "- v1 (round 1)" not in round3,
              f"{game}: after an accept, the section is empty for the new parent")
        store = RejectedStore(os.path.join(root, "rejected_edits.jsonl"))
        ids = [e["id"] for e in store.entries]
        round1 = [e for e in store.entries if e["round"] == 1]
        gate_v1 = [e for e in round1 if e["rejected_by"].startswith("gate:")]
        check([e["name"] for e in round1 if e["rejected_by"] == "validate: fact-check"] == ["facts"]
              and len(gate_v1) == len(v1["edits_accepted"]) and "tips" in [e["name"] for e in gate_v1]
              and len(ids) == len(set(ids)),
              f"{game}: rejected_edits.jsonl holds the Validate drop and every edit of the rejected version, "
              f"once each ({ids})")
        report = json.load(open(os.path.join(root, "reports", "round_2", "analysis.json"), encoding="utf-8"))
        as_of_round2 = {"rounds": archive["rounds"][:2], "versions": archive["versions"][:2]}
        rebuilt = render_section(rejected_since_parent(as_of_round2, root,
                                                       load_harness("v0", os.path.join(root, "harnesses")),
                                                       archive["versions"][0]))
        check(report["rejected_since_parent"]["text"] == rebuilt,
              f"{game}: the stored section is what the archive and the round reports give")
        check("STATE CHANGE:" in seen[0][0]["content"] and "REPEATS:" in seen[0][0]["content"]
              and "ACTION RECORD" in seen[0][0]["content"] and "action_log" in seen[0][0]["content"],
              f"{game}: the Meta prompt describes the two new checks, the player's record and action_log")
        out[game] = {"messages": seen, "root": root}
    return out


# ---------------------------------------------------------------------------
# 5. leak test, extended
# ---------------------------------------------------------------------------


def leak_checks(section_runs: dict[str, Any]) -> None:
    print("leak test: the new Meta input section and the player's action record (#16)")
    for game in GAMES:
        check(all(leaks(game, s) for s in ["32 tile clicks" if game == "ft09" else "50 steps"]),
              f"{game}: the scanner still finds a fact when it is there")
        for name, text in {"#16 Meta texts": STATE_CHANGE_TEXT + REPEAT_TEXT + META_SYSTEM,
                           "action_log API text": API_DOC_ACTION_LOG}.items():
            check(leaks(game, text) == [], f"{game}: {name}: none {leaks(game, text) or ''}")
        messages = section_runs[game]["messages"]
        sections = []
        for call in messages:
            content = call[-1]["content"]
            start = content.find("REJECTED SINCE CURRENT PARENT")
            sections.append(content[start:])
        check(all(leaks(game, s) == [] for s in sections) and any("- v1 (round 1): rejected at the Gate" in s
                                                                  for s in sections),
              f"{game}: every \"Rejected since current parent\" section of a run: none")
        check(all(leaks(game, "\n\n".join(m["content"] for m in call)) == [] for call in messages),
              f"{game}: every full Meta LLM input of that run: none")
        root = tempfile.mkdtemp(prefix=f"leak16_{game}_")
        player = CapturePlayer(NO_SOLUTION[game] * 3)
        episode = play(game, player.actions, root, player=player)
        records = logged_records(episode)
        context = "\n".join(player.seen)
        check(leaks(game, context) == [] and leaks(game, json.dumps(records)) == [] and "ACTION RECORD" in context,
              f"{game}: the player's turn messages with the action record, and the logged records: none")
        keys = set().union(*(set(r) for r in records))
        check(keys <= RECORD_KEYS and all(set(g) <= {"rows", "cols", "cells", "values"}
                                          for r in records for g in r["regions"]),
              f"{game}: the record holds frame observations only, no game state ({sorted(keys)})")
    check(set(LEAK_PATTERNS) == set(GAMES), "both games' notes are scanned")


def main() -> None:
    action_record_checks()
    state_change_checks()
    repeat_checks()
    runs = section_checks()
    leak_checks(runs)


if __name__ == "__main__":
    main()
    print("all #16 self-tests passed")
