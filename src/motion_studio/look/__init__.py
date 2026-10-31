"""Contact sheets: filmstrip, waveform, word labels and face boxes, and the look budget.

`look_range` draws a time range of one clip and counts against `edit.look_budget`;
`look_asset` and `write_asset_sheet` draw a B-roll clip or image into `contact/<id>.png`,
the path `assets.md` links to, and `write_screen_sheet` draws a screen recording there at
1 fps at ingest. Neither counts: seeing each clip once is part of every edit.
"""

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import soundfile

from motion_studio import APP_NAME
from motion_studio.analysis import ClipAnalysis, Faces, FaceSample
from motion_studio.config import load_config
from motion_studio.errors import UserError
from motion_studio.ingest import ClipMedia, load_manifest
from motion_studio.look.sheet import FRAME_HEIGHT, Frame, asset_sheet, fit_frame, range_sheet
from motion_studio.media.ffmpeg import read_frames
from motion_studio.paths import ProjectPaths, project_paths
from motion_studio.state import load_state, save_state

DEFAULT_FRAMES = 8
MAX_FRAMES = 24
ASSET_FRAMES = 6
# The look skill tells agents to split anything longer into the moments that matter.
LONG_RANGE_S = 20.0
IMAGE_HEIGHT = 720
SCREEN_FPS = 1.0
SCREEN_FRAME_HEIGHT = 180
# About 30 rows of frames; a longer recording is sampled more sparsely, with a warning.
MAX_SCREEN_FRAMES = 180


@dataclass
class LookReport:
    sheet: Path
    description: str
    frames: int
    look_count: int | None = None
    look_budget: int | None = None
    warnings: list[str] = field(default_factory=lambda: list[str]())

    def to_json(self) -> dict[str, Any]:
        return {
            "sheet": str(self.sheet),
            "description": self.description,
            "frames": self.frames,
            "look_count": self.look_count,
            "look_budget": self.look_budget,
            "warnings": self.warnings,
        }


def look_range(
    workspace: Path,
    slug: str,
    clip_id: str,
    t0: float,
    t1: float,
    *,
    frames: int = DEFAULT_FRAMES,
    out: Path | None = None,
) -> LookReport:
    """Draw [t0, t1] (source seconds) of one clip and count it against the look budget."""
    from motion_studio.analyze import load_analysis

    project = project_paths(workspace, slug).require()
    clip = _clip(project, clip_id)
    if clip.kind == "image":
        raise UserError(
            f"{clip_id} is an image", hint=f"run `{APP_NAME} look-asset {slug} {clip_id}`"
        )
    if not 1 <= frames <= MAX_FRAMES:
        raise UserError(
            f"--frames must be 1 to {MAX_FRAMES}, not {frames}",
            hint=f"the default is {DEFAULT_FRAMES}; use 6 to compare two takes",
        )
    duration = clip.duration_s or 0.0
    if not 0 <= t0 < t1:
        raise UserError(f"the range {t0:g}-{t1:g} s is empty", hint="pass <t0> < <t1> in seconds")
    if t0 >= duration:
        raise UserError(
            f"{clip_id} is {duration:.2f} s long; {t0:g} s is past its end",
            hint=f"pass times between 0 and {duration:.2f}",
        )
    warnings: list[str] = []
    if t1 > duration:
        warnings.append(f"{t1:g} s is past the end of {clip_id}; the sheet stops at {duration:.2f}")
        t1 = duration
    if t1 - t0 > LONG_RANGE_S:
        warnings.append(
            f"a {t1 - t0:.0f} s range is hard to read; look at the moments that matter instead"
        )
    analysis = load_analysis(project, clip_id)
    step = (t1 - t0) / frames
    times = [t0 + (i + 0.5) * step for i in range(frames)]
    words = [w for w in analysis.words if w.end > t0 and w.start < t1]
    sheet_frames = _frames(project, clip, times, analysis.faces)
    samples = _samples(project, clip, t0, t1)
    title = f"{clip_id} · {Path(clip.source).name} · {t0:.2f}-{t1:.2f} s · {frames} frames"
    if words:
        title += f" · {words[0].id} to {words[-1].id}"
    image = range_sheet(
        title,
        sheet_frames,
        t0=t0,
        t1=t1,
        samples=samples,
        vad=analysis.vad,
        pauses=analysis.pauses,
        words=words,
    )
    path = out or project.contact / f"{clip_id}_{t0:.2f}-{t1:.2f}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, optimize=True)

    hard = sum(w.filler == "hard" for w in words)
    soft = sum(w.filler == "soft" for w in words)
    faced = sum(f.face is not None for f in sheet_frames)
    description = (
        f"{clip_id} {t0:.2f}-{t1:.2f} s: {frames} frames, {len(words)} words "
        f"({hard} hard, {soft} soft fillers), face in {faced}/{frames} frames"
    )
    count, budget = _count_look(workspace, project)
    if count > budget:
        warnings.append(
            f"look budget exceeded ({count} of {budget} sheets); look only when the decision "
            "needs eyes, and say why in notes.md"
        )
    return LookReport(path, description, frames, count, budget, warnings)


def look_asset(workspace: Path, slug: str, asset_id: str) -> LookReport:
    """Redraw the contact sheet of one B-roll clip or image into `contact/<id>.png`."""
    from motion_studio.analyze import load_analysis

    project = project_paths(workspace, slug).require()
    clip = _clip(project, asset_id)
    analysis = load_analysis(project, asset_id)
    if analysis.clip.role == "aroll":
        raise UserError(
            f"{asset_id} is A-roll, not an asset",
            hint=f"run `{APP_NAME} look {slug} {asset_id} <t0> <t1>`",
        )
    path = write_asset_sheet(project, clip, analysis)
    return LookReport(path, asset_description(clip, analysis), _asset_frame_count(clip))


def write_asset_sheet(project: ProjectPaths, clip: ClipMedia, analysis: ClipAnalysis) -> Path:
    if clip.kind == "image":
        frames = _frames(project, clip, [0.0], analysis.faces, height=IMAGE_HEIGHT)
        image = asset_sheet(_asset_title(clip), frames, stamps=False)
    else:
        duration = clip.duration_s or 0.0
        count = _asset_frame_count(clip)
        times = [(i + 0.5) * duration / count for i in range(count)]
        image = asset_sheet(_asset_title(clip), _frames(project, clip, times, analysis.faces))
    path = project.asset_sheet(clip.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, optimize=True)
    return path


def write_screen_sheet(project: ProjectPaths, clip: ClipMedia) -> tuple[Path, list[str]]:
    """One frame per second of a screen recording, each stamped with its source time."""
    duration = clip.duration_s or 0.0
    count = max(1, math.ceil(duration * SCREEN_FPS - 1e-6))
    warnings: list[str] = []
    if count > MAX_SCREEN_FRAMES:
        warnings.append(
            f"{clip.id}: {duration:.0f} s is too long for a 1 fps sheet; "
            f"it shows {MAX_SCREEN_FRAMES} frames, one every {duration / MAX_SCREEN_FRAMES:.1f} s"
        )
        count = MAX_SCREEN_FRAMES
    step = duration / count if duration else 0.0
    times = [(i + 0.5) * step for i in range(count)]
    frames = _frames(project, clip, times, Faces(), height=SCREEN_FRAME_HEIGHT)
    title = f"{_asset_title(clip)} · {len(frames)} frames, one per {step:.1f} s"
    path = project.asset_sheet(clip.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    asset_sheet(title, frames).save(path, optimize=True)
    return path, warnings


def asset_description(clip: ClipMedia, analysis: ClipAnalysis) -> str:
    kind = "image" if clip.kind == "image" else f"{clip.duration_s or 0:.1f} s B-roll"
    faces = len(analysis.faces.samples)
    seen = f"face in {faces} sampled frames" if faces else "no face"
    return f"{clip.id} {kind}, {clip.width}x{clip.height}, {seen}"


def _asset_title(clip: ClipMedia) -> str:
    length = "still image" if clip.kind == "image" else f"{clip.duration_s or 0:.1f} s"
    return f"{clip.id} · {Path(clip.source).name} · {length} · {clip.width}x{clip.height}"


def _asset_frame_count(clip: ClipMedia) -> int:
    return 1 if clip.kind == "image" else ASSET_FRAMES


def _clip(project: ProjectPaths, clip_id: str) -> ClipMedia:
    clips = {c.id: c for c in load_manifest(project).clips}
    if clip_id not in clips:
        raise UserError(
            f"no clip {clip_id!r} in {project.slug!r}", hint=f"clips: {', '.join(clips)}"
        )
    return clips[clip_id]


def _frames(
    project: ProjectPaths,
    clip: ClipMedia,
    times: list[float],
    faces: Faces,
    *,
    height: int = FRAME_HEIGHT,
) -> list[Frame]:
    source = project.root / clip.mezzanine
    if not source.exists():
        raise UserError(f"{source} is missing", hint=f"run `{APP_NAME} ingest {project.slug}`")
    width, height = fit_frame(clip.width, clip.height, height)
    last = max(0.0, (clip.duration_s or 0.0) - 1 / (clip.fps or 30.0))
    frames: list[Frame] = []
    for t in times:
        # Seek before -i so each frame decodes from the nearest keyframe, not from the start.
        seek = ["-ss", f"{min(t, last):.3f}"] if clip.kind == "video" else []
        args = [*seek, "-i", source, "-frames:v", "1"]
        decoded = list(
            read_frames(args, width=width, height=height, filters=f"scale={width}:{height}")
        )
        if decoded:
            frames.append(Frame(decoded[0], t, _face_at(faces, t)))
    if not frames:
        raise UserError(
            f"could not decode a frame of {clip.id}", hint=f"re-run `{APP_NAME} ingest`"
        )
    return frames


def _face_at(faces: Faces, t: float) -> FaceSample | None:
    """The face sample nearest `t`, if one lies within half a sampling interval."""
    window = 0.5 / faces.sample_fps + 1e-6
    near = [s for s in faces.samples if abs(s.t - t) <= window]
    return min(near, key=lambda s: abs(s.t - t)) if near else None


def _samples(
    project: ProjectPaths, clip: ClipMedia, t0: float, t1: float
) -> npt.NDArray[np.float32] | None:
    if clip.audio_16k is None or not (project.root / clip.audio_16k).exists():
        return None
    with soundfile.SoundFile(str(project.root / clip.audio_16k)) as wav:
        rate = wav.samplerate
        wav.seek(min(int(t0 * rate), wav.frames))
        data = wav.read(max(0, int((t1 - t0) * rate)), dtype="float32", always_2d=True)
    return np.ascontiguousarray(data.mean(axis=1), dtype=np.float32)


def _count_look(workspace: Path, project: ProjectPaths) -> tuple[int, int]:
    budget = load_config(workspace, project.slug).edit.look_budget
    state = load_state(project)
    state.look_count += 1
    save_state(project, state)
    return state.look_count, budget
