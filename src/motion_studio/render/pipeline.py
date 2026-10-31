"""`motion-studio render`: assemble once, compose and mix each format into preview/ or final/."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from motion_studio import APP_NAME
from motion_studio.config import Brand as BrandConfig
from motion_studio.config import load_config
from motion_studio.edl import Timeline
from motion_studio.edl.models import TimelineBroll, TimelineFootage, TimelineImage
from motion_studio.errors import MotionStudioError, UserError
from motion_studio.ingest import MANIFEST, ClipMedia, load_manifest
from motion_studio.paths import ProjectPaths, project_paths
from motion_studio.plan import load_edl, timeline_path, validate_project
from motion_studio.render import share as sharing
from motion_studio.render.assemble import assemble, assembly_canvas, count_frames, video_size
from motion_studio.render.compose import (
    PRODUCT,
    REEL,
    compose,
    find_brand,
    prepare_public,
    product_props,
    props,
)
from motion_studio.render.mix import mix
from motion_studio.render.renderer import find_renderer, remotion_version
from motion_studio.state import (
    ensure_free_disk,
    mark_done,
    mark_failed,
    project_lock,
    record_warning,
    stage_is_fresh,
    stage_status,
)
from motion_studio.target import RenderTarget

DEFAULT_CONCURRENCY = 4
# Bump when the assemble recipe changes, so earlier assembled A-roll goes stale.
ASSEMBLE_RECIPE = 2
# Bump when the renderer's output or the mix recipe changes, so earlier renders go stale.
RENDER_RECIPE = 3
ASSEMBLE_RECORD = "render.assemble"
# Bump when the share copy's encode changes: it redoes the share copies, not the finals.
SHARE_RECIPE = 1
SHARE_RECORD = "final.share"


@dataclass(frozen=True)
class Output:
    format: str
    path: Path
    voice: Path
    width: int
    height: int
    frames: int
    fps: int
    share: Path | None = None
    share_written: bool = False

    @property
    def share_bytes(self) -> int | None:
        return self.share.stat().st_size if self.share is not None else None

    def to_json(self) -> dict[str, Any]:
        share = None
        if self.share is not None:
            share = {"path": str(self.share), "bytes": self.share_bytes}
        return {
            "format": self.format,
            "path": str(self.path),
            "voice": str(self.voice),
            "width": self.width,
            "height": self.height,
            "duration_s": round(self.frames / self.fps, 3),
            "share": share,
        }


@dataclass
class RenderReport:
    stage: str
    outputs: list[Output]
    # None for a product video, which has no A-roll to assemble.
    assembled: Path | None
    cuts_s: list[float]
    noop: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "noop": self.noop,
            "outputs": [o.to_json() for o in self.outputs],
            "assembled": str(self.assembled) if self.assembled is not None else None,
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
    on_progress: Callable[[float, float], None] | None = None,
) -> RenderReport:
    """`on_progress` gets (seconds assembled, timeline seconds) while the A-roll is cut."""
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
        clips = {c.id: c for c in load_manifest(project).clips}
        product = timeline.kind == "product"
        media = (
            _footage_media(project, timeline)
            if product
            else _a_roll_media(project, timeline, clips)
        )
        assemble_inputs = [timeline_path(project), manifest, *media]
        inputs = [*assemble_inputs, *_overlay_media(project, timeline)]
        inputs += [*([music_file] if music_file is not None else []), *brand.files()]
        params = {
            "recipe": RENDER_RECIPE,
            "formats": chosen,
            "music": music.model_dump(),
            "master": config.master.model_dump(),
            "remotion": remotion_version(renderer),
        }
        outputs = {
            fmt: (output_path(project, target, fmt), voice_path(project, fmt)) for fmt in chosen
        }
        assembled = None if product else project.build / "assembled.mp4"
        cuts = [round(start / timeline.fps, 3) for start in _cut_frames(timeline)]

        if stage_is_fresh(project, stage, inputs, params=params):
            done = [_describe(fmt, *outputs[fmt], timeline.fps) for fmt in chosen]
            done = _share_copies(project, target, done, step)
            return RenderReport(stage, done, assembled, cuts, noop=True)

        try:
            for message in brand.warnings:
                record_warning(project, stage, message)
                warn(message)
            if assembled is not None and not stage_is_fresh(
                project, ASSEMBLE_RECORD, assemble_inputs, params={"recipe": ASSEMBLE_RECIPE}
            ):
                step("assembling the A-roll cuts")
                total = timeline.duration_frames / timeline.fps
                assembling = (lambda s: on_progress(s, total)) if on_progress else None
                assemble(timeline, clips, project.root, project.build, assembling)
                mark_done(
                    project,
                    ASSEMBLE_RECORD,
                    assemble_inputs,
                    outputs=[assembled],
                    params={"recipe": ASSEMBLE_RECIPE},
                )
            public = prepare_public(project.build, assembled, timeline, project.root, brand)
            done: list[Output] = []
            for fmt in chosen:
                step(f"composing {fmt} with Remotion")
                if assembled is None:
                    data = product_props(timeline, fmt, brand)
                else:
                    canvas = assembly_canvas(timeline, clips)
                    data = props(timeline, fmt, canvas, assembled.name, brand)
                composed = compose(
                    renderer,
                    data,
                    project.build,
                    public,
                    preview=target is RenderTarget.PREVIEW,
                    concurrency=concurrency,
                    composition=PRODUCT if product else REEL,
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
        except MotionStudioError as exc:
            mark_failed(project, stage, exc.message)
            raise
        done = _share_copies(project, target, done, step)
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


def _a_roll_media(
    project: ProjectPaths, timeline: Timeline, clips: dict[str, ClipMedia]
) -> list[Path]:
    """The mezzanines and voice files the runs cut from, so replacing one re-renders."""
    found: list[Path] = []
    for clip_id in dict.fromkeys(run.clip for run in timeline.runs):
        media = clips.get(clip_id)
        if media is not None:
            found += [project.root / p for p in (media.mezzanine, media.audio) if p]
    return found


def _footage_media(project: ProjectPaths, timeline: Timeline) -> list[Path]:
    """The recordings product scenes play, so replacing one re-renders."""
    srcs = [s.src for s in timeline.scenes if isinstance(s, TimelineFootage)]
    return [project.root / src for src in dict.fromkeys(srcs)]


def _cut_frames(timeline: Timeline) -> list[int]:
    if timeline.kind == "product":
        return [scene.start for scene in timeline.scenes[1:]]
    return [run.out_in for run in timeline.runs[1:]]


def _overlay_media(project: ProjectPaths, timeline: Timeline) -> list[Path]:
    srcs = [e.src for e in timeline.events if isinstance(e, TimelineBroll | TimelineImage)]
    return [project.root / src for src in dict.fromkeys(srcs)]


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


def _share_copies(
    project: ProjectPaths, target: RenderTarget, done: list[Output], step: Callable[[str], None]
) -> list[Output]:
    """Each final's share copy, kept in its own record so a share change never re-renders."""
    if target is not RenderTarget.FINAL:
        return done
    shared: list[Output] = []
    params = {"recipe": SHARE_RECIPE, "cap_bytes": sharing.CAP_BYTES}
    for out in done:
        record = f"{SHARE_RECORD}.{out.format}"
        path = sharing.share_path(out.path)
        written = not stage_is_fresh(project, record, [out.path], params=params)
        if written:
            step(f"writing the {out.format} share copy")
            try:
                cap = sharing.CAP_BYTES
                sharing.share_copy(out.path, path, cap_bytes=cap, scratch=project.build)
            except MotionStudioError as exc:
                mark_failed(project, record, exc.message)
                raise
            mark_done(project, record, [out.path], outputs=[path], params=params)
        shared.append(replace(out, share=path, share_written=written))
    return shared


def _describe(fmt: str, path: Path, voice: Path, fps: int) -> Output:
    width, height = video_size(path)
    return Output(fmt, path, voice, width, height, count_frames(path), fps)
