"""Failure modes of issue #12's episodes, measured from the logged game state.

    python -m analysis.failure_modes12 [root]   ->  <root>/failure_modes.json

Per finished episode:

- blocked moves: ACTION1-4 that left the player where it was (a wall, or the
  goal blocking a wrongly rotated player). Each still costs one tick of the
  42-move counter, and when the counter runs out a life is lost, which puts
  the player back at the start with its rotation reset;
- whether it reached the square directly under the goal with the wrong
  rotation, and how often it then pressed ACTION1 into the goal;
- when it first matched the goal's rotation, and how much of the counter was
  left at that moment;
- how close it got to the goal while rotated, and whether a lost life undid
  the rotation.
"""

from __future__ import annotations

import glob
import json
import os
import sys
from typing import Any

from evolve.action_loop import read_records
from evolve.goal_score import level1_maze

MOVES = ("ACTION1", "ACTION2", "ACTION3", "ACTION4")


def episode_modes(records: list[dict[str, Any]], maze: Any) -> dict[str, Any]:
    head = next(r for r in records if r.get("type") == "episode_start")
    goal = head["start_state"]["goals"][0]
    under = (goal["x"], goal["y"] + maze.step)
    need = goal["rotation"]
    prev = head["start_state"]
    out = {"moves": 0, "blocked_moves": 0, "reached_under_goal_unrotated": False, "presses_into_goal": 0,
           "rotations": [], "closest_moves_while_rotated": None, "rotation_lost_to_life_loss": 0}
    for record in records:
        if record.get("type") != "tool_call":
            continue
        for item in record.get("actions") or []:
            state = item["game_state"]
            same_life = state["lives"] == prev["lives"]
            if item["action"] in MOVES:
                out["moves"] += 1
                if (state["x"], state["y"]) == (prev["x"], prev["y"]) and same_life:
                    out["blocked_moves"] += 1
                    if (state["x"], state["y"]) == under and item["action"] == "ACTION1":
                        out["presses_into_goal"] += 1
            if state["rotation"] == need and prev["rotation"] != need and same_life:
                out["rotations"].append({"action": item["action_index"], "counter_left_before": prev["moves_left"]})
            if prev["rotation"] == need and state["rotation"] != need and not same_life:
                out["rotation_lost_to_life_loss"] += 1
            if state["rotation"] == need:
                moves = maze.moves_to_goal(state["x"], state["y"])
                best = out["closest_moves_while_rotated"]
                out["closest_moves_while_rotated"] = moves if best is None else min(best, moves)
            elif (state["x"], state["y"]) == under:
                out["reached_under_goal_unrotated"] = True
            prev = item.get("auto_reset_state") or state
    return out


def analyse(root: str) -> dict[str, Any]:
    archive = json.load(open(os.path.join(root, "archive.json"), encoding="utf-8"))
    maze = level1_maze(archive["config"]["game"])
    per_version, episodes = [], []
    for entry in archive["versions"]:
        rows = []
        for episode in entry["episodes"]:
            row = episode_modes(read_records(episode["trajectory"]), maze)
            row.update(version=entry["version"], seed=episode["seed"], progress=episode["score"])
            rows.append(row)
        episodes += rows
        per_version.append({
            "version": entry["version"],
            "blocked_share": round(sum(r["blocked_moves"] for r in rows) / max(1, sum(r["moves"] for r in rows)), 3),
            "under_goal_unrotated": sum(r["reached_under_goal_unrotated"] for r in rows),
            "presses_into_goal": sum(r["presses_into_goal"] for r in rows),
            "rotated": sum(bool(r["rotations"]) for r in rows),
            "first_rotation_actions": [r["rotations"][0]["action"] for r in rows if r["rotations"]],
            "closest_while_rotated": [r["closest_moves_while_rotated"] for r in rows
                                      if r["closest_moves_while_rotated"] is not None],
            "n": len(rows),
        })
    total_moves = sum(r["moves"] for r in episodes)
    totals = {
        "episodes": len(episodes),
        "moves": total_moves,
        "blocked_moves": sum(r["blocked_moves"] for r in episodes),
        "blocked_share": round(sum(r["blocked_moves"] for r in episodes) / max(1, total_moves), 3),
        "reached_under_goal_unrotated": sum(r["reached_under_goal_unrotated"] for r in episodes),
        "presses_into_goal": sum(r["presses_into_goal"] for r in episodes),
        "max_presses_into_goal": max((r["presses_into_goal"] for r in episodes), default=0),
        "rotated": sum(bool(r["rotations"]) for r in episodes),
        "rotated_after_action_130": sum(1 for r in episodes if r["rotations"] and r["rotations"][0]["action"] > 130),
        "within_3_moves_while_rotated": sum(1 for r in episodes if r["closest_moves_while_rotated"] is not None
                                            and r["closest_moves_while_rotated"] <= 3),
        "rotation_lost_to_life_loss": sum(1 for r in episodes if r["rotation_lost_to_life_loss"]),
    }
    return {"totals": totals, "per_version": per_version, "episodes": episodes}


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.join("results", "evolve_12")
    result = analyse(root)
    path = os.path.join(root, "failure_modes.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=1)
        handle.write("\n")
    print("wrote", path)
    print(json.dumps(result["totals"], indent=1))
    for v in result["per_version"]:
        print(v)
