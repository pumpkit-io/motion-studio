"""The face worker: `python -m reelcut.vision.worker` reads a FaceRequest on stdin.

It loads one detector, samples every job's frames and prints a FaceRun on stdout. The parent
holds the heavy-model lock for the worker's whole life. Exit 2 means no usable detector.
"""

import os
import resource
import sys
from pathlib import Path
from typing import Protocol

import numpy as np
import numpy.typing as npt

from reelcut.analysis.models import FaceSample
from reelcut.errors import DependencyError
from reelcut.media.ffmpeg import read_frames
from reelcut.vision import Detector, FaceJob, FaceRequest, FaceResult, FaceRun

Frame = npt.NDArray[np.uint8]
# (x, y, w, h, score) in pixels of the frame given to the detector.
Box = tuple[float, float, float, float, float]


class FaceDetector(Protocol):
    name: Detector

    def detect(self, rgb: Frame) -> list[Box]: ...


class MediaPipeDetector:
    name: Detector = "mediapipe"

    def __init__(self, model: Path) -> None:
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision

        self._mp = mp
        options = vision.FaceDetectorOptions(base_options=BaseOptions(model_asset_path=str(model)))
        self._detector = vision.FaceDetector.create_from_options(options)

    def detect(self, rgb: Frame) -> list[Box]:
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        boxes: list[Box] = []
        for found in self._detector.detect(image).detections:
            box = found.bounding_box
            score = found.categories[0].score if found.categories else 0.0
            boxes.append((box.origin_x, box.origin_y, box.width, box.height, score or 0.0))
        return boxes


class YuNetDetector:
    name: Detector = "yunet"

    def __init__(self, model: Path) -> None:
        import cv2

        self._cv2 = cv2
        self._detector = cv2.FaceDetectorYN.create(str(model), "", (320, 320), 0.6)

    def detect(self, rgb: Frame) -> list[Box]:
        height, width = rgb.shape[:2]
        self._detector.setInputSize((width, height))
        bgr = np.ascontiguousarray(rgb[..., ::-1])
        _, faces = self._detector.detect(bgr)
        if faces is None:
            return []
        return [(float(f[0]), float(f[1]), float(f[2]), float(f[3]), float(f[-1])) for f in faces]


def load_detector(request: FaceRequest) -> tuple[FaceDetector, str | None]:
    """MediaPipe if it loads, else YuNet with the reason MediaPipe was not used."""
    if request.mediapipe_model is None:
        reason = "the MediaPipe face model is not in the cache"
    else:
        try:
            return MediaPipeDetector(request.mediapipe_model), None
        except Exception as exc:
            reason = f"MediaPipe failed to load ({type(exc).__name__}: {exc})"
    if request.yunet_model is None:
        raise DependencyError(f"{reason}, and the YuNet model is not in the cache either")
    return YuNetDetector(request.yunet_model), reason


def scaled_size(width: int, height: int, long_side: int) -> tuple[int, int]:
    scale = min(1.0, long_side / max(width, height))
    return max(2, round(width * scale / 2) * 2), max(2, round(height * scale / 2) * 2)


def sample_faces(job: FaceJob, detector: FaceDetector, request: FaceRequest) -> FaceResult:
    width, height = scaled_size(job.width, job.height, request.long_side)
    scale = f"scale={width}:{height}"
    if job.kind == "image":
        frames = read_frames(
            ["-i", job.path, "-frames:v", "1"], width=width, height=height, filters=scale
        )
    else:
        frames = read_frames(
            ["-i", job.path],
            width=width,
            height=height,
            filters=f"fps={request.sample_fps},{scale}",
        )
    samples: list[FaceSample] = []
    for index, frame in enumerate(frames):
        boxes = detector.detect(np.ascontiguousarray(frame))
        if not boxes:
            continue
        x, y, w, h, score = max(boxes, key=lambda b: b[2] * b[3])
        samples.append(
            FaceSample(
                t=round(index / request.sample_fps, 3),
                cx=round((x + w / 2) / width, 4),
                cy=round((y + h / 2) / height, 4),
                w=round(w / width, 4),
                h=round(h / height, 4),
                score=round(min(max(score, 0.0), 1.0), 4),
            )
        )
    return FaceResult(id=job.id, samples=samples)


def _peak_rss_mb() -> float:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # ru_maxrss is bytes on macOS and kilobytes on Linux.
    return round(peak / 1e6 if sys.platform == "darwin" else peak / 1e3, 1)


def main() -> int:
    request = FaceRequest.model_validate_json(sys.stdin.read())
    # Model libraries may print progress; only the response may reach the parent's stdout.
    out, sys.stdout = sys.stdout, sys.stderr
    try:
        detector, reason = load_detector(request)
    except DependencyError as exc:
        print(str(exc), file=sys.stderr)
        return DependencyError.exit_code
    results = [sample_faces(job, detector, request) for job in request.jobs]
    out.write(
        FaceRun(
            pid=os.getpid(),
            peak_rss_mb=_peak_rss_mb(),
            detector=detector.name,
            fallback_reason=reason,
            results=results,
        ).model_dump_json()
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
