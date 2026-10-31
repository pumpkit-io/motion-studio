"""The share copy: a final at full resolution that fits under the 30 MiB chat-upload cap."""

import json
import shutil
from pathlib import Path

from motion_studio.errors import InternalError, UserError
from motion_studio.media.ffmpeg import run_ffmpeg, run_ffprobe

CAP_BYTES = 30 * 1024 * 1024
# Two-pass x264 lands within a few percent of its bitrate; the rest covers the MP4 boxes.
HEADROOM = 0.94
MIN_VIDEO_BPS = 250_000
ATTEMPTS = 3


def share_path(final: Path) -> Path:
    return final.with_name(f"{final.stem}_share.mp4")


def share_copy(final: Path, out: Path, *, cap_bytes: int, scratch: Path) -> Path:
    """Write `out` from `final` under `cap_bytes` at the final's resolution, with `+faststart`.

    A final already under the cap is copied as it is. Otherwise the video is re-encoded with
    two-pass x264 at a bitrate that fits, and the mastered audio is copied so loudness and true
    peak stay exactly as mixed.
    """
    tmp = out.with_name(f".{out.name}")
    if final.stat().st_size <= cap_bytes:
        shutil.copyfile(final, tmp)
        tmp.replace(out)
        return out
    duration_s, audio_bps = _duration_and_audio_rate(final)
    video_bps = int(cap_bytes * HEADROOM * 8 / duration_s) - audio_bps
    if video_bps < MIN_VIDEO_BPS:
        raise UserError(
            f"{final.name} is too long for a share copy under {cap_bytes / 2**20:.0f} MiB "
            f"({duration_s:.0f} s leaves {max(video_bps, 0) // 1000} kb/s for the video)",
            hint="send the final itself, or shorten the edit",
        )
    for _ in range(ATTEMPTS):
        _encode(final, tmp, video_bps, scratch / f"{out.stem}_x264")
        size = tmp.stat().st_size
        if size <= cap_bytes:
            tmp.replace(out)
            return out
        video_bps = int(video_bps * cap_bytes * HEADROOM / size)
    tmp.unlink(missing_ok=True)
    raise InternalError(f"the share copy of {final.name} stayed over the cap in {ATTEMPTS} tries")


def _encode(final: Path, dest: Path, video_bps: int, passlog: Path) -> None:
    video: list[str | Path] = ["-map", "0:v:0", "-c:v", "libx264", "-preset", "medium"]
    video += ["-profile:v", "high", "-pix_fmt", "yuv420p", "-b:v", str(video_bps)]
    video += ["-passlogfile", passlog]
    run_ffmpeg(["-y", "-i", final, *video, "-pass", "1", "-an", "-f", "null", "-"])
    run_ffmpeg(
        ["-y", "-i", final, *video, "-pass", "2", "-map", "0:a?", "-c:a", "copy",
         "-movflags", "+faststart", dest]
    )  # fmt: skip


def _duration_and_audio_rate(final: Path) -> tuple[float, int]:
    out = run_ffprobe(["-v", "error", "-show_streams", "-show_format", "-of", "json", final])
    data = json.loads(out)
    audio = [s for s in data.get("streams", []) if s.get("codec_type") == "audio"]
    audio_bps = int(audio[0].get("bit_rate", 0)) if audio else 0
    return float(data["format"]["duration"]), audio_bps
