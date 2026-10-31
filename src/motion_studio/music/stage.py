"""The music stage: `build/music.wav` and `build/music.json` from the EDL's music block.

The bed starts at output time zero, so its beat times are output seconds; `plan validate`
reads them from `music.json` to snap B-roll and image starts.
"""

import json
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import soundfile as sf
from pydantic import BaseModel, ConfigDict, Field

from motion_studio import APP_NAME
from motion_studio.analysis import ClipAnalysis
from motion_studio.config import Config, load_config
from motion_studio.edl import resolve
from motion_studio.edl.grid import DEFAULT_BPM, BeatGrid
from motion_studio.edl.models import Edl, MusicPreset, ProductEdl
from motion_studio.edl.models import MusicAlign as EdlMusicAlign
from motion_studio.errors import UserError
from motion_studio.media.ffmpeg import run_ffmpeg
from motion_studio.music import acestep, library
from motion_studio.music.align import (
    CROSSFADE_S,
    Ending,
    grid_period,
    plan_alignment,
    render_alignment,
)
from motion_studio.music.beats import BEATS_PER_BAR, BedAnalysis, HitName, TempoSource, analyze_bed
from motion_studio.music.presets import PRESETS
from motion_studio.music.shape import CHAIN, shape_bed
from motion_studio.music.vocals import MAX_SPEECH_RATIO, speech_ratio
from motion_studio.paths import ProjectPaths, project_paths
from motion_studio.plan import MUSIC_JSON, load_analyses, resolve_project
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
MAX_CANDIDATES = 4
CANDIDATES_DIR = "music-candidates"
ALIGN_ROUNDS = 4
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


class MusicCandidate(BaseModel):
    """One generated bed, kept so the EDL's `seed` can pick it without generating again."""

    model_config = ConfigDict(extra="forbid")

    seed: int
    path: str | None = Field(description="The shaped bed relative to the project; null if vocals.")
    speech_ratio: float
    accepted: bool = Field(description="False when the bed had vocals.")
    duration_s: float
    detected_bpm: float | None = None
    tempo_from: TempoSource | None = None
    hits: list[MusicHit] = Field(default_factory=lambda: list[MusicHit]())
    elapsed_s: float = Field(description="Generation wall time, with the model load if any.")


class MusicEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    at_s: float = Field(description="Output seconds, on a bar line.")
    bars: int = Field(description="Bars repeated (positive) or cut (negative).")
    crossfade_ms: int


class MusicAlignment(BaseModel):
    """How the bed was fitted: which hit landed where, the phrase edits and the ending."""

    model_config = ConfigDict(extra="forbid")

    hit: HitName
    at: str = Field(description="The scene the hit lands on.")
    at_s: float = Field(description="The scene's start, in output seconds.")
    hit_in_bed_s: float = Field(description="The hit in the generated bed, before fitting.")
    starts_at_s: float = Field(description="Where in the generated bed the fitted bed starts.")
    edits: list[MusicEdit] = Field(default_factory=lambda: list[MusicEdit]())
    ending: Ending = Field(description="natural, or echo when the bed stops on a bar.")


class MusicInfo(BaseModel):
    """`build/music.json`: what the bed is, how to reproduce it and how to credit it."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    mode: Mode
    path: str | None = Field(description="The bed relative to the project; null for none.")
    duration_s: float | None = None
    preset: MusicPreset | None = None
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
    candidates: list[MusicCandidate] = Field(
        default_factory=lambda: list[MusicCandidate](),
        description="Every bed generated for this prompt, bpm and length; `seed` picks one.",
    )
    align: MusicAlignment | None = None
    elapsed_s: float | None = Field(default=None, description="Generation wall time.")


@dataclass
class MusicReport:
    info: MusicInfo
    json_path: Path
    wav_path: Path | None
    fresh: bool
    credits_path: Path | None = None
    warnings: list[str] = field(default_factory=lambda: list[str]())
    # Worker processes started, each loading the model once.
    model_loads: int = 0

    def to_json(self) -> dict[str, Any]:
        return {
            **self.info.model_dump(),
            "model_loads": self.model_loads,
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
    candidates: int | None = None,
    on_step: Callable[[str], None] | None = None,
    on_wait: Callable[[str], None] | None = None,
) -> MusicReport:
    """Generate, pick or clear the music bed per the EDL. Raises UserError on a bad block.

    `candidates` generates that many seeds from the EDL's (1 to 4) in one worker process.
    """
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
            if candidates is not None and mode != "generate":
                raise UserError(
                    f"--candidates needs a generated bed, and the mode is {mode}",
                    hint='set "mode": "generate" in the music block, or drop --candidates',
                )
            if candidates is not None and not 1 <= candidates <= MAX_CANDIDATES:
                raise UserError(f"--candidates takes 1 to {MAX_CANDIDATES}, not {candidates}")
            if mode == "none":
                return _none(project)
            if mode == "library":
                return _library(workspace, project, block.prompt, block.bpm, block.track, duration)
            preset = PRESETS[block.preset] if block.preset else None
            bpm = block.bpm if block.bpm is not None else (preset.bpm if preset else None)
            request = Request(
                prompt=block.prompt or (preset.prompt if preset else DEFAULT_PROMPT),
                preset=block.preset,
                bpm=bpm,
                seed=block.seed if block.seed is not None else DEFAULT_SEED,
                candidates=candidates,
            )
            return _generate(
                project,
                Fit(edl, load_analyses(project), config, duration),
                request,
                step=step,
                on_wait=on_wait,
            )
        except UserError as exc:
            mark_failed(project, STAGE, exc.message)
            raise


@dataclass(frozen=True)
class Request:
    prompt: str
    preset: MusicPreset | None
    bpm: int | None
    seed: int
    candidates: int | None


@dataclass(frozen=True)
class Fit:
    """What the bed is fitted to: the EDL, the clips it points into, and the timeline's length."""

    edl: Edl
    clips: list[ClipAnalysis]
    config: Config
    duration_s: float

    def generation_s(self, bpm: int | None) -> float:
        """The length to generate: the timeline, a product's scenes on the requested tempo.

        Product scenes move once the bed's own beats are the grid; sizing them on the requested
        tempo instead keeps the generated candidates valid across those runs.
        """
        if not isinstance(self.edl, ProductEdl):
            return self.duration_s
        steady = BeatGrid.steady(bpm or DEFAULT_BPM)
        return self._resolved(list(steady.beats)).duration_s

    def on_grid(self, beats: list[float]) -> float:
        """The timeline's length with the scenes on these beats (talk timelines ignore them)."""
        if not isinstance(self.edl, ProductEdl):
            return self.duration_s
        return self._resolved(beats).duration_s

    def aligned(self, scene: str, beat_s: float) -> tuple[float, float]:
        """The scene's start and the video's length, on a grid of `beat_s` with a beat there.

        The fitted bed's grid is phased on the hit, so it depends on the start it decides. From
        a grid with a beat at zero, so the bed starts on a beat, a few rounds settle on a start
        (a whole frame) that the grid it implies reproduces.
        """
        at = 0.0
        total = self.duration_s
        for _ in range(ALIGN_ROUNDS):
            timed = self._resolved([at % beat_s, at % beat_s + beat_s])
            start = timed.starts.get(scene, at)
            total = timed.duration_s
            if abs(start - at) < 1e-9:
                break
            at = start
        return at, total

    def _resolved(self, beats: list[float]) -> "_Timed":
        timeline = resolve(self.clips, self.edl, self.config, beats).timeline
        return _Timed(
            duration_s=timeline.duration_frames / timeline.fps,
            starts={s.id: s.start / timeline.fps for s in timeline.scenes},
        )


@dataclass(frozen=True)
class _Timed:
    duration_s: float
    starts: dict[str, float]


def _fresh_report(
    project: ProjectPaths, params: dict[str, Any], until_s: float, inputs: list[Path] | None = None
) -> MusicReport | None:
    path = music_json_path(project)
    if not path.exists() or not stage_is_fresh(project, STAGE, inputs or [], params=params):
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
    fit: Fit,
    request: Request,
    *,
    step: Callable[[str], None],
    on_wait: Callable[[str], None] | None,
) -> MusicReport:
    length = round(fit.generation_s(request.bpm) + TAIL_S, 3)
    key = {
        "prompt": request.prompt,
        "bpm": request.bpm,
        "duration": length,
        "model": acestep.MODEL,
        "shaping": CHAIN,
    }
    align = fit.edl.music.align
    params = {
        "mode": "generate",
        **key,
        "seed": request.seed,
        "preset": request.preset,
        "align": align.model_dump() if align else None,
    }
    # An aligned bed depends on every scene, not only on its length.
    inputs = [project.edl] if align else []
    store = CandidateStore(project, key)
    wanted = [request.seed + i for i in range(request.candidates or 0)]
    if all(store.get(s) for s in wanted):
        fresh = _fresh_report(project, params, fit.duration_s, inputs)
        if fresh is not None:
            return fresh
    ensure_free_disk(project.root)
    attempts: list[Attempt] = []
    chosen: MusicCandidate | None = None
    with acestep.Session(on_wait=on_wait) as session:
        for i, seed in enumerate(wanted):
            if store.get(seed) is None:
                what = f"candidate {i + 1} of {len(wanted)} (seed {seed})"
                try:
                    store.make(session, seed, request, length, what, step)
                except acestep.LowMemory as exc:
                    made = sum(1 for s in wanted if store.get(s))
                    raise UserError(
                        exc.message,
                        hint=f"close memory-hungry apps and run `{APP_NAME} music "
                        f"{project.slug} --candidates {len(wanted)}` again; the {made} already "
                        f"made are kept in {store.dir.relative_to(project.root).as_posix()}/",
                    ) from exc
        for offset in range(MAX_ATTEMPTS):
            seed = request.seed + offset
            candidate = store.get(seed) or store.make(
                session, seed, request, length, f"seed {seed}", step
            )
            attempts.append(
                Attempt(seed=seed, speech_ratio=candidate.speech_ratio, accepted=candidate.accepted)
            )
            if candidate.accepted:
                chosen = candidate
                break
        loads = session.loads
    if chosen is None or chosen.path is None:
        last = request.seed + MAX_ATTEMPTS - 1
        raise UserError(
            f"all {MAX_ATTEMPTS} generations had vocals (seeds {request.seed}-{last})",
            hint='describe instruments only in "prompt", try another "seed", '
            'or use "mode": "library"',
        )
    wav = music_wav_path(project)
    source = project.root / chosen.path
    bed = analyze_bed(source)
    if align is not None:
        grid, aligned, duration = _align(source, wav, bed, fit, align)
    else:
        shutil.copyfile(source, wav)
        grid = _until(bed, fit.on_grid(bed.beats))
        aligned, duration = None, chosen.duration_s
    record = acestep.installed()
    info = MusicInfo(
        mode="generate",
        path=f"build/{MUSIC_WAV}",
        duration_s=duration,
        preset=request.preset,
        prompt=request.prompt,
        seed=chosen.seed,
        bpm=request.bpm,
        **grid,
        model=acestep.MODEL,
        licence=record.licence if record else None,
        licence_source=_licence_source(record),
        attempts=attempts,
        candidates=store.candidates,
        align=aligned,
        elapsed_s=round(sum(c.elapsed_s for c in store.candidates if c.seed == chosen.seed), 1),
    )
    path = _write(project, info)
    mark_done(project, STAGE, inputs, outputs=[wav, path], params=params)
    return MusicReport(info, path, wav, fresh=False, model_loads=loads)


def _align(
    source: Path, wav: Path, bed: BedAnalysis, fit: Fit, align: EdlMusicAlign
) -> tuple[dict[str, Any], MusicAlignment, float]:
    """Fit the bed so the hit lands on the scene; returns music.json's grid fields and record."""
    if len(bed.beats) < 2:
        raise UserError("the bed has no beat grid to align on", hint='try another "seed"')
    beat = grid_period(bed)
    at_s, total = fit.aligned(align.at, beat)
    plan = plan_alignment(bed, sf.info(str(source)).duration, align.hit, at_s, total, BEATS_PER_BAR)
    render_alignment(source, plan, wav)
    grid = {
        "detected_bpm": bed.bpm,
        "tracker_bpm": bed.tracker_bpm,
        "tempo_from": bed.tempo_from,
        "beats": plan.beats,
        "bars": plan.bars,
        "sections": [MusicSection(**vars(s)) for s in plan.sections],
        "hits": [MusicHit(**vars(h)) for h in plan.hits],
    }
    record = MusicAlignment(
        hit=align.hit,
        at=align.at,
        at_s=round(at_s, 4),
        hit_in_bed_s=plan.hit_src_s,
        starts_at_s=round(plan.pieces[0].src_start, 3),
        edits=[
            MusicEdit(at_s=round(e.at_s, 3), bars=e.bars, crossfade_ms=round(CROSSFADE_S * 1000))
            for e in plan.edits
        ],
        ending=plan.ending,
    )
    return grid, record, round(total, 3)


def _until(bed: BedAnalysis, end_s: float) -> dict[str, Any]:
    """music.json's grid fields, the beats and bars stopping at the end of the timeline."""
    fields = _grid_fields(bed)
    fields["beats"] = [b for b in bed.beats if b < end_s - 1e-9]
    fields["bars"] = [b for b in bed.bars if b < end_s - 1e-9]
    return fields


class _Index(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: dict[str, Any]
    candidates: list[MusicCandidate] = Field(default_factory=lambda: list[MusicCandidate]())


class CandidateStore:
    """The beds generated for one prompt, bpm, length, model and shaping, by seed.

    `build/music-candidates/` keeps them across runs; a different key starts it afresh.
    """

    def __init__(self, project: ProjectPaths, key: dict[str, Any]) -> None:
        self.project = project
        self.dir = project.build / CANDIDATES_DIR
        self.index_path = self.dir / "index.json"
        index = None
        if self.index_path.exists():
            try:
                index = _Index.model_validate_json(self.index_path.read_text(encoding="utf-8"))
            except ValueError:
                index = None
        if index is None or index.key != json.loads(json.dumps(key)):
            if self.dir.exists():
                shutil.rmtree(self.dir)
            index = _Index(key=key)
        self.index = index

    @property
    def candidates(self) -> list[MusicCandidate]:
        return sorted(self.index.candidates, key=lambda c: c.seed)

    def get(self, seed: int) -> MusicCandidate | None:
        for candidate in self.index.candidates:
            if candidate.seed == seed and (
                candidate.path is None or (self.project.root / candidate.path).is_file()
            ):
                return candidate
        return None

    def make(
        self,
        session: acestep.Session,
        seed: int,
        request: Request,
        length: float,
        what: str,
        step: Callable[[str], None],
    ) -> MusicCandidate:
        """Generate, check for vocals, shape and analyse one bed, and record it."""
        session.check_memory(what)
        step(f"generating {length:.0f} s of music with ACE-Step ({what})")
        self.dir.mkdir(parents=True, exist_ok=True)
        raw = self.dir / f"seed-{seed}.generated.wav"
        generated = session.generate(
            prompt=request.prompt, duration_s=length, bpm=request.bpm, seed=seed, out=raw
        )
        ratio = round(speech_ratio(generated.wav), 3)
        accepted = ratio <= MAX_SPEECH_RATIO
        path: str | None = None
        bed = BedAnalysis()
        if accepted:
            shaped = shape_bed(generated.wav, self.dir / f"seed-{seed}.wav")
            path = shaped.relative_to(self.project.root).as_posix()
            bed = analyze_bed(shaped)
        generated.wav.unlink(missing_ok=True)
        candidate = MusicCandidate(
            seed=seed,
            path=path,
            speech_ratio=ratio,
            accepted=accepted,
            duration_s=length,
            detected_bpm=bed.bpm,
            tempo_from=bed.tempo_from,
            hits=[MusicHit(**vars(h)) for h in bed.hits],
            elapsed_s=generated.elapsed_s,
        )
        self.index.candidates = [c for c in self.index.candidates if c.seed != seed]
        self.index.candidates.append(candidate)
        self.index_path.write_text(self.index.model_dump_json(indent=2) + "\n", encoding="utf-8")
        return candidate


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
