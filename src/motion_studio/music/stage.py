"""The music stage: `build/music.wav` and `build/music.json` from the EDL's music block.

The bed starts at output time zero, so its beat times are output seconds; `plan validate`
reads them from `music.json` to snap B-roll and image starts.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from motion_studio import APP_NAME
from motion_studio.config import load_config
from motion_studio.errors import UserError
from motion_studio.media.ffmpeg import run_ffmpeg
from motion_studio.music import acestep, library
from motion_studio.music.beats import BEATS_PER_BAR, BedAnalysis, HitName, TempoSource, analyze_bed
from motion_studio.music.shape import CHAIN, shape_bed
from motion_studio.music.vocals import MAX_SPEECH_RATIO, speech_ratio
from motion_studio.paths import ProjectPaths, project_paths
from motion_studio.plan import MUSIC_JSON, resolve_project
from motion_studio.state import (
    ensure_free_disk,
    mark_done,
    mark_failed,
    project_lock,
    stage_is_fresh,
)

STAGE = "music"
MUSIC_WAV = "music.wav"
# Generation runs this much past the timeline so the mix can fade out instead of cutting.
TAIL_S = 3.0
MAX_ATTEMPTS = 3
DEFAULT_PROMPT = "minimal electronic, warm pads, soft drums, calm, instrumental"
DEFAULT_SEED = 1

Mode = Literal["generate", "library", "none"]


class Attempt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seed: int
    speech_ratio: float
    accepted: bool


class MusicSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_s: float
    end_s: float
    energy_db: float = Field(description="Mean level relative to the loudest section (0).")


class MusicHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: HitName
    time_s: float = Field(description="Seconds from the start of the bed.")


class MusicInfo(BaseModel):
    """`build/music.json`: what the bed is, how to reproduce it and how to credit it."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    mode: Mode
    path: str | None = Field(description="The bed relative to the project; null for none.")
    duration_s: float | None = None
    prompt: str | None = None
    seed: int | None = Field(default=None, description="The seed of the accepted generation.")
    bpm: float | None = Field(default=None, description="Requested BPM, or the track's.")
    detected_bpm: float | None = Field(
        default=None, description="Measured tempo, cross-checked against the section changes."
    )
    tracker_bpm: float | None = Field(default=None, description="librosa's coarse estimate.")
    tempo_from: TempoSource | None = Field(
        default=None, description="onsets, or sections when the section period corrected it."
    )
    beats_per_bar: int = BEATS_PER_BAR
    model: str | None = None
    licence: str | None = None
    licence_source: str | None = None
    track: str | None = None
    title: str | None = None
    source_url: str | None = None
    attribution: str | None = None
    credits: str | None = Field(default=None, description="Credits file, relative to project.")
    beats: list[float] = Field(default_factory=lambda: list[float](), description="Output s.")
    bars: list[float] = Field(
        default_factory=lambda: list[float](), description="Downbeats in output s."
    )
    sections: list[MusicSection] = Field(
        default_factory=lambda: list[MusicSection](), description="The whole bed, in order."
    )
    hits: list[MusicHit] = Field(
        default_factory=lambda: list[MusicHit](),
        description="intro_end, build, drop and ending, each only when the bed has it.",
    )
    attempts: list[Attempt] = Field(default_factory=lambda: list[Attempt]())
    elapsed_s: float | None = Field(default=None, description="Generation wall time.")


@dataclass
class MusicReport:
    info: MusicInfo
    json_path: Path
    wav_path: Path | None
    fresh: bool
    credits_path: Path | None = None
    warnings: list[str] = field(default_factory=lambda: list[str]())

    def to_json(self) -> dict[str, Any]:
        return {
            **self.info.model_dump(),
            "music_json": str(self.json_path),
            "music_wav": str(self.wav_path) if self.wav_path else None,
            "credits": str(self.credits_path) if self.credits_path else None,
            "fresh": self.fresh,
            "warnings": self.warnings,
        }


def music_json_path(project: ProjectPaths) -> Path:
    return project.build / MUSIC_JSON


def music_wav_path(project: ProjectPaths) -> Path:
    return project.build / MUSIC_WAV


def run_music(
    workspace: Path,
    slug: str,
    *,
    on_step: Callable[[str], None] | None = None,
    on_wait: Callable[[str], None] | None = None,
) -> MusicReport:
    """Generate, pick or clear the music bed per the EDL. Raises UserError on a bad block."""
    project = project_paths(workspace, slug).require()
    step = on_step or (lambda _m: None)
    with project_lock(project):
        edl, resolution = resolve_project(workspace, slug)
        config = load_config(workspace, slug)
        timeline = resolution.timeline
        duration = timeline.duration_frames / timeline.fps
        block = edl.music
        mode: Mode = block.mode or config.music.mode
        project.build.mkdir(parents=True, exist_ok=True)
        try:
            if mode == "none":
                return _none(project)
            if mode == "library":
                return _library(workspace, project, block.prompt, block.bpm, block.track, duration)
            return _generate(
                project,
                prompt=block.prompt or DEFAULT_PROMPT,
                bpm=block.bpm,
                seed=block.seed if block.seed is not None else DEFAULT_SEED,
                duration=duration,
                step=step,
                on_wait=on_wait,
            )
        except UserError as exc:
            mark_failed(project, STAGE, exc.message)
            raise


def _fresh_report(
    project: ProjectPaths, params: dict[str, Any], until_s: float
) -> MusicReport | None:
    path = music_json_path(project)
    if not path.exists() or not stage_is_fresh(project, STAGE, [], params=params):
        return None
    info = MusicInfo.model_validate_json(path.read_text(encoding="utf-8"))
    wav = project.root / info.path if info.path else None
    # A music.json from before the bar grid: analyse the bed again rather than regenerate it.
    if wav is not None and wav.exists() and info.beats and info.tempo_from is None:
        info = info.model_copy(update=_grid_fields(analyze_bed(wav, until_s=until_s)))
        _write(project, info)
    credits = project.root / info.credits if info.credits else None
    return MusicReport(info, path, wav, fresh=True, credits_path=credits)


def _write(project: ProjectPaths, info: MusicInfo) -> Path:
    path = music_json_path(project)
    path.write_text(info.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def _none(project: ProjectPaths) -> MusicReport:
    music_wav_path(project).unlink(missing_ok=True)
    info = MusicInfo(mode="none", path=None)
    path = _write(project, info)
    mark_done(project, STAGE, [], outputs=[path], params={"mode": "none"})
    return MusicReport(info, path, None, fresh=False)


def _generate(
    project: ProjectPaths,
    *,
    prompt: str,
    bpm: int | None,
    seed: int,
    duration: float,
    step: Callable[[str], None],
    on_wait: Callable[[str], None] | None,
) -> MusicReport:
    length = round(duration + TAIL_S, 3)
    params = {
        "mode": "generate",
        "prompt": prompt,
        "bpm": bpm,
        "seed": seed,
        "duration": length,
        "model": acestep.MODEL,
        "shaping": CHAIN,
    }
    fresh = _fresh_report(project, params, duration)
    if fresh is not None:
        return fresh
    ensure_free_disk(project.root)
    wav = music_wav_path(project)
    candidate = project.build / "music.candidate.wav"
    attempts: list[Attempt] = []
    elapsed = 0.0
    for offset in range(MAX_ATTEMPTS):
        step(f"generating {length:.0f} s of music with ACE-Step (seed {seed + offset})")
        generated = acestep.generate(
            prompt=prompt,
            duration_s=length,
            bpm=bpm,
            seed=seed + offset,
            out=candidate,
            on_wait=on_wait,
        )
        elapsed += generated.elapsed_s
        ratio = round(speech_ratio(generated.wav), 3)
        accepted = ratio <= MAX_SPEECH_RATIO
        attempts.append(Attempt(seed=generated.seed, speech_ratio=ratio, accepted=accepted))
        if accepted:
            shape_bed(generated.wav, wav)
            generated.wav.unlink(missing_ok=True)
            break
        generated.wav.unlink(missing_ok=True)
    else:
        raise UserError(
            f"all {MAX_ATTEMPTS} generations had vocals (seeds {seed}-{seed + MAX_ATTEMPTS - 1})",
            hint='describe instruments only in "prompt", try another "seed", '
            'or use "mode": "library"',
        )
    grid = analyze_bed(wav, until_s=duration)
    record = acestep.installed()
    info = MusicInfo(
        mode="generate",
        path=f"build/{MUSIC_WAV}",
        duration_s=length,
        prompt=prompt,
        seed=attempts[-1].seed,
        bpm=bpm,
        **_grid_fields(grid),
        model=acestep.MODEL,
        licence=record.licence if record else None,
        licence_source=_licence_source(record),
        attempts=attempts,
        elapsed_s=round(elapsed, 1),
    )
    path = _write(project, info)
    mark_done(project, STAGE, [], outputs=[wav, path], params=params)
    return MusicReport(info, path, wav, fresh=False)


def _grid_fields(grid: BedAnalysis) -> dict[str, Any]:
    return {
        "detected_bpm": grid.bpm,
        "tracker_bpm": grid.tracker_bpm,
        "tempo_from": grid.tempo_from,
        "beats": grid.beats,
        "bars": grid.bars,
        "sections": [MusicSection(**vars(s)) for s in grid.sections],
        "hits": [MusicHit(**vars(h)) for h in grid.hits],
    }


def _licence_source(record: acestep.Install | None) -> str | None:
    if record is None or record.licence_source is None:
        return None
    return f"{record.weights}: {record.licence_source}"


def _library(
    workspace: Path,
    project: ProjectPaths,
    prompt: str | None,
    bpm: int | None,
    track: str | None,
    duration: float,
) -> MusicReport:
    tags = library.tags_path(workspace)
    pick = library.pick(library.load_tags(workspace), prompt=prompt, bpm=bpm, track=track)
    source = tags.parent / pick.track.file
    if not source.is_file():
        raise UserError(f"library track {source} does not exist", hint=f"fix its entry in {tags}")
    params = {"mode": "library", "track": pick.track.model_dump(), "duration": round(duration, 3)}
    fresh = _fresh_report(project, params, duration)
    if fresh is not None:
        fresh.warnings = pick.warnings
        return fresh
    ensure_free_disk(project.root)
    wav = music_wav_path(project)
    run_ffmpeg(["-y", "-i", source, "-vn", "-ac", "2", "-ar", "48000", "-c:a", "pcm_s16le", wav])
    grid = analyze_bed(wav, until_s=duration)
    credits = library.write_credits(project, pick.track)
    info = MusicInfo(
        mode="library",
        path=f"build/{MUSIC_WAV}",
        bpm=pick.track.bpm,
        **_grid_fields(grid),
        licence=pick.track.licence,
        licence_source=str(tags),
        track=pick.track.file,
        title=pick.track.title,
        source_url=pick.track.source_url,
        attribution=pick.track.attribution,
        credits=credits.relative_to(project.root).as_posix() if credits else None,
    )
    path = _write(project, info)
    outputs = [wav, path, *([credits] if credits else [])]
    mark_done(project, STAGE, [tags, source], outputs=outputs, params=params)
    return MusicReport(info, path, wav, fresh=False, credits_path=credits, warnings=pick.warnings)


def next_hint(slug: str) -> str:
    return f"next: `{APP_NAME} plan validate {slug}` to snap overlays to the beats, then render"


def load_music_info(project: ProjectPaths) -> MusicInfo | None:
    path = music_json_path(project)
    if not path.exists():
        return None
    return MusicInfo.model_validate(json.loads(path.read_text(encoding="utf-8")))
