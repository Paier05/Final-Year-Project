"""Self-tests for issue #15: the ft09 and vc33 scorers, frame evidence on
click games, the per-game fact-check, v0 without `knowledge`, and the leak
test extended to both games' notes.

These tests know the games (winning click sequences, the facts in
scorer/<game>/GAME_NOTES.md), so they live under scorer/, next to the notes.
Run with `python -m scorer.tests` or through `python -m evolve.selftest`.
"""

from __future__ import annotations

import copy
import inspect
import json
import os
import re
import tempfile
from typing import Any

import numpy as np
import yaml

os.environ.setdefault("OPERATION_MODE", "offline")

from evolve import analyze as analyze_mod  # noqa: E402
from evolve import frame_evidence, loop  # noqa: E402
from evolve.action_loop import load_frames, read_records, run_episode  # noqa: E402
from evolve.factcheck import check_claim, ground_truth  # noqa: E402
from evolve.harness import API_DOC  # noqa: E402
from evolve.propose import META_SYSTEM, SCORE_UNDISCLOSED, meta_messages  # noqa: E402
from evolve.replay import make_env  # noqa: E402
from evolve.sandbox import Sandbox  # noqa: E402
from evolve.seed_v0 import build_v0  # noqa: E402
from evolve.skill_names import check_harness  # noqa: E402
from evolve.stub import ScriptedPlayer  # noqa: E402
from scorer import for_game  # noqa: E402

GAMES = ("ft09", "vc33")

# Winning click sequences, (6, x, y): see each game's GAME_NOTES.md.
WIN = {
    "ft09": [(6, 37, 37), (6, 37, 45), (6, 37, 53), (6, 53, 45)],
    "vc33": [(6, 61, 33)] * 3,
}
# Two right moves, not a clear.
PARTIAL = {"ft09": WIN["ft09"][:2], "vc33": WIN["vc33"][:2]}
# Clicks that never touch a tile that must change (ft09) or the right button
# (vc33): used where a trajectory must not carry the solution.
NO_SOLUTION = {
    "ft09": [(6, 5, 5), (6, 45, 37), (6, 45, 37), (6, 20, 30), (6, 53, 53), (6, 45, 53), (6, 5, 5), (6, 45, 37)],
    "vc33": [(6, 5, 5), (6, 40, 10), (6, 61, 25), (6, 20, 50), (6, 61, 25), (6, 5, 5)],
}


def check(condition: bool, label: str) -> None:
    print(f"  {'ok  ' if condition else 'FAIL'} {label}")
    if not condition:
        raise SystemExit(f"self-test failed: {label}")


def game_cfg(game: str) -> dict[str, Any]:
    from evolve_run import apply_game

    with open("config_evolve_15.yaml", encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle)
    apply_game(cfg, game)
    cfg["budget"] |= {"max_actions": 40, "max_turns": 30}
    return cfg


def random_clicks(n: int, seed: int) -> list[tuple[int, int, int]]:
    rng = np.random.RandomState(seed)
    return [(6, int(x), int(y)) for x, y in rng.randint(0, 64, size=(n, 2))]


def play(game: str, actions: list[Any], root: str, seed: int = 1) -> dict[str, Any]:
    cfg = game_cfg(game)
    cfg["budget"] |= {"max_actions": len(actions) + 6, "max_turns": -(-len(actions) // 6) + 1}
    outcome = run_episode(
        env=make_env(cfg["game"], seed=seed), client=ScriptedPlayer(list(actions)),
        harness=build_v0(cfg["v0_drop_prompts"]), round_index=0, episode=seed, seed=seed, cfg=cfg,
        traj_root=os.path.join(root, "t"), frame_root=os.path.join(root, "f"), log=lambda _m: None,
        probe=for_game(cfg["game"]).read_state,
    )
    return {"cfg": cfg, "outcome": outcome, "seed": seed, "trajectory": outcome.trajectory,
            "frames_path": outcome.frames, "records": read_records(outcome.trajectory)}


def score(game: str, episode: dict[str, Any]) -> dict[str, Any]:
    cfg = episode["cfg"]
    return for_game(cfg["game"]).score_episode(episode["records"], cfg["game"], cfg["score"]["weights"])


# ---------------------------------------------------------------------------
# 1. scorers
# ---------------------------------------------------------------------------


def scorer_checks() -> dict[str, dict[str, Any]]:
    print("scorers: ft09 and vc33 goal progress (#15)")
    root = tempfile.mkdtemp(prefix="scorer15_")
    saved = {}
    for game in GAMES:
        win = play(game, WIN[game], os.path.join(root, game, "win"))
        result = score(game, win)
        check(win["outcome"].solved and result["score"] == 1.0 and result["cleared"],
              f"{game}: a winning trajectory ({len(WIN[game])} clicks) scores 1.0")
        rand = play(game, random_clicks(40, seed=7), os.path.join(root, game, "random"))
        r_result = score(game, rand)
        check(not rand["outcome"].solved and r_result["score"] < 1.0,
              f"{game}: a random-click trajectory (40 clicks, seed 7) scores below that: {r_result['score']}")
        again = score(game, rand)
        replay = play(game, random_clicks(40, seed=7), os.path.join(root, game, "random_again"))
        check(again == r_result and score(game, replay)["score"] == r_result["score"],
              f"{game}: the same trajectory scores the same twice (and a replay of its clicks too)")
        part = score(game, play(game, PARTIAL[game], os.path.join(root, game, "partial")))
        check(0.0 < part["score"] < 1.0 and not part["cleared"],
              f"{game}: two right clicks score strictly between 0 and 1: {part['score']}")
        sc = for_game(win["cfg"]["game"])
        start = sc.state_parts(dict(win["records"][0]["start_state"], action_index=0),
                               sc.start_failing(win["cfg"]["game"]) if game == "ft09"
                               else sc.start_distances(win["cfg"]["game"]))
        check(start[sc.PARTS[0]] == 0.0, f"{game}: the start state scores 0")
        non_clear = [v for v, s, p in _scored(game, win) if s["action_index"] < len(WIN[game])]
        check(all(v < 1.0 for v in non_clear), f"{game}: no state before the clear reaches 1.0")
        check(sc.describe_failure(result) is None and sc.DISCLOSE_PARTS is False,
              f"{game}: the scorer gives Analyze no failure text and does not disclose its parts")
        saved[game] = rand
    return saved


def _scored(game: str, episode: dict[str, Any]) -> list:
    from scorer.common import score_records

    sc = for_game(episode["cfg"]["game"])
    at_start = sc.start_failing(episode["cfg"]["game"]) if game == "ft09" else sc.start_distances(episode["cfg"]["game"])
    _result, scored = score_records(episode["records"], lambda s: sc.state_parts(s, at_start),
                                    sc.DEFAULT_WEIGHTS, sc.PARTS)
    return scored


# ---------------------------------------------------------------------------
# 2. frame evidence on click games
# ---------------------------------------------------------------------------


def frame_evidence_checks(saved: dict[str, dict[str, Any]]) -> None:
    print("frame evidence on games played by clicks (#15)")
    for game in GAMES:
        # From the files on disk, as Analyze reads them.
        episodes = [{"seed": 1, "records": read_records(saved[game]["trajectory"]),
                     "frames": load_frames(saved[game]["frames_path"])}]
        first = frame_evidence.build(episodes)
        text = frame_evidence.render(first, "v0")
        check(first.get("mode") == "clicks" and "A. ACTIONS AND WHERE THEY LANDED" in text,
              f"{game}: runs on a saved trajectory without errors and reports clicks, not a block")
        second = frame_evidence.build(episodes)
        check(frame_evidence.render(second, "v0") == text
              and json.dumps({k: v for k, v in second.items() if k != "per_step"}, default=str)
              == json.dumps({k: v for k, v in first.items() if k != "per_step"}, default=str),
              f"{game}: gives the same output twice")
        clicks = [a for r in episodes[0]["records"] if r.get("type") == "tool_call" for a in r.get("actions") or []]
        n_clicks = sum(1 for a in clicks if a["action"] == "ACTION6")
        check(first["episodes"][0]["clicks"] == n_clicks and len(first["per_step"]) == len(clicks)
              + sum(1 for a in clicks if a.get("auto_reset_frame") is not None),
              f"{game}: every click is reported with its coordinates ({n_clicks} clicks)")
        files = frame_evidence.write_per_step(first, {1: saved[game]["trajectory"]})
        with open(files[0], encoding="utf-8") as handle:
            rows = handle.read().splitlines()
        check(rows[0].endswith(",click") and len(rows) == len(first["per_step"]) + 1,
              f"{game}: the per-step table has a click column and a row per step")

    # Part C: in ft09 each tile changes only when it is clicked, so every
    # tile is a rare region and its changes follow clicks inside it.
    root = tempfile.mkdtemp(prefix="fe15_")
    tiles = [(6, x, y) for y in (37, 45, 53) for x in (37, 45, 53) if (x, y) != (45, 45)]
    misses = [(6, 5, 5), (6, 10, 60)] * 6
    episode = play("ft09", tiles + misses, root)
    evidence = frame_evidence.build([{"seed": 1, "records": episode["records"],
                                      "frames": load_frames(episode["frames_path"])}])
    rare = [link for link in evidence["links"]]
    check(len(rare) >= 8 and all(link["after_click_inside_region"] == link["events"] for link in rare[:8]),
          f"ft09: Part C links each rare change to the click inside it ({len(rare)} rare regions)")
    check(evidence["episodes"][0]["clicks_no_change"] == len(misses),
          "ft09: clicks that changed nothing are counted as such")

    # No block and no clicks: a keyboard game where nothing moves.
    frames = np.zeros((4, 64, 64), dtype=np.int8)
    frames[2, 0, 0] = 3
    records = [{"type": "tool_call", "turn": 0, "actions": [
        {"action": "ACTION1", "args": {}, "action_index": i + 1, "frame_before": i, "frame_after": i + 1}
        for i in range(3)]}]
    still = frame_evidence.build([{"seed": 1, "records": records, "frames": frames}])
    text = frame_evidence.render(still, "vX")
    check(still.get("mode") == "clicks" and "no block was seen moving" in text and "ACTION1 x3" in text,
          "a game where no moving block is found: Part A reports the actions instead of a position")


# ---------------------------------------------------------------------------
# 3. fact-check ground truth, v0, sandbox
# ---------------------------------------------------------------------------


def factcheck_checks() -> None:
    print("fact-check ground truth per game (#15; the ls20 facts are not used)")
    expect = {
        "ft09": [({"kind": "count", "what": "moves_per_life", "value": 32}, "true"),
                 ({"kind": "goal_requirement", "requires": ["colour"]}, "true"),
                 ({"kind": "goal_requirement", "requires": ["position", "rotation"]}, "false")],
        "vc33": [({"kind": "count", "what": "moves_per_life", "value": 50}, "true"),
                 ({"kind": "goal_requirement", "requires": ["position"]}, "true"),
                 ({"kind": "location", "object": "goal", "rows": [28, 31], "cols": [36, 39]}, "true"),
                 ({"kind": "location", "object": "goal", "region": "bottom-left"}, "false")],
    }
    common = [({"kind": "move", "action": 6, "direction": "left", "cells": 2}, "unverifiable"),
              ({"kind": "move", "action": 1, "direction": "up", "cells": 5}, "unverifiable"),
              ({"kind": "move", "action": None, "direction": "up"}, "unverifiable"),
              ({"kind": "colour_role", "colour": "maroon", "role": "lives"}, "false"),
              ({"kind": "colour_role", "colour": "maroon", "role": "wall"}, "unverifiable"),
              ({"kind": "rotation_cause", "cause": "action", "action": 6}, "false"),
              ({"kind": "skill_output", "skill": "player_detector", "returns": "player_position"}, "unverifiable")]
    ls20 = ground_truth("ls20-9607627b")
    for game in GAMES:
        cfg = game_cfg(game)
        truth = ground_truth(cfg["game"])
        check(truth is not ls20 and truth.has_player is False and truth.click_actions == {6},
              f"{game}: its own ground truth (no player sprite, ACTION6 is a click)")
        from evolve.factcheck import make_skill_runner

        runner = make_skill_runner(build_v0(), [("start", [])], cfg)
        for claim, label in expect[game] + common:
            got, evidence = check_claim(claim, truth, {}, runner)
            check(got == label, f"{game}: {claim} -> {got}")


def v0_and_sandbox_checks() -> None:
    print("v0 for ft09/vc33 and the player's sandbox (#15)")
    v0, full = build_v0(["knowledge"]), build_v0()
    check(list(v0.prompts) == ["system", "format"] and v0.steps == full.steps and v0.skills == full.skills
          and v0.prompts["system"] == full.prompts["system"],
          "v0 without `knowledge`: the other prompts, steps and skills are #14's, unchanged")
    check(check_harness(v0) == [], "skill-name check on that v0: no missing names")
    sandbox = Sandbox(preload={}, time_limit_s=5)
    tries = ["import scorer", "open('scorer/ft09/GAME_NOTES.md').read()",
             "__import__('scorer')", "import os"]
    results = [sandbox.run(code) for code in tries]
    check(all(r.error for r in results), "the sandbox cannot import scorer/ or read files: "
          + "; ".join((r.error or "")[:40] for r in results))


# ---------------------------------------------------------------------------
# 4. leak test
# ---------------------------------------------------------------------------

# Facts from each game's GAME_NOTES.md, as patterns a text stating them would
# match. Internal names, the win rule, the solution, the budgets.
LEAK_PATTERNS = {
    "ft09": {
        "internal names": [r"\b(bsT|Hkx|NTi|gqb|irw|cgj|lpw|kCv|elp|wmW|UEq|Ycb|dzy)\b"],
        "win rule": [r"pixel\s+is\s+0", r"equal\w*\s+(to\s+)?(the\s+)?(pattern'?s?\s+)?cent(re|er)",
                     r"differ\w*\s+(from\s+)?(the\s+)?(pattern'?s?\s+)?cent(re|er)",
                     r"(must|should)\s+(be|become|turn)\s+(cyan|colou?r\s*8)\b"],
        "solution": [r"grid\s*\(\s*(18|26)\s*,\s*(18|22|26)\s*\)", r"\b4\s+(right\s+|correct\s+)?clicks?\s+(solve|clear|win)",
                     r"\(37,\s*37\),\s*\(37,\s*45\)"],
        "budget": [r"\b32\s+(tile\s+)?clicks", r"(clicks?|budget)\s+(of|is|=)\s+32\b"],
    },
    "vc33": {
        "internal names": [r"\b(0016uciqlhjlom|0010gnulkywfpz|0043nzrtobajqi|0025yfyiswdvoh|0022jvmlspyigc|"
                           r"xitrlzpbgu|ielczunthe|heczcoeosi|dwwmpxqsza|xowbpvmzbd|bcpuwqzpxw|rcbyiqlbza)\b"],
        "mechanics": [r"gravity", r"moves?\s+2\s+(grid\s+)?cells?\s+of\s+(width|height)", r"target\s+mark"],
        "solution": [r"button\s*\(?\s*30\s*,\s*16", r"\bx\s*(=|of|to)\s*17\b", r"\b3\s+clicks?\s+on\b",
                     r"\(\s*61\s*,\s*33\s*\)"],
        "budget": [r"\b50\s+(steps|clicks)"],
    },
}
SAMPLES = {
    "ft09": ["the pattern's pixel is 0 there", "tiles must be cyan", "click grid (18, 22)",
             "32 tile clicks", "the gqb palette"],
    "vc33": ["press button (30, 16)", "move the object to x = 17", "gravity points right", "50 steps",
             "heczcoeosi"],
}


def leaks(game: str, text: str) -> list[str]:
    found = []
    for fact, patterns in LEAK_PATTERNS[game].items():
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                found.append(f"{fact}: {match.group(0)!r}")
    return found


def leak_test() -> None:
    print("leak test: ft09/vc33 game-notes facts stay out of v0, the templates and the Meta LLM's input (#15)")
    for game in GAMES:
        check(all(leaks(game, s) for s in SAMPLES[game]), f"{game}: the scanner finds each kind of fact")
        cfg = game_cfg(game)
        v0 = build_v0(cfg["v0_drop_prompts"])
        v0_text = "\n".join([v0.render_system(int(cfg["budget"]["actions_per_turn"])),
                             *v0.prompts.values(), *v0.steps, *v0.skills.values()])
        check(leaks(game, v0_text) == [], f"{game}: v0 (prompts, steps, skills, rendered system prompt): none")
        templates = {
            "Meta LLM system prompt": META_SYSTEM, "its score paragraph for these games": SCORE_UNDISCLOSED,
            "sandbox API text": API_DOC, "frame-evidence code": inspect.getsource(frame_evidence),
            "Analyze code": inspect.getsource(analyze_mod),
        }
        for name, text in templates.items():
            check(leaks(game, text) == [], f"{game}: {name}: none {leaks(game, text) or ''}")

        # A full Meta LLM input, built as the run builds it: round 0 of the
        # #15 config with scripted episodes, Analyze, Propose's messages.
        root = tempfile.mkdtemp(prefix=f"leak15_{game}_")
        cfg["seeds"] = [1, 2]
        scripts = {1: NO_SOLUTION[game], 2: list(reversed(NO_SOLUTION[game]))}
        archive = loop.run(cfg, loop.Paths(root, title="leak test"), 0,
                           lambda seed: ScriptedPlayer(scripts[seed]), None, log=lambda _m: None)
        entry = archive["versions"][0]
        report = analyze_mod.analyze(build_v0(cfg["v0_drop_prompts"]), entry, archive["versions"], game=cfg["game"])
        messages = meta_messages(report, build_v0(cfg["v0_drop_prompts"]), cfg)
        full = "\n\n".join(m["content"] for m in messages)
        check("A. ACTIONS AND WHERE THEY LANDED" in full and SCORE_UNDISCLOSED in full
              and "position 0.4" not in full and "LEARNED SKILL LIBRARY" not in full,
              f"{game}: the Meta input has the click evidence and the neutral score paragraph ({len(full)} chars)")
        check(leaks(game, full) == [], f"{game}: a full Meta LLM input: none {leaks(game, full) or ''}")
        check(all("goal_parts" not in e and "goal_failure" not in e for e in report["episodes"])
              and report["goal_parts"] == {}, f"{game}: the Analyze report carries scores, no goal parts")
        stored = json.dumps(report, default=str)
        check(leaks(game, stored) == [], f"{game}: the stored Analyze report: none")
        goal = json.dumps(entry["episodes"][0]["goal"])
        check(("start_checks_failing" if game == "ft09" else "start_distance") in goal
              and str(list(cfg["score"]["weights"])[0]) not in full,
              f"{game}: (the scorer's own record holds its parts, so the scan is not vacuous; the part name "
              "is not in the Meta input)")


def main() -> None:
    saved = scorer_checks()
    frame_evidence_checks(saved)
    factcheck_checks()
    v0_and_sandbox_checks()
    leak_test()


if __name__ == "__main__":
    main()
    print("all #15 self-tests passed")
