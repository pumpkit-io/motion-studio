"""`look --at`: stills of the latest render at a scene, a marker or an output time.

A scene gives its middle frame, a marker the frame that shows that moment of its recording.
The frames are the timeline's, so the render must be as fresh as `build/timeline.json`.
"""

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image

from motion_studio import APP_NAME
from motion_studio.edl import Timeline
from motion_studio.edl.models import TimelineFootage, TimelineScene
from motion_studio.errors import InternalError, UserError
from motion_studio.look import budget_warnings, count_look
from motion_studio.look.sheet import MAX_WIDTH
from motion_studio.media.ffmpeg import read_frames
from motion_studio.paths import ProjectPaths, project_paths
from motion_studio.plan import timeline_path
from motion_studio.render import output_path
from motion_studio.render.assemble import video_size
from motion_studio.state import load_state, stage_status
from motion_studio.target import RenderTarget

_MARKER = re.compile(r"^(?P<clip>[a-z]+\d+)\.m\.(?P<name>[A-Za-z0-9_][A-Za-z0-9_-]*)$")
_SECONDS = re.compile(r"^(?P<t>-?\d+(?:\.\d+)?)s?$")
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


@dataclass
class Still:
    at: str
    frame: int
    t: float
    scene: str | None
    path: Path

    def to_json(self) -> dict[str, Any]:
        return {
            "at": self.at,
            "frame": self.frame,
            "t": round(self.t, 3),
            "scene": self.scene,
            "path": str(self.path),
        }


@dataclass
class StillsReport:
    render: Path
    stage: str
    fmt: str
    stills: list[Still]
    look_count: int
    look_budget: int
    warnings: list[str] = field(default_factory=lambda: list[str]())

    def to_json(self) -> dict[str, Any]:
        return {
            "render": str(self.render),
            "stage": self.stage,
            "format": self.fmt,
            "stills": [s.to_json() for s in self.stills],
            "look_count": self.look_count,
            "look_budget": self.look_budget,
            "warnings": self.warnings,
        }


def look_at(workspace: Path, slug: str, ats: Sequence[str]) -> StillsReport:
    """One still per moment of the latest render; the call counts once against the budget."""
    project = project_paths(workspace, slug).require()
    target = _latest_render(project)
    timeline = Timeline.model_validate_json(timeline_path(project).read_text(encoding="utf-8"))
    outputs = set(load_state(project).stages[target.stage].outputs)
    fmt = next(
        f.name
        for f in timeline.formats
        if str(output_path(project, target, f.name).relative_to(project.root)) in outputs
    )
    video = output_path(project, target, fmt)
    frames = [_frame_of(project, timeline, at) for at in ats]
    size = _still_size(video_size(video))
    stills: list[Still] = []
    for at, frame in zip(ats, frames, strict=True):
        path = project.contact / f"at_{_UNSAFE.sub('_', at)}.png"
        _write_still(video, frame, timeline.fps, size, path)
        scene = next((s.id for s in timeline.scenes if s.start <= frame < s.end), None)
        stills.append(Still(at, frame, frame / timeline.fps, scene, path))
    count, budget = count_look(workspace, project)
    return StillsReport(
        video, target.stage, fmt, stills, count, budget, budget_warnings(count, budget)
    )


def _latest_render(project: ProjectPaths) -> RenderTarget:
    state = load_state(project)
    done = [t for t in RenderTarget if stage_status(project, t.stage) == "done"]
    hint = f"run `{APP_NAME} render {project.slug}` first"
    if not done:
        stale = any(stage_status(project, t.stage) == "stale" for t in RenderTarget)
        what = "the latest render is out of date" if stale else "nothing is rendered yet"
        raise UserError(f"{what}, so there is no frame to look at", hint=hint)
    return max(done, key=lambda t: state.stages[t.stage].finished_at or 0)


def _frame_of(project: ProjectPaths, timeline: Timeline, at: str) -> int:
    scene = next((s for s in timeline.scenes if s.id == at), None)
    if scene is not None:
        return scene.start + (scene.end - scene.start) // 2
    marker = _MARKER.match(at)
    if marker is not None:
        return _marker_frame(project, timeline, at, marker["clip"], marker["name"])
    seconds = _SECONDS.match(at)
    if seconds is not None:
        return _time_frame(timeline, float(seconds["t"]))
    scenes = ", ".join(s.id for s in timeline.scenes)
    choices = f"a scene ({scenes}), a marker such as c1.m.start, or " if scenes else ""
    raise UserError(
        f"--at {at!r} is not a scene, marker or output time of the render",
        hint=f"pass {choices}output seconds from 0 to {_length(timeline)}",
    )


def _time_frame(timeline: Timeline, t: float) -> int:
    # The 1e-6 keeps 4.1 s at 30 fps on frame 123, not 122.
    frame = math.floor(t * timeline.fps + 1e-6)
    if not 0 <= frame < timeline.duration_frames:
        raise UserError(
            f"{t:g} s is outside the render",
            hint=f"pass output seconds from 0 to {_length(timeline)}",
        )
    return frame


def _marker_frame(project: ProjectPaths, timeline: Timeline, ref: str, clip: str, name: str) -> int:
    from motion_studio.analyze import load_analysis

    footage = [s for s in timeline.scenes if isinstance(s, TimelineFootage)]
    recordings = sorted({s.clip for s in footage})
    if clip not in recordings:
        raise UserError(
            f"{clip} is not a screen recording in the render",
            hint=f"screen recordings on screen: {', '.join(recordings) or 'none'}",
        )
    markers = load_analysis(project, clip).markers
    marker = next((m for m in markers if m.name == name), None)
    if marker is None:
        listed = ", ".join(f"{clip}.m.{m.name}" for m in markers) or "no markers"
        raise UserError(f"{ref} does not exist", hint=f"{clip} has {listed}")
    playing = [s for s in footage if s.clip == clip]
    scene = next((s for s in playing if s.src_in_s <= marker.t <= s.src_out_s + 1e-6), None)
    if scene is None:
        spans = ", ".join(_span(s) for s in playing)
        raise UserError(
            f"{ref} ({marker.t:.2f} s into {clip}) is not on screen in the render",
            hint=f"scenes playing {clip}: {spans}",
        )
    frame = scene.start + round((marker.t - scene.src_in_s) / scene.rate * timeline.fps)
    return min(frame, scene.end - 1)


def _span(scene: TimelineScene) -> str:
    assert isinstance(scene, TimelineFootage)
    return f"{scene.id} ({scene.src_in_s:.2f}-{scene.src_out_s:.2f} s of {scene.clip})"


def _length(timeline: Timeline) -> str:
    return f"{timeline.duration_frames / timeline.fps:.2f} s"


def _still_size(size: tuple[int, int]) -> tuple[int, int]:
    width, height = size
    scale = min(1.0, MAX_WIDTH / width)
    return max(2, round(width * scale / 2) * 2), max(2, round(height * scale / 2) * 2)


def _write_still(video: Path, frame: int, fps: int, size: tuple[int, int], out: Path) -> None:
    # ffmpeg returns the first frame at or after the seek, so aim a quarter frame early.
    seek = max(0.0, (frame - 0.25) / fps)
    width, height = size
    args = ["-ss", f"{seek:.6f}", "-i", video, "-frames:v", "1"]
    decoded = list(read_frames(args, width=width, height=height, filters=f"scale={width}:{height}"))
    if not decoded:
        raise InternalError(f"could not decode frame {frame} of {video}")
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(decoded[0]).save(out, optimize=True)
