"""ffprobe a raw file into the facts ingest needs: kind, display size, rate, duration, HDR."""

import json
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Literal

from motion_studio.media.ffmpeg import FFmpegError, run_ffprobe

IMAGE_EXTENSIONS = frozenset(
    {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".tif", ".tiff", ".bmp", ".gif"}
)
IMAGE_CODECS = frozenset({"mjpeg", "png", "webp", "tiff", "bmp", "gif", "hevc_image"})

# ffprobe names for the HLG and PQ transfer functions.
HDR_TRANSFERS = {"arib-std-b67": "hlg", "smpte2084": "pq"}

Kind = Literal["video", "image", "unsupported"]


@dataclass(frozen=True)
class Probe:
    kind: Kind
    width: int = 0
    height: int = 0
    # Display-matrix rotation in degrees, as ffprobe reports it; width and height are after it.
    rotation: int = 0
    fps: Fraction = Fraction(0)
    duration_s: float = 0.0
    has_audio: bool = False
    hdr: Literal["hlg", "pq"] | None = None
    color_transfer: str | None = None
    reason: str | None = None


def probe(path: Path) -> Probe:
    if path.suffix.lower() in IMAGE_EXTENSIONS:
        return Probe(kind="image")
    try:
        out = run_ffprobe(["-v", "error", "-show_streams", "-show_format", "-of", "json", path])
    except FFmpegError as exc:
        return Probe(kind="unsupported", reason=exc.stderr_tail[-1] if exc.stderr_tail else "")
    data: dict[str, Any] = json.loads(out)
    streams: list[dict[str, Any]] = data.get("streams", [])
    videos = [s for s in streams if s.get("codec_type") == "video"]
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    if not videos:
        return Probe(kind="unsupported", reason="no video stream")
    video = videos[0]
    if video.get("codec_name") in IMAGE_CODECS and len(videos) == 1 and not has_audio:
        return Probe(kind="image")
    rotation = _rotation(video)
    width, height = int(video["width"]), int(video["height"])
    if rotation % 180:
        width, height = height, width
    transfer = video.get("color_transfer")
    return Probe(
        kind="video",
        width=width,
        height=height,
        rotation=rotation,
        fps=_fps(video),
        duration_s=_duration(video, data.get("format", {})),
        has_audio=has_audio,
        hdr=HDR_TRANSFERS.get(transfer or ""),  # pyright: ignore[reportArgumentType]
        color_transfer=transfer,
    )


def _rotation(video: dict[str, Any]) -> int:
    for side in video.get("side_data_list", []):
        if "rotation" in side:
            return int(float(side["rotation"])) % 360
    tag = video.get("tags", {}).get("rotate")
    return int(tag) % 360 if tag else 0


def _fps(video: dict[str, Any]) -> Fraction:
    # Phones write VFR; avg_frame_rate is the real rate, r_frame_rate can read 10x too high.
    for key in ("avg_frame_rate", "r_frame_rate"):
        value = video.get(key, "0/0")
        num, _, den = value.partition("/")
        if den and int(den) and int(num):
            return Fraction(int(num), int(den))
    return Fraction(0)


def _duration(video: dict[str, Any], fmt: dict[str, Any]) -> float:
    for value in (video.get("duration"), fmt.get("duration")):
        if value not in (None, "N/A"):
            return float(value)
    return 0.0
