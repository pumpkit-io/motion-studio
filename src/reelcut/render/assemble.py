"""Assemble: cut the A-roll runs out of the mezzanines and join them into `build/assembled.mp4`.

One ffmpeg filter graph does every cut, so the voice is decoded and encoded once.
"""

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from reelcut.edl import Timeline
from reelcut.errors import InternalError, UserError
from reelcut.ingest import ClipMedia
from reelcut.media.ffmpeg import ffmpeg_caps, filter_graph_args, run_ffmpeg, run_ffprobe

SAMPLE_RATE = 48_000
FADE_S = 0.03
ASSEMBLED = "assembled.mp4"


@dataclass(frozen=True)
class Input:
    """One A-roll clip as ffmpeg inputs: its mezzanine and its enhanced voice."""

    clip: str
    video: Path
    audio: Path


@dataclass(frozen=True)
class Region:
    """Where one clip's picture sits in the assembled canvas, in pixels."""

    x: int
    y: int
    width: int
    height: int

    def to_json(self) -> dict[str, int]:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}


@dataclass(frozen=True)
class Canvas:
    """The assembled frame: wide and tall enough to hold every A-roll clip unscaled."""

    width: int
    height: int
    regions: dict[str, Region]


def assembly_canvas(timeline: Timeline, clips: dict[str, ClipMedia]) -> Canvas:
    """Each clip centred at its own size, so the renderer can frame every run from its region.

    Scaling every clip to the first one's size would letterbox a landscape take beside portrait
    ones and frame its face wrongly.
    """
    sizes = {
        c: (_even_down(clips[c].width), _even_down(clips[c].height))
        for c in dict.fromkeys(run.clip for run in timeline.runs)
        if c in clips
    }
    width = max((w for w, _ in sizes.values()), default=2)
    height = max((h for _, h in sizes.values()), default=2)
    regions = {
        c: Region(_even_down((width - w) // 2), _even_down((height - h) // 2), w, h)
        for c, (w, h) in sizes.items()
    }
    return Canvas(width, height, regions)


def _even_down(value: int) -> int:
    return value - value % 2


def assembly_graph(timeline: Timeline, inputs: Sequence[Input], canvas: Canvas) -> str:
    """Per run a frame-exact trim, a sample-exact atrim and 30 ms fades, then one concat.

    Input k's video is ffmpeg input 2k and its audio 2k + 1. Every run is padded, unscaled, to
    its clip's region of the canvas.
    """
    index = {inp.clip: k for k, inp in enumerate(inputs)}
    fps = timeline.fps
    chains: list[str] = []
    pads: list[str] = []
    for n, run in enumerate(timeline.runs):
        k = index[run.clip]
        first, last = round(run.src_in_s * fps), round(run.src_out_s * fps)
        s_in = round(first * SAMPLE_RATE / fps)
        s_out = round(last * SAMPLE_RATE / fps)
        duration = (last - first) / fps
        fade = min(FADE_S, duration / 2)
        r = canvas.regions[run.clip]
        chains.append(
            f"[{2 * k}:v]trim=start_frame={first}:end_frame={last},setpts=PTS-STARTPTS,"
            f"crop={r.width}:{r.height}:0:0,"
            f"pad={canvas.width}:{canvas.height}:{r.x}:{r.y},setsar=1,format=yuv420p[v{n}]"
        )
        chains.append(
            f"[{2 * k + 1}:a]aresample={SAMPLE_RATE},"
            f"atrim=start_sample={s_in}:end_sample={s_out},asetpts=PTS-STARTPTS,"
            f"afade=t=in:d={fade:.4f},afade=t=out:st={duration - fade:.4f}:d={fade:.4f}[a{n}]"
        )
        pads.append(f"[v{n}][a{n}]")
    chains.append(f"{''.join(pads)}concat=n={len(timeline.runs)}:v=1:a=1[v][a]")
    return ";\n".join(chains) + "\n"


def assemble(
    timeline: Timeline,
    clips: dict[str, ClipMedia],
    project_root: Path,
    build: Path,
    progress: Callable[[float], None] | None = None,
) -> Path:
    """Write `build/assembled.mp4` and check it lasts the timeline's duration within one frame."""
    if not timeline.runs:
        raise UserError("the timeline has no runs to render", hint="add segments to edl.json")
    inputs: list[Input] = []
    for clip_id in dict.fromkeys(run.clip for run in timeline.runs):
        media = clips.get(clip_id)
        if media is None or media.audio is None:
            raise UserError(
                f"clip {clip_id} has no ingested video with audio",
                hint="run `ingest` again, or remove its segments from edl.json",
            )
        inputs.append(Input(clip_id, project_root / media.mezzanine, project_root / media.audio))
    canvas = assembly_canvas(timeline, clips)

    build.mkdir(parents=True, exist_ok=True)
    out = build / ASSEMBLED
    graph = assembly_graph(timeline, inputs, canvas)
    args: list[str | Path] = []
    for inp in inputs:
        args += ["-i", inp.video, "-i", inp.audio]
    args += filter_graph_args(ffmpeg_caps(), graph, build / "assemble.filtergraph")
    args += ["-map", "[v]", "-map", "[a]", "-r", str(timeline.fps)]
    args += ["-c:v", "libx264", "-crf", "14", "-preset", "medium", "-pix_fmt", "yuv420p"]
    args += ["-c:a", "aac", "-b:a", "320k", "-ar", str(SAMPLE_RATE)]
    args += ["-movflags", "+faststart", "-y", out]
    run_ffmpeg(args, progress=progress)

    frames = count_frames(out)
    if abs(frames - timeline.duration_frames) > 1:
        raise InternalError(
            f"assembled.mp4 has {frames} frames; the timeline has {timeline.duration_frames}"
        )
    return out


def count_frames(path: Path) -> int:
    out = run_ffprobe(
        [
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-count_packets",
            "-show_streams",
            "-of",
            "json",
            path,
        ]
    )
    return int(json.loads(out)["streams"][0]["nb_read_packets"])


def video_size(path: Path) -> tuple[int, int]:
    out = run_ffprobe(
        ["-v", "error", "-select_streams", "v:0", "-show_streams", "-of", "json", path]
    )
    stream = json.loads(out)["streams"][0]
    return int(stream["width"]), int(stream["height"])
