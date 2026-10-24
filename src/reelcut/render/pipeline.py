"""`reelcut render`: assemble once, then compose and mix each format into preview/ or final/."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from reelcut import APP_NAME
from reelcut.config import Brand as BrandConfig
from reelcut.config import load_config
from reelcut.edl import Timeline
from reelcut.errors import ReelcutError, UserError
from reelcut.ingest import MANIFEST, load_manifest
from reelcut.paths import ProjectPaths, project_paths
from reelcut.plan import load_edl, timeline_path, validate_project
from reelcut.render.assemble import assemble, count_frames, video_size
from reelcut.render.compose import compose, find_brand, prepare_public, props
from reelcut.render.mix import mix
from reelcut.render.renderer import find_renderer, remotion_version
from reelcut.state import (
    ensure_free_disk,
    mark_done,
    mark_failed,
    project_lock,
    record_warning,
    stage_is_fresh,
    stage_status,
)
from reelcut.target import RenderTarget

DEFAULT_CONCURRENCY = 4
# Bump when the assemble, compose or mix recipe changes, so earlier renders go stale.
RECIPE = 1
ASSEMBLE_RECORD = "render.assemble"


@dataclass(frozen=True)
class Output:
    format: str
    path: Path
    voice: Path
    width: int
    height: int
    frames: int
    fps: int

    def to_json(self) -> dict[str, Any]:
        return {
            "format": self.format,
            "path": str(self.path),
            "voice": str(self.voice),
            "width": self.width,
            "height": self.height,
            "duration_s": round(self.frames / self.fps, 3),
        }


@dataclass
class RenderReport:
    stage: str
    outputs: list[Output]
    assembled: Path
    cuts_s: list[float]
    noop: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "noop": self.noop,
            "outputs": [o.to_json() for o in self.outputs],
            "assembled": str(self.assembled),
            "cuts_s": self.cuts_s,
            "warnings": self.warnings,
        }


def output_path(project: ProjectPaths, target: RenderTarget, fmt: str) -> Path:
    if target is RenderTarget.FINAL:
        return project.final / f"{project.slug}_{fmt}.mp4"
    return project.preview / f"{fmt}.mp4"


def voice_path(project: ProjectPaths, fmt: str) -> Path:
    return project.build / f"voice_{fmt}.wav"


def render_project(
    workspace: Path,
    slug: str,
    *,
    target: RenderTarget,
    formats: Sequence[str] = (),
    concurrency: int = DEFAULT_CONCURRENCY,
    on_step: Callable[[str], None] | None = None,
    on_warning: Callable[[str], None] | None = None,
) -> RenderReport:
    step = on_step or (lambda _msg: None)
    warn = on_warning or (lambda _msg: None)
    project = project_paths(workspace, slug).require()
    ensure_free_disk(project.root)
    if concurrency < 1:
        raise UserError("--concurrency must be at least 1")
    if stage_status(project, "plan") != "done":
        step("validating edl.json")
        validate_project(workspace, slug)
    renderer = find_renderer()
    stage = target.stage

    with project_lock(project):
        timeline = Timeline.model_validate_json(timeline_path(project).read_text(encoding="utf-8"))
        config = load_config(workspace, slug)
        music = config.music
        gain_db = load_edl(project).music.gain_db
        if gain_db is not None:
            music = music.model_copy(update={"gain_db": gain_db})
        chosen = _formats(timeline, formats)
        music_file = _music_file(project, timeline)
        brand = find_brand(timeline, workspace, BrandConfig().logo)
        manifest = project.media / MANIFEST
        inputs = [timeline_path(project), manifest]
        inputs += [p for p in (music_file, brand.font, brand.logo) if p is not None]
        params = {
            "recipe": RECIPE,
            "formats": chosen,
            "music": music.model_dump(),
            "master": config.master.model_dump(),
            "remotion": remotion_version(renderer),
        }
        outputs = {
            fmt: (output_path(project, target, fmt), voice_path(project, fmt)) for fmt in chosen
        }
        assembled = project.build / "assembled.mp4"
        cuts = [round(run.out_in / timeline.fps, 3) for run in timeline.runs[1:]]

        if stage_is_fresh(project, stage, inputs, params=params):
            done = [_describe(fmt, *outputs[fmt], timeline.fps) for fmt in chosen]
            return RenderReport(stage, done, assembled, cuts, noop=True)

        try:
            for message in brand.warnings:
                record_warning(project, stage, message)
                warn(message)
            assemble_inputs = [timeline_path(project), manifest]
            if not stage_is_fresh(
                project, ASSEMBLE_RECORD, assemble_inputs, params={"recipe": RECIPE}
            ):
                step("assembling the A-roll cuts")
                clips = {c.id: c for c in load_manifest(project).clips}
                assemble(timeline, clips, project.root, project.build)
                mark_done(
                    project,
                    ASSEMBLE_RECORD,
                    assemble_inputs,
                    outputs=[assembled],
                    params={"recipe": RECIPE},
                )
            public = prepare_public(project.build, assembled, timeline, project.root, brand)
            source = video_size(assembled)
            done: list[Output] = []
            for fmt in chosen:
                step(f"composing {fmt} with Remotion")
                data = props(timeline, fmt, source, assembled.name, brand)
                composed = compose(
                    renderer,
                    data,
                    project.build,
                    public,
                    preview=target is RenderTarget.PREVIEW,
                    concurrency=concurrency,
                )
                step(f"mixing and mastering {fmt}")
                out, voice = outputs[fmt]
                mix(
                    composed,
                    out,
                    voice,
                    duration_s=timeline.duration_frames / timeline.fps,
                    music_file=music_file,
                    music=music,
                    master=config.master,
                    scratch=project.build,
                )
                done.append(_describe(fmt, out, voice, timeline.fps))
            mark_done(
                project,
                stage,
                inputs,
                outputs=[p for pair in outputs.values() for p in pair],
                params=params,
            )
        except ReelcutError as exc:
            mark_failed(project, stage, exc.message)
            raise
    return RenderReport(stage, done, assembled, cuts, warnings=list(brand.warnings))


def _formats(timeline: Timeline, requested: Sequence[str]) -> list[str]:
    known = [f.name for f in timeline.formats]
    if not requested:
        return known
    unknown = [f for f in requested if f not in known]
    if unknown:
        raise UserError(
            f"format {', '.join(unknown)} is not in the timeline (it has {', '.join(known)})",
            hint='add it to "formats" in edl.json and run `plan validate`',
        )
    return list(dict.fromkeys(requested))


def _music_file(project: ProjectPaths, timeline: Timeline) -> Path | None:
    if timeline.music_path is None:
        return None
    path = project.root / timeline.music_path
    if not path.is_file():
        raise UserError(
            f"the music bed {path} does not exist",
            hint=f'run `{APP_NAME} music {project.slug}`, or set "music": {{"mode": "none"}} '
            "in edl.json",
        )
    return path


def _describe(fmt: str, path: Path, voice: Path, fps: int) -> Output:
    width, height = video_size(path)
    return Output(fmt, path, voice, width, height, count_frames(path), fps)
