"""Per-stage state.json, input hashing, freshness checks and locks.

A stage is fresh when its last run finished, its inputs and parameters hash the same as then,
and every output it recorded still exists. Inputs are fingerprinted by path and content hash.
The content hash is cached in `.hashes.json` against each file's size and mtime, so a file
whose size and mtime hold is not read again and `status` stays instant on large footage.
"""

import fcntl
import hashlib
import json
import os
import shutil
import time
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any, Literal

from pydantic import BaseModel, Field

from motion_studio import ENV_PREFIX
from motion_studio.errors import DependencyError, UserError
from motion_studio.paths import ProjectPaths, locks_dir

# Pipeline order; `status` reports them in this order and suggests the first one not fresh.
STAGES = ("ingest", "analyze", "plan", "music", "preview", "check", "final")

# Long-writing stages (ingest, render, music) refuse to start below this much free space.
MIN_FREE_GB = 20.0
MIN_FREE_ENV = f"{ENV_PREFIX}_MIN_FREE_GB"

HEAVY_MODEL_LOCK = "heavy-model.lock"


class StageRecord(BaseModel):
    status: Literal["done", "failed"]
    input_hash: str = ""
    inputs: list[str] = Field(default_factory=list)
    params_hash: str = ""
    outputs: list[str] = Field(default_factory=list)
    finished_at: datetime | None = None
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None


class State(BaseModel):
    schema_version: Literal[1] = 1
    stages: dict[str, StageRecord] = Field(default_factory=dict)
    # Fallback warnings raised while a stage runs, attached to its record when it finishes.
    pending_warnings: dict[str, list[str]] = Field(default_factory=dict)
    look_count: int = 0


def load_state(project: ProjectPaths) -> State:
    if not project.state.exists():
        return State()
    try:
        return State.model_validate_json(project.state.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise UserError(
            f"{project.state} is corrupt: {exc}",
            hint="delete it; every stage will then run again",
        ) from exc


def save_state(project: ProjectPaths, state: State) -> None:
    tmp = project.state.with_suffix(".json.tmp")
    tmp.write_text(state.model_dump_json(indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, project.state)


def stage_is_fresh(
    project: ProjectPaths,
    stage: str,
    inputs: Iterable[Path],
    *,
    params: Mapping[str, Any] | None = None,
) -> bool:
    record = load_state(project).stages.get(stage)
    if record is None or record.status != "done":
        return False
    return record.input_hash == _input_hash(project, inputs, _params_hash(params)) and all(
        (project.root / out).exists() for out in record.outputs
    )


def stage_status(
    project: ProjectPaths, stage: str
) -> Literal["pending", "done", "stale", "failed"]:
    """Judge a stage from what its last run recorded: its own inputs and parameters.

    Parameter changes since then are only caught when the stage itself runs `stage_is_fresh`.
    """
    record = load_state(project).stages.get(stage)
    if record is None:
        return "pending"
    if record.status == "failed":
        return "failed"
    inputs = [project.root / name for name in record.inputs]
    fresh = record.input_hash == _input_hash(project, inputs, record.params_hash) and all(
        (project.root / out).exists() for out in record.outputs
    )
    return "done" if fresh else "stale"


def mark_done(
    project: ProjectPaths,
    stage: str,
    inputs: Iterable[Path],
    *,
    outputs: Iterable[Path],
    params: Mapping[str, Any] | None = None,
    warnings: Iterable[str] = (),
) -> StageRecord:
    inputs = list(inputs)
    params_hash = _params_hash(params)
    state = load_state(project)
    record = StageRecord(
        status="done",
        input_hash=_input_hash(project, inputs, params_hash),
        inputs=[_relative(project, p) for p in inputs],
        params_hash=params_hash,
        outputs=[_relative(project, p) for p in outputs],
        finished_at=datetime.now(UTC),
        warnings=[*state.pending_warnings.pop(stage, []), *warnings],
    )
    state.stages[stage] = record
    save_state(project, state)
    return record


def mark_failed(project: ProjectPaths, stage: str, error: str) -> None:
    state = load_state(project)
    state.stages[stage] = StageRecord(
        status="failed",
        finished_at=datetime.now(UTC),
        warnings=state.pending_warnings.pop(stage, []),
        error=error,
    )
    save_state(project, state)


def record_warning(project: ProjectPaths, stage: str, message: str) -> None:
    """Record a fallback in state.json; the caller also prints it as a one-line warning."""
    state = load_state(project)
    state.pending_warnings.setdefault(stage, []).append(message)
    save_state(project, state)


@contextmanager
def project_lock(project: ProjectPaths) -> Iterator[None]:
    """Hold the per-project lock; a second command on the same project fails at once."""
    with open(project.lock, "a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise UserError(
                f"another command is already running on project {project.slug!r}",
                hint="wait for it to finish, then run this command again",
            ) from exc
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


@contextmanager
def heavy_model_lock(
    model: str,
    *,
    timeout_s: float | None = None,
    on_wait: Callable[[str], None] | None = None,
) -> Iterator[None]:
    """Hold the machine-wide lock that keeps one speech-to-text, face or music model loaded.

    Blocks while another process holds it; `on_wait` is called once with the holder's
    description. The kernel drops the lock if the holder dies, so a crash never wedges it.
    """
    path = locks_dir() / HEAVY_MODEL_LOCK
    with open(path, "a+", encoding="utf-8") as handle:
        _acquire(handle, model, timeout_s, on_wait)
        try:
            handle.seek(0)
            handle.truncate()
            handle.write(f"{model} pid={os.getpid()} since={datetime.now(UTC).isoformat()}\n")
            handle.flush()
            yield
        finally:
            handle.seek(0)
            handle.truncate()
            handle.flush()
            fcntl.flock(handle, fcntl.LOCK_UN)


def _acquire(
    handle: IO[str],
    model: str,
    timeout_s: float | None,
    on_wait: Callable[[str], None] | None,
) -> None:
    deadline = None if timeout_s is None else time.monotonic() + timeout_s
    notified = False
    while True:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except BlockingIOError:
            holder = _holder(handle)
            if on_wait is not None and not notified:
                on_wait(holder)
                notified = True
            if deadline is not None and time.monotonic() >= deadline:
                raise DependencyError(
                    f"timed out waiting for the heavy-model lock to load {model}; held by {holder}",
                    hint="wait for the other model run to finish, then retry",
                ) from None
            time.sleep(0.1)


def _holder(handle: IO[str]) -> str:
    handle.seek(0)
    return handle.read().strip() or "another process"


def free_disk_gb(path: Path) -> float:
    existing = path
    while not existing.exists() and existing != existing.parent:
        existing = existing.parent
    return shutil.disk_usage(existing).free / 1e9


def min_free_gb() -> float:
    """The free-disk threshold in GB: the env override if set, else MIN_FREE_GB."""
    value = os.environ.get(MIN_FREE_ENV)
    try:
        return float(value) if value else MIN_FREE_GB
    except ValueError as exc:
        raise UserError(f"{MIN_FREE_ENV}={value!r} is not a number") from exc


def ensure_free_disk(path: Path, *, threshold_gb: float | None = None) -> float:
    """Return free GB on `path`'s volume, or raise before a long write can fail halfway."""
    threshold = min_free_gb() if threshold_gb is None else threshold_gb
    free = free_disk_gb(path)
    if free < threshold:
        raise DependencyError(
            f"only {free:.1f} GB free on the volume holding {path}; need {threshold:.0f} GB",
            hint="free some disk space, or reclaim caches with `clean <slug>`",
        )
    return free


def _relative(project: ProjectPaths, path: Path) -> str:
    try:
        return path.resolve().relative_to(project.root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _params_hash(params: Mapping[str, Any] | None) -> str:
    text = json.dumps(params or {}, sort_keys=True, default=str)
    return hashlib.sha256(text.encode()).hexdigest()


def _input_hash(project: ProjectPaths, inputs: Iterable[Path], params_hash: str) -> str:
    digest = hashlib.sha256(params_hash.encode())
    cache = _HashCache(project.hash_cache)
    for path in sorted(inputs, key=lambda p: _relative(project, p)):
        for line in _fingerprint(project, path, cache):
            digest.update(line.encode())
            digest.update(b"\n")
    cache.save()
    return digest.hexdigest()


def _fingerprint(project: ProjectPaths, path: Path, cache: "_HashCache") -> Iterator[str]:
    if path.is_dir():
        files = sorted(p for p in path.rglob("*") if p.is_file() and not p.name.startswith("."))
        yield f"dir {_relative(project, path)} {len(files)}"
        for file in files:
            yield from _fingerprint(project, file, cache)
    elif path.is_file():
        yield f"file {_relative(project, path)} {cache.digest(path)}"
    else:
        yield f"missing {_relative(project, path)}"


class _HashCache:
    """Content hashes keyed by absolute path, trusted while the file's size and mtime hold."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.dirty = False
        self.entries: dict[str, list[Any]] = {}
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if isinstance(loaded, dict):
            self.entries = loaded  # pyright: ignore[reportUnknownMemberType]

    def digest(self, file: Path) -> str:
        key = str(file.resolve())
        stat = file.stat()
        entry = self.entries.get(key)
        if entry is not None and entry[:2] == [stat.st_size, stat.st_mtime_ns]:
            return str(entry[2])
        with open(file, "rb") as handle:
            value = hashlib.file_digest(handle, "sha256").hexdigest()
        self.entries[key] = [stat.st_size, stat.st_mtime_ns, value]
        self.dirty = True
        return value

    def save(self) -> None:
        if not self.dirty or not self.path.parent.is_dir():
            return
        tmp = self.path.with_name(f"{self.path.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(self.entries), encoding="utf-8")
        os.replace(tmp, self.path)
        self.dirty = False
