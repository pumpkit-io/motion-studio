"""Ingest: give every raw file a stable clip ID and turn it into the media later stages read.

`project.toml` holds one `[clips.<id>]` table per clip with `source`, `role` and `auto_role`.
`auto_role` is what motion-studio classified; a `role` that differs from it is the creator's
override and nothing motion-studio does changes it. IDs are never renumbered or reused, even
when the source disappears from raw/.
"""

import re
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import tomli_w
from pydantic import BaseModel

from motion_studio import APP_NAME
from motion_studio.analysis.models import Role
from motion_studio.audio.enhance import Denoiser, denoiser_available, extract_voice
from motion_studio.config import load_config
from motion_studio.errors import UserError
from motion_studio.kind import ProjectKind, project_kind
from motion_studio.media.ffmpeg import FFmpegCaps, ffmpeg_caps, run_ffmpeg
from motion_studio.media.normalise import (
    HEIF_EXTENSIONS,
    HEIF_HINT,
    heif_decoder,
    make_mezzanine,
    normalise_image,
)
from motion_studio.media.probe import Probe, probe
from motion_studio.paths import MARKERS_SUFFIX, ProjectPaths, project_paths
from motion_studio.state import (
    ensure_free_disk,
    load_state,
    mark_done,
    mark_failed,
    project_lock,
    record_warning,
    stage_is_fresh,
)

STAGE = "ingest"
# Bump when the mezzanine or audio recipe changes, so existing projects re-ingest.
RECIPE = 1

ROLES: tuple[Role, ...] = ("aroll", "broll", "image", "screen")
# Product projects have no A-roll, so screen recordings take its prefix (ADR 0005's `c2.m.<name>`).
PREFIX: dict[Role, str] = {"aroll": "c", "broll": "b", "image": "i", "screen": "c"}

# A video whose loudest moment is quieter than this has no speech worth cutting.
SPEECH_PEAK_DB = -35.0

MANIFEST = "manifest.json"

# Called with (done, total) in the same unit, here seconds of media.
Progress = Callable[[float, float], None]


class ClipEntry(BaseModel):
    source: str
    role: Role
    auto_role: Role

    @property
    def overridden(self) -> bool:
        return self.role != self.auto_role


class ClipMedia(BaseModel):
    """One clip's normalised media, as `media/manifest.json` lists it for later stages."""

    id: str
    role: Role
    source: str
    kind: Literal["video", "image"]
    mezzanine: str
    audio: str | None = None
    audio_16k: str | None = None
    width: int
    height: int
    fps: float | None = None
    duration_s: float | None = None
    hdr: Literal["hlg", "pq"] | None = None
    tonemap: str | None = None
    denoiser: Denoiser | None = None


class Manifest(BaseModel):
    schema_version: Literal[1] = 1
    clips: list[ClipMedia]


@dataclass
class IngestReport:
    project: ProjectPaths
    clips: list[ClipMedia]
    ingested: list[str]
    unchanged: list[str]
    warnings: list[str] = field(default_factory=list)
    sheets: list[Path] = field(default_factory=lambda: list[Path]())
    noop: bool = False

    def to_json(self) -> dict[str, Any]:
        root = self.project.root
        return {
            "project": str(root),
            "noop": self.noop,
            "clips": [
                {
                    **c.model_dump(),
                    "mezzanine": str(root / c.mezzanine),
                    "audio": str(root / c.audio) if c.audio else None,
                    "audio_16k": str(root / c.audio_16k) if c.audio_16k else None,
                    "status": "ingested" if c.id in self.ingested else "unchanged",
                }
                for c in self.clips
            ],
            "manifest": str(self.project.media / MANIFEST),
            "sheets": [str(p) for p in self.sheets],
            "warnings": self.warnings,
        }


def load_clips(project: ProjectPaths) -> dict[str, ClipEntry]:
    """The `[clips]` table of project.toml, validated."""
    data = _read_toml(project)
    clips = data.get("clips", {})
    if not isinstance(clips, dict):
        raise UserError(f"{project.project_toml}: [clips] must be a table")
    entries: dict[str, ClipEntry] = {}
    for clip_id, raw in clips.items():  # pyright: ignore[reportUnknownVariableType]
        if not isinstance(raw, dict) or not re.fullmatch(r"[cbi][1-9][0-9]*", str(clip_id)):
            raise UserError(f"{project.project_toml}: [clips.{clip_id}] is not a clip entry")
        values: dict[str, Any] = dict(raw)  # pyright: ignore[reportUnknownArgumentType]
        role = values.get("role")
        if role not in ROLES:
            raise UserError(
                f"{project.project_toml}: clips.{clip_id}.role is {role!r}",
                hint=f"use one of {', '.join(ROLES)}",
            )
        values.setdefault("auto_role", role)
        entries[str(clip_id)] = ClipEntry.model_validate(values)
    return entries


def record_auto_role(project: ProjectPaths, clip_id: str, role: Role) -> ClipEntry:
    """Store a new classification; `role` follows it unless the creator overrode it."""
    entries = load_clips(project)
    entry = entries[clip_id]
    updated = ClipEntry(
        source=entry.source, role=entry.role if entry.overridden else role, auto_role=role
    )
    entries[clip_id] = updated
    _write_clips(project, entries)
    return updated


def markers_sidecar(project: ProjectPaths, source: str) -> Path:
    """Where the markers of the clip from `source` (relative to the project) would be."""
    path = project.root / source
    return path.with_name(path.stem + MARKERS_SUFFIX)


def load_manifest(project: ProjectPaths) -> Manifest:
    path = project.media / MANIFEST
    if not path.exists():
        raise UserError(f"{project.slug!r} is not ingested", hint=f"run `ingest {project.slug}`")
    return Manifest.model_validate_json(path.read_text(encoding="utf-8"))


def ingest_project(
    workspace: Path,
    slug: str,
    *,
    on_warning: Callable[[str], None] | None = None,
    on_step: Callable[[str], None] | None = None,
    on_progress: Progress | None = None,
) -> IngestReport:
    """`on_progress` gets (seconds encoded, clip seconds) while a mezzanine is written."""
    project = project_paths(workspace, slug).require()
    ensure_free_disk(project.media)
    with project_lock(project):
        try:
            return _ingest(
                project,
                workspace,
                on_warning or (lambda _msg: None),
                on_step or (lambda _msg: None),
                on_progress or (lambda _done, _total: None),
            )
        except Exception as exc:
            mark_failed(project, STAGE, str(exc))
            raise


def _ingest(
    project: ProjectPaths,
    workspace: Path,
    on_warning: Callable[[str], None],
    on_step: Callable[[str], None],
    on_progress: Progress,
) -> IngestReport:
    fps = load_config(workspace, project.slug).defaults.fps
    kind = project_kind(project)
    caps = ffmpeg_caps()
    heif = heif_decoder()
    params: dict[str, Any] = {
        "recipe": RECIPE,
        "fps": fps,
        "denoiser": denoiser_available(caps),
        "heif": heif,
    }
    # Only product projects carry the kind, so existing talk projects stay fresh.
    if kind is ProjectKind.PRODUCT:
        params["project_kind"] = kind.value
    project.media.mkdir(exist_ok=True)
    if stage_is_fresh(project, STAGE, [project.raw], params=params):
        entries = load_clips(project)
        clips = [
            c.model_copy(update={"role": entries[c.id].role}) if c.id in entries else c
            for c in load_manifest(project).clips
        ]
        return IngestReport(project, clips, [], [c.id for c in clips], noop=True)

    warnings: list[str] = []

    def warn(message: str) -> None:
        warnings.append(message)
        record_warning(project, STAGE, message)
        on_warning(message)

    entries = load_clips(project)
    known = {entry.source: clip_id for clip_id, entry in entries.items()}
    for clip_id, entry in entries.items():
        if not (project.root / entry.source).is_file():
            warn(f"{clip_id}: {entry.source} is missing from raw/; its ID stays reserved")

    probes: dict[str, Probe] = {}
    added = False
    for source in sorted(p for p in project.raw.iterdir() if _visible_file(p)):
        if source.name.endswith(MARKERS_SUFFIX):
            continue
        rel = source.relative_to(project.root).as_posix()
        if heif is None and source.suffix.lower() in HEIF_EXTENSIONS:
            warn(f"skipped {rel}: nothing here decodes HEIC/HEIF; {HEIF_HINT}")
            continue
        info = probe(source)
        if rel in known:
            probes[known[rel]] = info
            continue
        if info.kind == "unsupported":
            warn(f"skipped {rel}: not a video or image ({info.reason})")
            continue
        role = _provisional_role(source, info, kind)
        clip_id = _next_id(entries, role)
        entries[clip_id] = ClipEntry(source=rel, role=role, auto_role=role)
        known[rel] = clip_id
        probes[clip_id] = info
        added = True
    if not probes:
        raise UserError(
            f"{project.raw} has no video or image files",
            hint=f"copy the takes into it, then run `{APP_NAME} ingest {project.slug}`",
        )
    if added:
        _write_clips(project, entries)

    state = load_state(project)
    media: list[ClipMedia] = []
    ingested: list[str] = []
    unchanged: list[str] = []
    retained: list[str] = []
    sheets: list[Path] = []
    for clip_id in sorted(probes, key=_id_order):
        entry, info = entries[clip_id], probes[clip_id]
        source = project.root / entry.source
        record_key = f"{STAGE}.{clip_id}"
        clip_params = {**params, "kind": info.kind}
        previous = _manifest_entry(project, clip_id)
        if previous and stage_is_fresh(project, record_key, [source], params=clip_params):
            media.append(previous.model_copy(update={"role": entry.role}))
            unchanged.append(clip_id)
            retained += state.stages[record_key].warnings
            continue
        on_step(f"normalising {clip_id} ({entry.source})")
        encoded = _out_of(on_progress, info.duration_s) if info.duration_s else None
        clip, clip_warnings = _normalise(project, clip_id, entry, info, fps, caps, encoded)
        for message in clip_warnings:
            warn(message)
        outputs = [project.root / p for p in (clip.mezzanine, clip.audio, clip.audio_16k) if p]
        if clip.role == "screen":
            sheet, sheet_warnings = write_screen_sheet(project, clip)
            for message in sheet_warnings:
                warn(message)
            clip_warnings = [*clip_warnings, *sheet_warnings]
            outputs.append(sheet)
            sheets.append(sheet)
        mark_done(
            project,
            record_key,
            [source],
            outputs=outputs,
            params=clip_params,
            warnings=clip_warnings,
        )
        media.append(clip)
        ingested.append(clip_id)

    manifest_path = project.media / MANIFEST
    manifest_path.write_text(
        Manifest(clips=media).model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    outputs = [manifest_path] + [
        project.root / p for c in media for p in (c.mezzanine, c.audio, c.audio_16k) if p
    ]
    outputs += [project.asset_sheet(c.id) for c in media if c.role == "screen"]
    mark_done(project, STAGE, [project.raw], outputs=outputs, params=params, warnings=retained)
    return IngestReport(project, media, ingested, unchanged, [*warnings, *retained], sheets)


def _normalise(
    project: ProjectPaths,
    clip_id: str,
    entry: ClipEntry,
    info: Probe,
    fps: int,
    caps: FFmpegCaps,
    progress: Callable[[float], None] | None = None,
) -> tuple[ClipMedia, list[str]]:
    source = project.root / entry.source

    def rel(path: Path) -> str:
        return path.relative_to(project.root).as_posix()

    if info.kind == "image":
        dest, width, height = normalise_image(source, project.media / clip_id)
        return ClipMedia(
            id=clip_id,
            role=entry.role,
            source=entry.source,
            kind="image",
            mezzanine=rel(dest),
            width=width,
            height=height,
        ), []
    warnings: list[str] = []
    mezzanine = make_mezzanine(
        source, project.media / f"{clip_id}.mp4", info, fps=fps, caps=caps, progress=progress
    )
    warnings += mezzanine.warnings
    audio = audio_16k = None
    denoiser: Denoiser | None = None
    # A screen recording's sound is never cut or mixed, so it gets no voice track.
    if info.has_audio and entry.role != "screen":
        voice = extract_voice(
            source,
            project.media / f"{clip_id}.wav",
            project.media / f"{clip_id}_16k.wav",
            caps=caps,
        )
        audio, audio_16k, denoiser = rel(voice.wav), rel(voice.wav_16k), voice.denoiser
        if voice.warning:
            warnings.append(f"{clip_id}: {voice.warning}")
    out = probe(mezzanine.path)
    return ClipMedia(
        id=clip_id,
        role=entry.role,
        source=entry.source,
        kind="video",
        mezzanine=rel(mezzanine.path),
        audio=audio,
        audio_16k=audio_16k,
        width=mezzanine.width,
        height=mezzanine.height,
        fps=fps,
        duration_s=round(out.duration_s, 3),
        hdr=info.hdr,
        tonemap=mezzanine.tonemap,
        denoiser=denoiser,
    ), [w if w.startswith(clip_id) else f"{clip_id}: {w}" for w in warnings]


def _out_of(on_progress: Progress, total: float) -> Callable[[float], None]:
    return lambda done: on_progress(done, total)


def _manifest_entry(project: ProjectPaths, clip_id: str) -> ClipMedia | None:
    try:
        clips = load_manifest(project).clips
    except (UserError, ValueError):
        return None
    return next((c for c in clips if c.id == clip_id), None)


def _provisional_role(source: Path, info: Probe, kind: ProjectKind) -> Role:
    """Image; in a product project, a screen recording; else video split on its audio level.

    The analysis stage replaces a talk project's guess with speech and face evidence.
    """
    if info.kind == "image":
        return "image"
    if kind is ProjectKind.PRODUCT:
        return "screen"
    if not info.has_audio:
        return "broll"
    lines = run_ffmpeg(["-i", source, "-map", "0:a:0", "-af", "volumedetect", "-f", "null", "-"])
    for line in lines:
        match = re.search(r"max_volume: (-?[\d.]+|-inf) dB", line)
        if match:
            peak = float(match.group(1))
            return "aroll" if peak > SPEECH_PEAK_DB else "broll"
    return "aroll"


def write_screen_sheet(project: ProjectPaths, clip: ClipMedia) -> tuple[Path, list[str]]:
    # look imports this module, so it can only be imported at call time.
    from motion_studio.look import write_screen_sheet as write

    return write(project, clip)


def _next_id(entries: dict[str, ClipEntry], role: Role) -> str:
    prefix = PREFIX[role]
    used = [int(i[1:]) for i in entries if i.startswith(prefix)]
    return f"{prefix}{max(used, default=0) + 1}"


def _id_order(clip_id: str) -> tuple[int, int]:
    return ("cbi".index(clip_id[0]), int(clip_id[1:]))


def _visible_file(path: Path) -> bool:
    return path.is_file() and not path.name.startswith(".")


def _read_toml(project: ProjectPaths) -> dict[str, Any]:
    try:
        return tomllib.loads(project.project_toml.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise UserError(f"{project.project_toml} is not valid TOML: {exc}") from exc


def _write_clips(project: ProjectPaths, entries: dict[str, ClipEntry]) -> None:
    data = _read_toml(project)
    data["clips"] = {
        clip_id: entries[clip_id].model_dump() for clip_id in sorted(entries, key=_id_order)
    }
    tmp = project.project_toml.with_name(".project.toml.tmp")
    tmp.write_text(tomli_w.dumps(data), encoding="utf-8")
    tmp.replace(project.project_toml)
