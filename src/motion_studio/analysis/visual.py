"""Static stretches and role finalisation, from measurements the vision stage takes."""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from motion_studio.analysis.models import ClipAnalysis, Role, Span


@dataclass(frozen=True)
class VisualParams:
    static_threshold: float = 1.5
    """Mean absolute difference (0-255) between sampled frames below which nothing moves."""
    screen_static_threshold: float = 0.02
    """The same for screen recordings, which have no sensor noise: one typed glyph in a
    1600x900 frame measures about 0.03, a blinking caret under 0.01."""
    static_min_s: float = 2.0
    aroll_speech_ratio: float = 0.3
    aroll_face_ratio: float = 0.5


def find_static(
    diffs: Sequence[float],
    sample_fps: float,
    *,
    vad: Sequence[Span],
    duration_s: float,
    params: VisualParams | None = None,
) -> list[Span]:
    """Stretches with almost no motion and no voice activity, at least `static_min_s` long.

    `diffs[i]` is the difference between the frames sampled at `i / sample_fps` and the next.
    """
    p = params or VisualParams()
    still: list[tuple[float, float]] = []
    start: int | None = None
    for index, diff in enumerate([*diffs, math.inf]):
        if diff < p.static_threshold:
            start = index if start is None else start
        elif start is not None:
            # The last sampled frame stands for the rest of the clip after it.
            end = duration_s if index == len(diffs) else min(index / sample_fps, duration_s)
            still.append((start / sample_fps, end))
            start = None

    static: list[Span] = []
    for begin, end in still:
        for piece_start, piece_end in _without(begin, end, vad):
            if piece_end - piece_start >= p.static_min_s:
                static.append(Span(start=round(piece_start, 3), end=round(piece_end, 3)))
    return static


def _without(start: float, end: float, spans: Sequence[Span]) -> list[tuple[float, float]]:
    pieces: list[tuple[float, float]] = []
    cursor = start
    for span in sorted(spans, key=lambda s: s.start):
        if span.end <= cursor or span.start >= end:
            continue
        if span.start > cursor:
            pieces.append((cursor, span.start))
        cursor = max(cursor, span.end)
    if cursor < end:
        pieces.append((cursor, end))
    return pieces


def face_sample_count(duration_s: float, sample_fps: float) -> int:
    """How many frames the face pass samples: one at each multiple of 1 / sample_fps."""
    return max(1, math.ceil(duration_s * sample_fps - 1e-6))


def finalise_role(
    analysis: ClipAnalysis,
    *,
    kind: Literal["video", "image"],
    params: VisualParams | None = None,
) -> Role:
    """A video is A-roll only when it holds enough speech and a face in most sampled frames."""
    if kind == "image":
        return "image"
    p = params or VisualParams()
    duration = analysis.clip.duration_s
    if duration <= 0:
        return "broll"
    speech = sum(s.end - s.start for s in analysis.vad) / duration
    faces = len(analysis.faces.samples) / face_sample_count(duration, analysis.faces.sample_fps)
    if speech > p.aroll_speech_ratio and faces > p.aroll_face_ratio:
        return "aroll"
    return "broll"
