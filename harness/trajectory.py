"""Trajectory logging (Phase 2).

One JSONL record per step at data/trajectories/<round>/<game>/<seed>.jsonl, plus
the raw frames as .npy so an episode can be replayed exactly.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

import numpy as np

TRAJ_ROOT = os.path.join("data", "trajectories")
FRAME_ROOT = os.path.join("data", "frames")

# Record schema required by the issue; asserted on write so a field cannot be
# silently dropped and break the mining step later.
REQUIRED_FIELDS = (
    "game",
    "seed",
    "round",
    "step",
    "frame_hash",
    "objects",
    "action",
    "args",
    "model_thought",
    "scratchpad",
    "next_frame_hash",
    "frame_diff",
    "state",
    "levels_completed",
    "tokens_in",
    "tokens_out",
    "latency_ms",
)


def frame_hash(grid: np.ndarray) -> str:
    """Stable content hash of a grid, used to detect loops and replay states."""
    if grid.size == 0:
        return "empty"
    return hashlib.sha1(
        np.ascontiguousarray(grid.astype(np.int16)).tobytes()
        + str(grid.shape).encode()
    ).hexdigest()[:16]


def trajectory_path(round_index: int, game_id: str, seed: int) -> str:
    return os.path.join(
        TRAJ_ROOT, f"round{round_index}", game_id, f"{seed}.jsonl"
    )


def frames_path(round_index: int, game_id: str, seed: int) -> str:
    return os.path.join(FRAME_ROOT, f"round{round_index}", game_id, f"{seed}.npy")


class TrajectoryWriter:
    """Append-only JSONL writer plus a frame buffer flushed at episode end."""

    def __init__(self, round_index: int, game_id: str, seed: int) -> None:
        self.path = trajectory_path(round_index, game_id, seed)
        self.frames_path = frames_path(round_index, game_id, seed)
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        os.makedirs(os.path.dirname(self.frames_path), exist_ok=True)
        # Truncate: a re-run of the same game/seed/round replaces its data
        # rather than appending a second episode into the same file.
        self._handle = open(self.path, "w", encoding="utf-8")
        self._frames: list[np.ndarray] = []

    def add_frame(self, grid: np.ndarray) -> None:
        self._frames.append(np.asarray(grid, dtype=np.int16))

    def write(self, record: dict[str, Any]) -> None:
        missing = [field for field in REQUIRED_FIELDS if field not in record]
        if missing:
            raise RuntimeError(f"trajectory record missing fields: {missing}")
        self._handle.write(json.dumps(record, separators=(",", ":")) + "\n")
        self._handle.flush()

    def close(self) -> None:
        self._handle.close()
        if not self._frames:
            return
        shapes = {frame.shape for frame in self._frames}
        if len(shapes) == 1:
            np.save(self.frames_path, np.stack(self._frames))
        else:
            # Ragged (a game resized its grid): keep each frame separately.
            np.savez_compressed(
                self.frames_path.replace(".npy", ".npz"),
                **{f"f{i}": frame for i, frame in enumerate(self._frames)},
            )

    def __enter__(self) -> "TrajectoryWriter":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


def read_trajectory(path: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def iter_trajectories(
    round_index: int, game_ids: list[str] | None = None
) -> list[tuple[str, int, list[dict[str, Any]]]]:
    """Load (game_id, seed, records) for a round, optionally filtered by game."""
    root = os.path.join(TRAJ_ROOT, f"round{round_index}")
    if not os.path.isdir(root):
        return []
    out: list[tuple[str, int, list[dict[str, Any]]]] = []
    for game_id in sorted(os.listdir(root)):
        if game_ids is not None and game_id not in game_ids:
            continue
        game_dir = os.path.join(root, game_id)
        if not os.path.isdir(game_dir):
            continue
        for name in sorted(os.listdir(game_dir)):
            if not name.endswith(".jsonl"):
                continue
            seed = int(os.path.splitext(name)[0])
            out.append((game_id, seed, read_trajectory(os.path.join(game_dir, name))))
    return out
