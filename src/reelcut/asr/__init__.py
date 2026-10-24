"""Speech-to-text: Silero VAD, language ID and word-level transcripts from a model subprocess.

`transcribe_clips()` is the entry point for every stage that needs speech (analyze, check). It
runs `reelcut.asr.worker` in a child process while holding the machine-wide heavy-model lock,
so the model's memory is returned to the system as soon as the child exits.
"""

import os
import platform
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from reelcut import APP_NAME
from reelcut.analysis.models import LanguageGuess, Span, TranscribedWord
from reelcut.errors import DependencyError, InternalError
from reelcut.paths import models_dir
from reelcut.state import heavy_model_lock

Backend = Literal["mlx-whisper", "faster-whisper"]
BACKENDS: tuple[Backend, ...] = ("mlx-whisper", "faster-whisper")

# Replaces the worker command (`python -m reelcut.asr.worker`) with another executable.
WORKER_ENV = f"{APP_NAME.upper()}_ASR_WORKER"
STDERR_TAIL = 20


@dataclass(frozen=True)
class ModelRef:
    repo: str
    revision: str
    python_module: str
    extra: str


# Revisions pinned on 2026-10-24 so a re-run transcribes with the same weights.
DEFAULT_MODELS: dict[Backend, ModelRef] = {
    "mlx-whisper": ModelRef(
        "mlx-community/whisper-large-v3-turbo",
        "a4aaeec0636e6fef84abdcbe3544cb2bf7e9f6fb",
        "mlx_whisper",
        "mac",
    ),
    "faster-whisper": ModelRef(
        "dropbox-dash/faster-whisper-large-v3-turbo",
        "0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf",
        "faster_whisper",
        "cpu",
    ),
}


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SpeechJob(_Model):
    """One audio file to analyse. `language` None means detect it among `candidates`."""

    id: str
    wav: Path = Field(description="16 kHz mono WAV.")
    language: str | None = None
    candidates: list[str]
    prompts: dict[str, str] = Field(description="Initial prompt per language code.")


class SpeechResult(_Model):
    id: str
    vad: list[Span]
    language: LanguageGuess | None = Field(description="None when the audio holds no speech.")
    words: list[TranscribedWord] = Field(description="Only words that overlap a VAD region.")


class WorkerRequest(_Model):
    backend: Backend
    model: str = Field(description="Local model directory.")
    vad_model: Path
    jobs: list[SpeechJob]


class WorkerResponse(_Model):
    pid: int
    peak_rss_mb: float
    results: list[SpeechResult]


@dataclass(frozen=True)
class TranscriptionRun:
    backend: Backend
    model: str
    results: list[SpeechResult]
    worker_pid: int
    worker_peak_rss_mb: float


def default_backend() -> Backend:
    apple = sys.platform == "darwin" and platform.machine() == "arm64"
    return "mlx-whisper" if apple else "faster-whisper"


def resolve_backend(configured: str) -> Backend:
    if configured == "auto":
        return default_backend()
    if configured not in BACKENDS:
        raise DependencyError(f"unknown speech-to-text backend {configured!r}")
    return configured  # pyright: ignore[reportReturnType]


def model_ref(backend: Backend, configured: str = "auto") -> ModelRef:
    """The model for `asr.model`: auto, a Hugging Face repo ID (main branch) or a local path."""
    default = DEFAULT_MODELS[backend]
    if configured == "auto":
        return default
    return ModelRef(configured, "main", default.python_module, default.extra)


def hf_cache() -> Path:
    return models_dir() / "huggingface"


def model_path(ref: ModelRef) -> Path | None:
    """Where the model's files are, or None when `setup` has not downloaded them."""
    if Path(ref.repo).is_dir():
        return Path(ref.repo)
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        return None
    try:
        return Path(
            snapshot_download(
                ref.repo, revision=ref.revision, cache_dir=hf_cache(), local_files_only=True
            )
        )
    except Exception:
        return None


def install_model(ref: ModelRef) -> Path:
    """Download the speech-to-text model into the reelcut cache; a no-op when it is there."""
    found = model_path(ref)
    if found is not None:
        return found
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise _missing_backend(ref) from exc
    return Path(snapshot_download(ref.repo, revision=ref.revision, cache_dir=hf_cache()))


def ensure_backend_installed(ref: ModelRef) -> None:
    import importlib.util

    if importlib.util.find_spec(ref.python_module) is None:
        raise _missing_backend(ref)


def _missing_backend(ref: ModelRef) -> DependencyError:
    return DependencyError(
        f"{ref.python_module} is not installed",
        hint=f"reinstall with the `{ref.extra}` extra: uv tool install '{APP_NAME}[{ref.extra}]'",
    )


def transcribe_clips(
    jobs: Sequence[SpeechJob],
    *,
    backend: Backend,
    model: str = "auto",
    on_wait: Callable[[str], None] | None = None,
) -> TranscriptionRun:
    """VAD, language and words for every job, from one model subprocess.

    Raises DependencyError (exit 2) when the backend, its model or the VAD model is missing.
    """
    from reelcut.asr.vad import vad_model_path

    ref = model_ref(backend, model)
    command = _worker_command()
    if not os.environ.get(WORKER_ENV):
        ensure_backend_installed(ref)
    path = model_path(ref)
    if path is None and not os.environ.get(WORKER_ENV):
        raise DependencyError(
            f"the {backend} model {ref.repo} is not in the cache {hf_cache()}",
            hint=f"run `{APP_NAME} setup` once while online",
        )
    vad = vad_model_path()
    if not vad.is_file() and not os.environ.get(WORKER_ENV):
        raise DependencyError(
            f"the Silero VAD model is not in {vad.parent}",
            hint=f"run `{APP_NAME} setup` once while online",
        )
    request = WorkerRequest(
        backend=backend, model=str(path or ref.repo), vad_model=vad, jobs=list(jobs)
    )
    with heavy_model_lock("asr", on_wait=on_wait):
        proc = subprocess.run(
            command,
            input=request.model_dump_json(),
            capture_output=True,
            text=True,
            check=False,
        )
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-STDERR_TAIL:])
        if proc.returncode == DependencyError.exit_code:
            raise DependencyError(f"speech-to-text worker: {tail}")
        raise InternalError(f"speech-to-text worker exited {proc.returncode}:\n{tail}")
    try:
        response = WorkerResponse.model_validate_json(proc.stdout)
    except ValueError as exc:
        raise InternalError(f"speech-to-text worker printed invalid output: {exc}") from exc
    return TranscriptionRun(
        backend=backend,
        model=ref.repo,
        results=response.results,
        worker_pid=response.pid,
        worker_peak_rss_mb=response.peak_rss_mb,
    )


def _worker_command() -> list[str]:
    override = os.environ.get(WORKER_ENV)
    if override:
        return [override]
    return [sys.executable, "-m", "reelcut.asr.worker"]
