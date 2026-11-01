"""Post-hoc check of #9's episodes against ls20's real Level-1 win condition.

Computed after the run, not used by the gate. The gate's progress term reuses
#8's approach distance (analysis/approach.py), whose "target" is the blue/black
object near (32, 21). Reading the game's own code shows that object is a
rotation switch, not the goal:

- Level 1 clears when the player sprite stands on the goal sprite AND its
  rotation matches the goal's (shape and colour already match at the start).
- The goal is the grey box at the top (sprite top-left x=34, y=10).
- The player starts with rotation index 3 and needs 0; bumping the switch
  advances the rotation by one.

So this module reports the two real sub-goals separately, without folding them
into a new composite score chosen after seeing the results:

- rotated:     did the player ever hold the goal's rotation?
- goal:        the closest the player got to the goal square (Manhattan, cells,
               between sprite top-lefts), overall and while correctly rotated.

It replays each saved episode's actions through the same EpisodeAPI the run
used (so resets and GAME_OVER auto-resets match; ls20 is deterministic) and
reads the game's internal state after every action. The attribute names below
are the game's own (obfuscated) names. This is evaluation-side knowledge only:
no harness, prompt or Meta LLM input ever sees it.
"""

from __future__ import annotations

import json
import os
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import yaml
from matplotlib.lines import Line2D

from analysis.figures import ROUND_COLOUR, SURFACE, TEXT_PRIMARY, TEXT_SECONDARY, _style
from evolve.action_loop import EpisodeAPI, TurnOver
from evolve.replay import make_env

# Ls20 internals, read from environment_files/ls20/9607627b/ls20.py.
PLAYER = "gudziatsk"          # the player sprite
GOALS = "plrpelhym"           # goal sprites (one on Level 1)
ROTATION = "cklxociuu"        # player's rotation index
GOAL_ROTATION = "ehwheiwsk"   # required rotation index per goal


def _tool_calls(path: str) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as handle:
        return [r for r in map(json.loads, handle) if r.get("type") == "tool_call"]


def trace_episode(trajectory: str, cfg: dict[str, Any]) -> dict[str, Any]:
    """Player position and rotation after every logged action of one episode."""
    actions = [a for r in _tool_calls(trajectory) for a in (r.get("actions") or [])]
    env = make_env(cfg["game"])
    api = EpisodeAPI(env, actions_per_turn=10**9, max_actions=10**9, max_resets=10**9)
    game = env._game
    goal = getattr(game, GOALS)[0]
    goal_xy = (goal.x, goal.y)
    need = getattr(game, GOAL_ROTATION)[0]
    player = getattr(game, PLAYER)
    start_xy = (player.x, player.y)
    steps = []
    for item in actions:
        api.begin_turn(0)
        action_id = 0 if item["action"] == "RESET" else int(item["action"].replace("ACTION", ""))
        args = item.get("args") or {}
        try:
            api.action(action_id, **({"x": args["x"], "y": args["y"]} if args else {}))
        except TurnOver:
            steps.append({"x": goal_xy[0], "y": goal_xy[1], "rotation": need, "cleared": True})
            break
        game = env._game  # a reset re-clones the level, so re-read every step
        player = getattr(game, PLAYER)
        steps.append({"x": player.x, "y": player.y, "rotation": getattr(game, ROTATION), "cleared": False})
    return {"goal_xy": goal_xy, "start_xy": start_xy, "need_rotation": need, "steps": steps}


def subgoals(trace: dict[str, Any]) -> dict[str, Any]:
    gx, gy = trace["goal_xy"]
    need = trace["need_rotation"]
    start = abs(trace["start_xy"][0] - gx) + abs(trace["start_xy"][1] - gy)
    dist = [abs(s["x"] - gx) + abs(s["y"] - gy) for s in trace["steps"]]
    rotated = [s["rotation"] == need for s in trace["steps"]]
    first = next((i + 1 for i, ok in enumerate(rotated) if ok), None)
    rotated_dist = [d for d, ok in zip(dist, rotated) if ok]
    return {
        "actions": len(trace["steps"]),
        "cleared": any(s["cleared"] for s in trace["steps"]),
        "start_distance_to_goal": start,
        "closest_to_goal": min(dist) if dist else start,
        "rotated": first is not None,
        "first_rotated_action": first,
        "actions_rotated": sum(rotated),
        "closest_to_goal_while_rotated": min(rotated_dist) if rotated_dist else None,
        "actions_on_goal": sum(1 for d in dist if d == 0),
    }


def analyse_run(root: str, config: str = "config_evolve.yaml") -> dict[str, Any]:
    with open(config, encoding="utf-8") as handle:
        cfg = yaml.safe_load(handle)
    with open(os.path.join(root, "archive.json"), encoding="utf-8") as handle:
        archive = json.load(handle)
    out = {"note": "post hoc; not used by the gate. See analysis/ls20_subgoals.py.", "versions": []}
    for entry in archive["versions"]:
        episodes = []
        for episode in entry["episodes"]:
            result = subgoals(trace_episode(episode["trajectory"], cfg))
            result.update(episode=episode["episode"], gate_score=episode["score"])
            episodes.append(result)
        out["versions"].append({
            "version": entry["version"],
            "decision": (entry.get("gate") or {}).get("decision", "baseline"),
            "episodes": episodes,
        })
    return out


def figure_subgoals(result: dict[str, Any], out_dir: str) -> str:
    """Closest approach to the real goal per episode, marked by whether the
    player held the goal's rotation at the time."""
    versions = result["versions"]
    figure, axes = plt.subplots(figsize=(8.6, 4.4), facecolor=SURFACE)
    _style(axes, grid_axis="y")
    rotated_style = {"colour": ROUND_COLOUR[0], "marker": "o", "label": "closest while correctly rotated"}
    any_style = {"colour": ROUND_COLOUR[1], "marker": "X", "label": "closest at any rotation"}
    top = 0
    labels = []
    for index, entry in enumerate(versions):
        n = len(entry["episodes"])
        jitter = np.linspace(-0.24, 0.24, n) if n > 1 else [0.0]
        for offset, episode in zip(jitter, entry["episodes"]):
            top = max(top, episode["start_distance_to_goal"])
            # The episode's two marks sit side by side, joined, so equal values
            # don't hide one another.
            x_any, x_rot = index + offset - 0.045, index + offset + 0.045
            rotated = episode["closest_to_goal_while_rotated"]
            if rotated is not None:
                axes.plot([x_any, x_rot], [episode["closest_to_goal"], rotated], color=TEXT_SECONDARY,
                          linewidth=0.8, zorder=2)
                axes.scatter([x_rot], [rotated], s=60, marker=rotated_style["marker"],
                             color=rotated_style["colour"], edgecolors=SURFACE, linewidths=1.5, zorder=4)
            axes.scatter([x_any], [episode["closest_to_goal"]], s=60, marker=any_style["marker"],
                         color=any_style["colour"], edgecolors=SURFACE, linewidths=1.5, zorder=3)
        n_rot = sum(e["rotated"] for e in entry["episodes"])
        labels.append(f"{entry['version']} ({entry['decision']})\nrotated in {n_rot}/{n}")
    axes.axhline(0, color=TEXT_SECONDARY, linewidth=0.8, zorder=1)
    axes.annotate("on the goal square (clears if correctly rotated)", (1.0, 0), xycoords=("axes fraction", "data"),
                  textcoords="offset points", xytext=(-2, 4), ha="right", fontsize=7, color=TEXT_SECONDARY)
    axes.set_xticks(range(len(versions)))
    axes.set_xticklabels(labels, fontsize=8)
    axes.set_ylim(-1, top + 2)
    axes.set_ylabel("Distance to the real goal (cells)", fontsize=9, color=TEXT_PRIMARY)
    axes.set_title("How close each episode got to ls20's real goal (post hoc, not used by the gate)",
                   fontsize=11, color=TEXT_PRIMARY, loc="left")
    handles = [Line2D([], [], marker=s["marker"], linestyle="none", color=s["colour"], markersize=8,
                      label=s["label"]) for s in (any_style, rotated_style)]
    axes.legend(handles=handles, frameon=False, fontsize=8, loc="upper center",
                bbox_to_anchor=(0.5, -0.2), ncol=2)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "real_goal_by_version.png")
    figure.savefig(path, dpi=160, bbox_inches="tight", facecolor=SURFACE)
    plt.close(figure)
    return path


def main(root: str) -> None:
    result = analyse_run(root)
    path = os.path.join(root, "subgoals.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=1)
    print("wrote", path)
    print("wrote", figure_subgoals(result, os.path.join(root, "figures")))
    for entry in result["versions"]:
        for e in entry["episodes"]:
            print(f"  {entry['version']} ep{e['episode']} gate={e['gate_score']:.3f} rotated={e['rotated']} "
                  f"(first at action {e['first_rotated_action']}) closest_to_goal={e['closest_to_goal']} "
                  f"while_rotated={e['closest_to_goal_while_rotated']} on_goal={e['actions_on_goal']}")


if __name__ == "__main__":
    import sys

    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join("results", "evolve"))
