"""Face detection, run in a model subprocess under the machine-wide heavy-model lock.

MediaPipe Tasks' FaceDetector (BlazeFace full range) is the detector; OpenCV's YuNet is the
fallback when MediaPipe or its model is unavailable. `reelcut setup` downloads both models.
"""

import hashlib
import os
import subprocess
import sys
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from reelcut import APP_NAME
from reelcut.analysis.models import FaceSample
from reelcut.errors import DependencyError, InternalError
from reelcut.paths import models_dir
from reelcut.state import heavy_model_lock

# Replaces the worker command (`python -m reelcut.vision.worker`) with another executable.
WORKER_ENV = f"{APP_NAME.upper()}_FACE_WORKER"
STDERR_TAIL = 20
SAMPLE_FPS = 2.0
# Frames are scaled so their long side is this many pixels before detection.
LONG_SIDE = 640

Detector = Literal["mediapipe", "yunet"]


@dataclass(frozen=True)
class ModelFile:
    name: str
    url: str
    sha256: str


# Both pinned on 2026-10-24; the hashes are of those downloads.
# Full range, not short range: short range misses faces under about 15% of the frame width.
MEDIAPIPE_MODEL = ModelFile(
    "blaze_face_full_range-float16-1.tflite",
    "https://storage.googleapis.com/mediapipe-models/face_detector/"
    "blaze_face_full_range/float16/1/blaze_face_full_range.tflite",
    "3698b18f063835bc609069ef052228fbe86d9c9a6dc8dcb7c7c2d69aed2b181b",
)
YUNET_MODEL = ModelFile(
    "face_detection_yunet_2023mar.onnx",
    "https://github.com/opencv/opencv_zoo/raw/48b10fa505aeb51fbd127fc60a5c660040e823b7/"
    "models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
    "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
)


def mediapipe_model_path() -> Path:
    return models_dir() / MEDIAPIPE_MODEL.name


def yunet_model_path() -> Path:
    return models_dir() / YUNET_MODEL.name


def install_face_model(model: ModelFile) -> Path:
    """Download one pinned face model into the cache, unless it is already there."""
    dest = models_dir() / model.name
    if dest.is_file():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f".{dest.name}.download")
    with urllib.request.urlopen(model.url, timeout=120) as response:
        tmp.write_bytes(response.read())
    digest = hashlib.sha256(tmp.read_bytes()).hexdigest()
    if digest != model.sha256:
        tmp.unlink()
        raise DependencyError(
            f"{model.name} download has SHA-256 {digest}, expected {model.sha256}"
        )
    tmp.replace(dest)
    return dest


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FaceJob(_Model):
    id: str
    path: Path = Field(description="Mezzanine video or normalised image.")
    kind: Literal["video", "image"]
    duration_s: float
    width: int
    height: int


class FaceRequest(_Model):
    mediapipe_model: Path | None
    yunet_model: Path | None
    sample_fps: float
    long_side: int
    jobs: list[FaceJob]


class FaceResult(_Model):
    id: str
    samples: list[FaceSample] = Field(description="Largest face per sampled frame that has one.")


class FaceRun(_Model):
    """The worker's response."""

    pid: int
    peak_rss_mb: float
    detector: Detector
    fallback_reason: str | None = Field(description="Why MediaPipe was not used, if it was not.")
    results: list[FaceResult]


def detect_faces(
    jobs: Sequence[FaceJob], *, on_wait: Callable[[str], None] | None = None
) -> FaceRun:
    """The largest face in each sampled frame of every job, from one model subprocess.

    Raises DependencyError (exit 2) when neither face model is in the cache.
    """
    mediapipe, yunet = mediapipe_model_path(), yunet_model_path()
    override = os.environ.get(WORKER_ENV)
    request = FaceRequest(
        mediapipe_model=mediapipe if mediapipe.is_file() else None,
        yunet_model=yunet if yunet.is_file() else None,
        sample_fps=SAMPLE_FPS,
        long_side=LONG_SIDE,
        jobs=list(jobs),
    )
    if request.mediapipe_model is None and request.yunet_model is None and not override:
        raise DependencyError(
            f"no face detection model in {models_dir()}",
            hint=f"run `{APP_NAME} setup` once while online",
        )
    command = [override] if override else [sys.executable, "-m", "reelcut.vision.worker"]
    with heavy_model_lock("faces", on_wait=on_wait):
        proc = subprocess.run(
            command, input=request.model_dump_json(), capture_output=True, text=True, check=False
        )
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-STDERR_TAIL:])
        if proc.returncode == DependencyError.exit_code:
            raise DependencyError(f"face detection worker: {tail}")
        raise InternalError(f"face detection worker exited {proc.returncode}:\n{tail}")
    try:
        return FaceRun.model_validate_json(proc.stdout)
    except ValueError as exc:
        raise InternalError(f"face detection worker printed invalid output: {exc}") from exc
