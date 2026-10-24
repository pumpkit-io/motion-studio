"""Shot boundaries (PySceneDetect) and frame-to-frame motion (OpenCV) of a mezzanine.

Neither loads a model, so both run in the calling process without the heavy-model lock.
"""

from itertools import pairwise
from pathlib import Path

import cv2
import numpy as np

from reelcut.analysis.models import Span
from reelcut.media.ffmpeg import read_frames

MOTION_FPS = 2.0
MOTION_WIDTH = 320


def frame_differences(
    video: Path, width: int, height: int, *, fps: float = MOTION_FPS
) -> list[float]:
    """Mean absolute grey-level difference (0-255) between consecutive frames sampled at `fps`."""
    out_w = MOTION_WIDTH
    out_h = max(2, round(height * MOTION_WIDTH / width / 2) * 2)
    diffs: list[float] = []
    previous: np.ndarray | None = None
    for frame in read_frames(
        ["-i", video],
        width=out_w,
        height=out_h,
        filters=f"fps={fps},scale={out_w}:{out_h}",
        gray=True,
    ):
        if previous is not None:
            diffs.append(float(cv2.absdiff(frame, previous).mean()))
        previous = frame
    return diffs


def find_shots(video: Path, duration_s: float) -> list[Span]:
    """Shots from ContentDetector on an auto-downscaled stream; one shot when there is no cut."""
    from scenedetect import ContentDetector, SceneManager, open_video

    manager = SceneManager()
    manager.auto_downscale = True
    manager.add_detector(ContentDetector())
    manager.detect_scenes(open_video(str(video)))
    cuts = sorted(
        round(start.seconds, 3)
        for start, _ in manager.get_scene_list(start_in_scene=True)
        if 0 < start.seconds < duration_s
    )
    bounds = [0.0, *cuts, round(duration_s, 3)]
    return [Span(start=a, end=b) for a, b in pairwise(bounds) if b > a]
