"""Checkpoint and resume for runs that span several cluster jobs (issue #14, fix 4).

TC1 caps a job at 6 hours and the 5-round run needs more, so a run must stop
at any point and carry on in a later job without losing or repeating work.

What is on disk, in the run directory:

    run_state.json   where the run is: round, stage, seeds done, parent
                     version, git commit, config hash, SLURM job ids, time used
    run.lock         one writer at a time
    partial/         trajectories of episodes that were cut off (not counted)

The loop already writes every stage's output before the next stage starts
(reports/round_N/*.json, harnesses/vN, archive.json). Those files are the
record; run_state.json is the summary of them, saved after every finished
episode and every finished stage, and always by writing a temp file and
renaming it, so a kill never leaves it half-written. On resume, everything
already done is skipped; an episode that was cut off is moved to partial/ and
its seed is replayed from the start; a stage that was cut off has no output
file and so runs again from its start.

Time guard (the runner knows the job's limit):

- a unit (an episode batch or a stage) is not started if the longest one of
  its kind seen so far, times `factor` (1.5), does not fit before the stop time;
- at the stop time (5 h 40 min) the run stops, saves and exits;
- on SIGUSR1 (SLURM, 15 minutes before the limit) or SIGTERM it saves and
  exits at once.

There is no automatic resubmit: the next part starts when the user says so.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import threading
import time
from typing import Any, Callable

STATE_FILE = "run_state.json"
LOCK_FILE = "run.lock"
PARTIAL_DIR = "partial"

STAGES = ("analyze", "propose", "validate", "write", "evaluate", "gate")


class StopRun(Exception):
    """The run must stop now and be resumed later. Not a failure."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class LockError(RuntimeError):
    """Another process is writing to this run directory."""


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def write_json_atomic(path: str, payload: Any) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, default=str)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def read_json(path: str, default: Any = None) -> Any:
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def config_hash(cfg: dict[str, Any]) -> str:
    text = json.dumps(cfg, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def git_commit() -> str:
    """The code's commit: from git, or from the COMMIT file an upload without
    .git leaves at the repo root."""
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10)
        if out.returncode == 0 and out.stdout.strip():
            dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"],
                                   capture_output=True, text=True, timeout=10)
            return out.stdout.strip() + ("+dirty" if dirty.stdout.strip() else "")
    except (OSError, subprocess.SubprocessError):
        pass
    if os.path.exists("COMMIT"):
        with open("COMMIT", encoding="utf-8") as handle:
            return handle.read().strip() or "unknown"
    return "unknown"


# ---------------------------------------------------------------------------
# One writer
# ---------------------------------------------------------------------------


def _pid_alive(pid: int) -> bool:
    if os.name == "nt":
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))  # QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(handle)
        return code.value == 259  # STILL_ACTIVE
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _slurm_job_running(job_id: str) -> bool | None:
    """True/False if squeue can say; None if it cannot be asked."""
    try:
        out = subprocess.run(["squeue", "-h", "-j", str(job_id), "-o", "%T"],
                             capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        # squeue errors on an id it no longer knows: that job is gone.
        return False if "Invalid job id" in (out.stderr or "") else None
    return bool(out.stdout.strip())


class RunLock:
    """A lock file in the run directory. A lock left by a process that is gone
    (same host and the pid is dead, or its SLURM job is no longer queued) is
    taken over; any other lock stops the run."""

    def __init__(self, run_dir: str) -> None:
        self.path = os.path.join(run_dir, LOCK_FILE)
        self.held = False

    def _owner(self) -> dict[str, Any]:
        return {"host": socket.gethostname(), "pid": os.getpid(),
                "slurm_job_id": os.environ.get("SLURM_JOB_ID"), "acquired": _now()}

    def acquire(self, force: bool = False) -> str | None:
        """Take the lock. Returns a note if a stale lock was replaced."""
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        note = None
        for _attempt in range(2):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                try:
                    other = read_json(self.path) or {}
                except (json.JSONDecodeError, OSError):
                    other = {}
                stale = None
                if force:
                    stale = "--break-lock given"
                elif other.get("host") == socket.gethostname() and other.get("pid") and not _pid_alive(other["pid"]):
                    stale = f"its process {other['pid']} on this host is gone"
                elif other.get("slurm_job_id") and other.get("slurm_job_id") != os.environ.get("SLURM_JOB_ID"):
                    if _slurm_job_running(other["slurm_job_id"]) is False:
                        stale = f"its SLURM job {other['slurm_job_id']} is no longer queued"
                if stale is None:
                    raise LockError(
                        f"{self.path} is held by {other or 'an unreadable lock'}. Another job is writing to "
                        "this run. If that job is gone, rerun with --break-lock."
                    ) from None
                note = f"replaced a stale lock ({other}): {stale}"
                os.remove(self.path)
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(self._owner(), handle)
            self.held = True
            return note
        raise LockError(f"could not take {self.path}")

    def release(self) -> None:
        if self.held:
            with contextlib.suppress(OSError):
                os.remove(self.path)
            self.held = False


# ---------------------------------------------------------------------------
# The checkpoint
# ---------------------------------------------------------------------------


class Checkpoint:
    """State file + time guard + stop signal for one process's part of a run."""

    def __init__(
        self,
        run_dir: str,
        cfg: dict[str, Any],
        *,
        time_limit_s: float | None = None,
        stop_by_s: float | None = None,
        factor: float = 1.5,
        log: Callable[[str], None] = print,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.run_dir = run_dir
        self.path = os.path.join(run_dir, STATE_FILE)
        self.log = log
        self.clock = clock
        self.factor = float(factor)
        self.time_limit_s = time_limit_s
        self.stop_by_s = stop_by_s if stop_by_s is not None else time_limit_s
        self.started = clock()
        # Under SLURM the limit counts from the job's start, not this process's.
        self.offset_s = 0.0
        start = os.environ.get("SLURM_JOB_START_TIME")
        if start and start.isdigit():
            self.offset_s = max(0.0, time.time() - int(start))
        self.stop_event = threading.Event()
        self.stop_reason: str | None = None
        self._mutex = threading.RLock()
        self._timer: threading.Timer | None = None
        self._force: threading.Timer | None = None
        self.on_forced_exit: Callable[[], None] | None = None
        self.state = read_json(self.path)
        self.resumed = self.state is not None
        commit, digest = git_commit(), config_hash(cfg)
        if self.state is None:
            self.state = {
                "run_id": os.path.basename(os.path.normpath(run_dir)),
                "created": _now(),
                "status": "running",
                "round": 0, "stage": None, "stage_status": None,
                "seeds_done": [], "parent_version": None,
                "git_commit": commit, "git_commits": [commit],
                "config_hash": digest,
                "slurm_job_ids": [],
                "time_used_s": 0.0,
                "longest_s": {},
                "segments": [],
                "completed": [],
                "replayed_after_cutoff": [],
            }
        self.state["status"] = "running"
        self._base_time = float(self.state.get("time_used_s") or 0.0)
        if commit not in self.state["git_commits"]:
            self.state["git_commits"].append(commit)
        self.state["git_commit"] = commit
        job = os.environ.get("SLURM_JOB_ID")
        if job and job not in self.state["slurm_job_ids"]:
            self.state["slurm_job_ids"].append(job)
        self.segment = {"started": _now(), "slurm_job_id": job, "host": socket.gethostname(),
                        "git_commit": commit, "seconds": 0.0, "ended": None, "stop_reason": None}
        self.state["segments"].append(self.segment)

    # -- state ---------------------------------------------------------------

    def elapsed(self) -> float:
        """Seconds of this job used so far."""
        return self.offset_s + (self.clock() - self.started)

    def save(self) -> None:
        with self._mutex:
            self.segment["seconds"] = round(self.clock() - self.started, 1)
            self.state["time_used_s"] = round(self._base_time + (self.clock() - self.started), 1)
            self.state["updated"] = _now()
            write_json_atomic(self.path, self.state)

    def position(self, round_index: int, stage: str | None, status: str, parent: str | None,
                 seeds_done: list[int] | None = None) -> None:
        with self._mutex:
            self.state.update(round=round_index, stage=stage, stage_status=status, parent_version=parent)
            if seeds_done is not None:
                self.state["seeds_done"] = sorted(seeds_done)
            self.save()

    def _record(self, kind: str, seconds: float) -> None:
        longest = self.state["longest_s"]
        longest[kind] = round(max(float(longest.get(kind) or 0.0), seconds), 1)

    def episode_done(self, round_index: int, seed: int, seconds: float, seeds_done: list[int]) -> None:
        with self._mutex:
            self._record("episode", seconds)
            self.state["completed"].append({"round": round_index, "unit": "episode", "seed": seed,
                                            "seconds": round(seconds, 1), "at": _now()})
            self.state["seeds_done"] = sorted(seeds_done)
            self.save()

    def stage_done(self, round_index: int, stage: str, seconds: float) -> None:
        with self._mutex:
            self._record(stage, seconds)
            self.state["completed"].append({"round": round_index, "unit": "stage", "stage": stage,
                                            "seconds": round(seconds, 1), "at": _now()})
            self.state["stage_status"] = "done"
            self.save()

    def stage_was_completed(self, round_index: int, stage: str) -> bool:
        return any(c.get("unit") == "stage" and c["round"] == round_index and c["stage"] == stage
                   for c in self.state["completed"])

    def note_replay(self, round_index: int, seed: int, moved: list[str]) -> None:
        with self._mutex:
            self.state["replayed_after_cutoff"].append(
                {"round": round_index, "seed": seed, "partial_files": moved, "at": _now()})
            self.save()

    def finish(self, status: str, reason: str | None = None) -> None:
        with self._mutex:
            self.state["status"] = status
            self.segment["ended"] = _now()
            self.segment["stop_reason"] = reason
            self.save()

    # -- time guard ------------------------------------------------------------

    def remaining(self) -> float | None:
        return None if self.stop_by_s is None else self.stop_by_s - self.elapsed()

    def check_start(self, kind: str, what: str) -> None:
        """Raise StopRun instead of starting a unit that will not fit."""
        if self.stop_event.is_set():
            raise StopRun(self.stop_reason or "stop requested")
        remaining = self.remaining()
        if remaining is None:
            return
        longest = self.state["longest_s"].get(kind)
        need = float(longest) * self.factor if longest else 0.0
        if remaining <= 0 or need > remaining:
            raise StopRun(
                f"time guard: not starting {what}: it needs about {need / 60:.0f} min "
                f"(longest {kind} so far {float(longest or 0) / 60:.0f} min x {self.factor}), "
                f"{max(remaining, 0) / 60:.0f} min left before the stop time"
            )

    def request_stop(self, reason: str, grace_s: float) -> None:
        """Ask the run to stop; force the exit if it has not unwound in time."""
        with self._mutex:
            if self.stop_event.is_set():
                return
            self.stop_reason = reason
            self.stop_event.set()
        self.log(f"*** stop requested: {reason} (saving; forced exit in {grace_s:.0f}s if still running)")
        self._force = threading.Timer(grace_s, self._forced_exit)
        self._force.daemon = True
        self._force.start()

    def _forced_exit(self) -> None:
        # A model call can hang for minutes; the state on disk is already
        # complete up to the last finished unit, so leaving now loses nothing.
        with self._mutex:
            self.finish("paused", f"{self.stop_reason} (forced exit: a unit was still running)")
            if self.on_forced_exit:
                self.on_forced_exit()
        os._exit(0)

    def arm(self, usr1_grace_s: float = 10.0, guard_grace_s: float = 120.0) -> None:
        """Start the stop-time timer and install the signal handlers."""
        remaining = self.remaining()
        if remaining is not None:
            self._timer = threading.Timer(
                max(0.0, remaining),
                lambda: self.request_stop(f"time guard: stop time reached ({self.stop_by_s / 60:.0f} min)",
                                          guard_grace_s),
            )
            self._timer.daemon = True
            self._timer.start()

        def handler(signum: int, _frame: Any) -> None:
            name = signal.Signals(signum).name
            self.request_stop(f"{name} received", usr1_grace_s)

        for name in ("SIGUSR1", "SIGTERM"):
            if hasattr(signal, name) and threading.current_thread() is threading.main_thread():
                signal.signal(getattr(signal, name), handler)

    def disarm(self) -> None:
        for timer in (self._timer, self._force):
            if timer is not None:
                timer.cancel()


# ---------------------------------------------------------------------------
# Episodes that were cut off
# ---------------------------------------------------------------------------


def move_partial(run_dir: str, round_index: int, seed: int, files: list[str]) -> list[str]:
    """Move a cut-off episode's files to partial/round_N/. Returns the new paths."""
    moved = []
    target_dir = os.path.join(run_dir, PARTIAL_DIR, f"round_{round_index}")
    for path in files:
        if not os.path.exists(path):
            continue
        os.makedirs(target_dir, exist_ok=True)
        base = os.path.basename(path)
        target = os.path.join(target_dir, base)
        n = 1
        while os.path.exists(target):  # a seed can be cut off more than once
            stem, ext = base.split(".", 1) if "." in base else (base, "")
            target = os.path.join(target_dir, f"{stem}.cut{n}.{ext}".rstrip("."))
            n += 1
        shutil.move(path, target)
        moved.append(target.replace(os.sep, "/"))
    return moved
