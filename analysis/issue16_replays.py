"""Issue #16: how each game's final parent finished its winning episode,
frame by frame. No new play: everything comes from the saved frames and
trajectory.

    python -m analysis.issue16_replays     # writes results/issue16/replays/

Per game, the final parent's cleared episode with the fewest actions:
- <game>_<version>_seed<k>.gif         one frame per action (the frame after
                                       it), a ring on the click, and the
                                       action-record line for that action
- <game>_<version>_seed<k>_frames.png  every frame on one sheet
- replays.json                         the same frames, captions and each
                                       turn's reasoning, for the results page
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from analysis.evolution import _save
from analysis.figures import SURFACE, TEXT_PRIMARY
from analysis.issue16_report import _board, _local, final_parent, load_archive, root16, version
from evolve.action_loop import load_frames, read_records
from evolve.frame_diff import record_line
from evolve.replay import tool_calls
from harness.model import _PALETTE_RGB

GAMES = ("ft09", "vc33")
OUT_DIR = os.path.join("results", "issue16", "replays")
SCALE = 8
CAPTION_H = 64
EXCERPT_CHARS = 600


def _reasoning(reply: str) -> str:
    """The turn's reply up to its code block, whitespace collapsed."""
    text = reply.split("```")[0]
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= EXCERPT_CHARS else text[:EXCERPT_CHARS].rsplit(" ", 1)[0] + " …"


def timeline(game: str) -> dict[str, Any]:
    root = root16(game)
    archive = load_archive(root)
    entry = version(archive, final_parent(archive))
    episode = min((e for e in entry["episodes"] if e["solved"]), key=lambda e: (e["actions_used"], e["seed"]))
    frames = load_frames(_local(episode["frames"], root))
    calls = tool_calls(read_records(_local(episode["trajectory"], root)))
    steps: list[dict[str, Any]] = [{"frame": 0, "turn": int(calls[0]["turn"]), "step": 0, "click": None,
                                    "kind": "start", "caption": "start of the episode"}]
    for call in calls:
        for item in call.get("actions") or []:
            args = item.get("args") or {}
            click = [int(args["x"]), int(args["y"])] if "x" in args else None
            record = item.get("record")
            caption = record_line(record) if record else f"step {item['action_index']} · {item['action']}"
            kind = "game_over" if item.get("state") == "GAME_OVER" else "action"
            if int(item.get("levels_completed") or 0) >= 1:
                kind = "cleared"
                caption += " · Level 1 cleared; the frame shown is the start of Level 2"
            steps.append({"frame": int(item["frame_after"]), "turn": int(call["turn"]),
                          "step": int(item["action_index"]), "click": click, "kind": kind, "caption": caption})
            if "auto_reset_frame" in item:
                steps.append({"frame": int(item["auto_reset_frame"]), "turn": int(call["turn"]),
                              "step": int(item["action_index"]), "click": None, "kind": "reset",
                              "caption": "game over: the harness restarted the level (the code kept running)"})
    turns = {int(c["turn"]): {"reasoning": _reasoning(str(c.get("reply") or "")),
                              "skills": c.get("skill_calls") or {},
                              "actions": len(c.get("actions") or [])} for c in calls}
    return {"game": game, "version": entry["version"], "seed": int(episode["seed"]),
            "actions": int(episode["actions_used"]), "turns_used": len(calls), "frames": frames,
            "steps": steps, "turns": turns}


def _rgb(grid: np.ndarray) -> np.ndarray:
    rgb = np.zeros((*grid.shape, 3), dtype=np.uint8)
    for value in np.unique(grid):
        rgb[grid == value] = _PALETTE_RGB.get(int(value), (80, 80, 80))
    return rgb


def _font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def write_gif(data: dict[str, Any]) -> str:
    frames = data["frames"]
    height, width = np.asarray(frames[0]).shape
    head, body = _font(15), _font(13)
    images, durations = [], []
    last_step = data["actions"]
    for item in data["steps"]:
        board = Image.fromarray(_rgb(np.asarray(frames[item["frame"]]))).resize(
            (width * SCALE, height * SCALE), Image.NEAREST)
        canvas = Image.new("RGB", (width * SCALE, height * SCALE + CAPTION_H), (252, 252, 251))
        canvas.paste(board, (0, 0))
        draw = ImageDraw.Draw(canvas)
        if item["click"] and item["kind"] != "cleared":
            cx, cy = (item["click"][0] + 0.5) * SCALE, (item["click"][1] + 0.5) * SCALE
            radius = 2.6 * SCALE
            draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline=(255, 255, 255), width=4)
            draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline=(11, 11, 11), width=2)
        top = height * SCALE + 8
        label = f"{data['game']} · {data['version']} · seed {data['seed']} · turn {item['turn']} · step {item['step']}/{last_step}"
        colour = {"game_over": (192, 60, 28), "reset": (192, 60, 28), "cleared": (18, 132, 90)}.get(item["kind"], (11, 11, 11))
        draw.text((10, top), label, fill=colour, font=head)
        caption = item["caption"] if len(item["caption"]) <= 70 else item["caption"][:69] + "…"
        draw.text((10, top + 24), caption, fill=(82, 81, 78), font=body)
        images.append(canvas)
        durations.append({"start": 1500, "game_over": 1800, "reset": 2000, "cleared": 3500}.get(
            item["kind"], 1300 if len(data["steps"]) < 10 else 650))
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"{data['game']}_{data['version']}_seed{data['seed']}.gif")
    images[0].save(path, save_all=True, append_images=images[1:], duration=durations, loop=0, optimize=True)
    return path


def write_sheet(data: dict[str, Any]) -> str:
    steps = data["steps"]
    cols = min(8, len(steps))
    rows = int(np.ceil(len(steps) / cols))
    figure, grid = plt.subplots(rows, cols, figsize=(2.15 * cols, 2.45 * rows + 0.5), facecolor=SURFACE,
                                squeeze=False)
    for index, item in enumerate(steps):
        axes = grid[index // cols][index % cols]
        _board(axes, data["frames"][item["frame"]])
        if item["click"] and item["kind"] != "cleared":
            axes.scatter([item["click"][0]], [item["click"][1]], s=80, facecolors="none", edgecolors="#ffffff",
                         linewidths=2.2, zorder=3)
            axes.scatter([item["click"][0]], [item["click"][1]], s=80, facecolors="none", edgecolors=TEXT_PRIMARY,
                         linewidths=1, zorder=4)
        if item["kind"] == "start":
            title, colour = "start", TEXT_PRIMARY
        elif item["kind"] == "reset":
            title, colour = "level restarted", "#c03c1c"
        elif item["kind"] == "cleared":
            title, colour = f"{item['step']}: cleared (Level 2 shown)", "#12845a"
        else:
            where = f" ({item['click'][0]}, {item['click'][1]})" if item["click"] else ""
            title = f"{item['step']}: click{where}" + (" GAME OVER" if item["kind"] == "game_over" else "")
            colour = "#c03c1c" if item["kind"] == "game_over" else TEXT_PRIMARY
        axes.set_title(f"t{item['turn']} · {title}", fontsize=7.2, color=colour)
    for index in range(len(steps), rows * cols):
        grid[index // cols][index % cols].set_visible(False)
    figure.suptitle(f"{data['game']}: {data['version']}, seed {data['seed']}, every frame (the frame after each "
                    f"action; ring = the click; t = turn)", fontsize=10.5, color=TEXT_PRIMARY, x=0.01, ha="left")
    figure.subplots_adjust(top=1 - 0.55 / (2.45 * rows + 0.5), hspace=0.32, wspace=0.06)
    return _save(figure, OUT_DIR, f"{data['game']}_{data['version']}_seed{data['seed']}_frames.png")


def page_data(items: list[dict[str, Any]]) -> dict[str, Any]:
    out = {"palette": ["#%02x%02x%02x" % _PALETTE_RGB[v] for v in range(16)], "games": []}
    for data in items:
        out["games"].append({
            **{k: data[k] for k in ("game", "version", "seed", "actions", "turns_used", "steps")},
            "turns": {str(k): v for k, v in data["turns"].items()},
            "frames": ["".join("%x" % int(v) for v in np.asarray(f).ravel()) for f in data["frames"]],
            "size": list(np.asarray(data["frames"][0]).shape),
        })
    return out


def main() -> int:
    items = [timeline(game) for game in GAMES]
    for data in items:
        print("wrote", write_gif(data))
        print("wrote", write_sheet(data))
        print(f"  {data['game']}: {data['version']} seed {data['seed']}, {data['actions']} actions, "
              f"{data['turns_used']} turns, {len(data['steps'])} frames shown")
    path = os.path.join(OUT_DIR, "replays.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(page_data(items), handle, ensure_ascii=False)
    print("wrote", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
