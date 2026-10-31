"""The analyze stage: speech, language, transcript and visual analysis per clip, then the indexes.

Writes `analysis/<clip>.json`, `analysis/retakes.json`, `analysis/packed.md`,
`analysis/assets.md` and each asset's `contact/<id>.png`, and finalises each clip's role in
project.toml. Each clip has its own state record (`analyze.<id>`), so only clips whose media
or settings changed go back through the speech-to-text and face workers.
"""

import hashlib
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from motion_studio import APP_NAME, lang
from motion_studio.analysis import (
    ClipAnalysis,
    ClipInfo,
    Faces,
    Retakes,
    ScreenMarkers,
    analyse_transcript,
    finalise_role,
    find_retakes,
    find_static,
    pack_assets,
    pack_project,
    pack_screen_project,
    project_language,
    read_descriptions,
)
from motion_studio.asr import SpeechJob, SpeechResult, model_ref, resolve_backend, transcribe_clips
from motion_studio.config import load_config
from motion_studio.errors import UserError
from motion_studio.ingest import (
    ClipMedia,
    load_clips,
    load_manifest,
    markers_sidecar,
    record_auto_role,
)
from motion_studio.kind import ProjectKind, project_kind
from motion_studio.look import write_asset_sheet
from motion_studio.paths import ProjectPaths, project_paths
from motion_studio.state import mark_done, mark_failed, project_lock, record_warning, stage_is_fresh
from motion_studio.vision import FaceJob, FaceResult, detect_faces
from motion_studio.vision.motion import MOTION_FPS, find_shots, frame_differences

STAGE = "analyze"
# Bump when the analysis output changes for the same audio, so existing projects re-analyse.
RECIPE = 2

RETAKES = "retakes.json"
PACKED = "packed.md"
ASSETS = "assets.md"


@dataclass
class ClipSummary:
    id: str
    role: str
    language: str | None
    confidence: float | None
    words: int
    utterances: int
    path: Path
    analysed: bool
    markers: int = 0


@dataclass
class AnalyzeReport:
    project: ProjectPaths
    language: str
    language_source: str
    clips: list[ClipSummary]
    retake_clusters: int
    packed: Path
    retakes: Path | None
    assets: Path
    sheets: list[Path] = field(default_factory=lambda: list[Path]())
    backend: str | None = None
    model: str | None = None
    worker_pid: int | None = None
    worker_peak_rss_mb: float | None = None
    warnings: list[str] = field(default_factory=lambda: list[str]())
    noop: bool = False

    @property
    def packed_tokens(self) -> int:
        return len(self.packed.read_text(encoding="utf-8")) // 4

    def to_json(self) -> dict[str, Any]:
        return {
            "project": str(self.project.root),
            "noop": self.noop,
            "language": self.language,
            "language_source": self.language_source,
            "clips": [
                {
                    "id": c.id,
                    "role": c.role,
                    "language": c.language,
                    "confidence": c.confidence,
                    "words": c.words,
                    "utterances": c.utterances,
                    "markers": c.markers,
                    "analysis": str(c.path),
                    "status": "analysed" if c.analysed else "unchanged",
                }
                for c in self.clips
            ],
            "retake_clusters": self.retake_clusters,
            "packed": str(self.packed),
            "packed_tokens": self.packed_tokens,
            "retakes": str(self.retakes) if self.retakes else None,
            "assets": str(self.assets),
            "sheets": [str(p) for p in self.sheets],
            "asr": {
                "backend": self.backend,
                "model": self.model,
                "worker_pid": self.worker_pid,
                "worker_peak_rss_mb": self.worker_peak_rss_mb,
            },
            "warnings": self.warnings,
        }


def analysis_path(project: ProjectPaths, clip_id: str) -> Path:
    return project.analysis / f"{clip_id}.json"


def load_analysis(project: ProjectPaths, clip_id: str) -> ClipAnalysis:
    path = analysis_path(project, clip_id)
    if not path.exists():
        raise UserError(f"clip {clip_id} is not analysed", hint=f"run `analyze {project.slug}`")
    return ClipAnalysis.model_validate_json(path.read_text(encoding="utf-8"))


def analyze_project(
    workspace: Path,
    slug: str,
    *,
    clip: str | None = None,
    on_warning: Callable[[str], None] | None = None,
) -> AnalyzeReport:
    project = project_paths(workspace, slug).require()
    with project_lock(project):
        try:
            return _analyze(project, workspace, clip, on_warning or (lambda _msg: None))
        except Exception as exc:
            mark_failed(project, STAGE, str(exc))
            raise


def _analyze(
    project: ProjectPaths, workspace: Path, only: str | None, on_warning: Callable[[str], None]
) -> AnalyzeReport:
    config = load_config(workspace, project.slug)
    config.ensure_supported()
    manifest = load_manifest(project)
    entries = load_clips(project)
    media = [c.model_copy(update={"role": entries[c.id].role}) for c in manifest.clips]
    if only is not None and only not in {c.id for c in media}:
        raise UserError(
            f"no clip {only!r} in {project.slug!r}",
            hint=f"clips: {', '.join(c.id for c in media)}",
        )
    kind = project_kind(project)
    talk = kind is ProjectKind.TALK
    configured = config.defaults.language
    if talk:
        backend = resolve_backend(config.asr.backend)
        ref = model_ref(backend, config.asr.model)
        params: dict[str, Any] = {
            "recipe": RECIPE,
            "backend": backend,
            "model": f"{ref.repo}@{ref.revision}",
            "language": configured,
            "lang_data": _lang_data_hash(),
        }
    else:
        backend = None
        params = {"recipe": RECIPE, "project_kind": kind.value}
    manifest_path = project.media / "manifest.json"
    stage_inputs = [
        manifest_path,
        project.project_toml,
        *(markers_sidecar(project, c.source) for c in media if c.role == "screen"),
    ]
    project.analysis.mkdir(exist_ok=True)
    outputs = [project.analysis / PACKED, project.analysis / ASSETS]
    if talk:
        outputs.append(project.analysis / RETAKES)

    if only is None and stage_is_fresh(project, STAGE, stage_inputs, params=params):
        analyses = [load_analysis(project, c.id) for c in media]
        return _report(project, kind, media, analyses, set(), configured, noop=True)

    stale = [
        c
        for c in media
        if (only is None or c.id == only) and (c.id == only or not _clip_fresh(project, c, params))
    ]
    jobs = [_job(project, c, configured) for c in stale if c.audio_16k] if talk else []
    speech: dict[str, SpeechResult] = {}
    run = None
    warnings: list[str] = []
    if jobs:
        assert backend is not None

        def waiting(holder: str) -> None:
            message = f"waiting for the heavy-model lock ({holder})"
            on_warning(message)

        run = transcribe_clips(jobs, backend=backend, model=config.asr.model, on_wait=waiting)
        speech = {r.id: r for r in run.results}

    faces = _faces(project, stale, on_warning=on_warning, warnings=warnings) if talk else {}
    for c in stale:
        analysis = _clip_analysis(project, c, speech.get(c.id))
        analysis = _with_visuals(project, c, analysis, faces.get(c.id))
        if c.role == "screen":
            analysis = _with_markers(project, c, analysis, warnings)
        path = analysis_path(project, c.id)
        path.write_text(analysis.model_dump_json(indent=2) + "\n", encoding="utf-8")
        mark_done(
            project,
            f"{STAGE}.{c.id}",
            _clip_inputs(project, c),
            outputs=[path],
            params=_clip_params(c, params),
        )
    if talk:
        media = _finalise_roles(project, media)

    analyses: list[ClipAnalysis] = []
    for c in media:
        if not analysis_path(project, c.id).exists():
            warnings.append(f"{c.id} is not analysed yet; run `{APP_NAME} analyze {project.slug}`")
            continue
        loaded = load_analysis(project, c.id)
        if loaded.clip.role != c.role:
            loaded = loaded.model_copy(
                update={"clip": loaded.clip.model_copy(update={"role": c.role})}
            )
            analysis_path(project, c.id).write_text(
                loaded.model_dump_json(indent=2) + "\n", encoding="utf-8"
            )
        analyses.append(loaded)
    for message in warnings:
        on_warning(message)

    report = _report(project, kind, media, analyses, {c.id for c in stale}, configured)
    if only is None:
        mark_done(
            project,
            STAGE,
            stage_inputs,
            outputs=[
                *outputs,
                *(analysis_path(project, c.id) for c in media),
                *(project.asset_sheet(a.clip.id) for a in analyses if _is_asset(a)),
            ],
            params=params,
        )
    if run is not None:
        report.backend, report.model = run.backend, run.model
        report.worker_pid, report.worker_peak_rss_mb = run.worker_pid, run.worker_peak_rss_mb
    report.warnings = warnings
    return report


def _report(
    project: ProjectPaths,
    kind: ProjectKind,
    media: list[ClipMedia],
    analyses: list[ClipAnalysis],
    analysed: set[str],
    configured: str,
    *,
    noop: bool = False,
) -> AnalyzeReport:
    talk = kind is ProjectKind.TALK
    language = project_language(analyses, configured)
    retakes = find_retakes(analyses) if talk else Retakes(threshold=0)
    retakes_path = project.analysis / RETAKES
    packed_path = project.analysis / PACKED
    assets_path = project.analysis / ASSETS
    sheets_written: list[Path] = []
    if not noop:
        title = project_title(project)
        if talk:
            retakes_path.write_text(retakes.model_dump_json(indent=2) + "\n", encoding="utf-8")
            packed = pack_project(title, language, analyses, retakes)
        else:
            packed = pack_screen_project(title, analyses)
        packed_path.write_text(packed, encoding="utf-8")
        old = assets_path.read_text(encoding="utf-8") if assets_path.exists() else ""
        sheets = {
            a.clip.id: project.asset_sheet(a.clip.id).relative_to(project.root).as_posix()
            for a in analyses
        }
        assets_path.write_text(
            pack_assets(
                project_title(project), analyses, descriptions=read_descriptions(old), sheets=sheets
            ),
            encoding="utf-8",
        )
        clips = {c.id: c for c in media}
        for a in analyses:
            sheet = project.asset_sheet(a.clip.id)
            if _is_asset(a) and (a.clip.id in analysed or not sheet.exists()):
                sheets_written.append(write_asset_sheet(project, clips[a.clip.id], a))
    roles = {c.id: c.role for c in media}
    return AnalyzeReport(
        project=project,
        language=language,
        language_source="config" if configured != "auto" else "majority of A-roll speech",
        clips=[
            ClipSummary(
                id=a.clip.id,
                role=roles.get(a.clip.id, a.clip.role),
                language=a.language.code if a.language else None,
                confidence=a.language.confidence if a.language else None,
                words=len(a.words),
                utterances=len(a.utterances),
                path=analysis_path(project, a.clip.id),
                analysed=a.clip.id in analysed,
                markers=len(a.markers),
            )
            for a in analyses
        ],
        retake_clusters=len(retakes.clusters),
        packed=packed_path,
        retakes=retakes_path if talk else None,
        assets=assets_path,
        sheets=sheets_written,
        noop=noop,
    )


def _is_asset(analysis: ClipAnalysis) -> bool:
    return analysis.clip.role in ("broll", "image")


def _clip_params(clip: ClipMedia, params: dict[str, Any]) -> dict[str, Any]:
    return {**params, "kind": clip.kind}


def _clip_inputs(project: ProjectPaths, clip: ClipMedia) -> list[Path]:
    inputs = [project.root / clip.mezzanine]
    if clip.role == "screen":
        inputs.append(markers_sidecar(project, clip.source))
    return [*inputs, project.root / clip.audio_16k] if clip.audio_16k else inputs


def _clip_fresh(project: ProjectPaths, clip: ClipMedia, params: dict[str, Any]) -> bool:
    return stage_is_fresh(
        project,
        f"{STAGE}.{clip.id}",
        _clip_inputs(project, clip),
        params=_clip_params(clip, params),
    )


def _faces(
    project: ProjectPaths,
    clips: list[ClipMedia],
    *,
    on_warning: Callable[[str], None],
    warnings: list[str],
) -> dict[str, FaceResult]:
    if not clips:
        return {}
    jobs = [
        FaceJob(
            id=c.id,
            path=project.root / c.mezzanine,
            kind=c.kind,
            duration_s=c.duration_s or 0.0,
            width=c.width,
            height=c.height,
        )
        for c in clips
    ]

    def waiting(holder: str) -> None:
        on_warning(f"waiting for the heavy-model lock ({holder})")

    run = detect_faces(jobs, on_wait=waiting)
    if run.fallback_reason is not None:
        message = f"face detection fell back to YuNet: {run.fallback_reason}"
        record_warning(project, STAGE, message)
        warnings.append(message)
    return {r.id: r for r in run.results}


def _with_visuals(
    project: ProjectPaths, clip: ClipMedia, analysis: ClipAnalysis, faces: FaceResult | None
) -> ClipAnalysis:
    update: dict[str, Any] = {"faces": Faces(samples=faces.samples if faces else [])}
    if clip.kind == "video" and clip.duration_s:
        video = project.root / clip.mezzanine
        diffs = frame_differences(video, clip.width, clip.height)
        update["static"] = find_static(
            diffs, MOTION_FPS, vad=analysis.vad, duration_s=clip.duration_s
        )
        update["shots"] = find_shots(video, clip.duration_s)
    return analysis.model_copy(update=update)


def _with_markers(
    project: ProjectPaths, clip: ClipMedia, analysis: ClipAnalysis, warnings: list[str]
) -> ClipAnalysis:
    """Read the clip's markers sidecar, if any, with its boxes scaled to the mezzanine."""
    path = markers_sidecar(project, clip.source)
    if not path.is_file():
        return analysis
    hint = (
        "give width and height of the recorded frame, and each marker a unique name "
        "(letters, digits, _ or -) and a time t in seconds; or delete the file"
    )
    try:
        sidecar = ScreenMarkers.model_validate_json(path.read_text(encoding="utf-8"))
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in e['loc']) or 'file'}: {e['msg']}" for e in exc.errors()
        )
        raise UserError(f"{path}: {problems}", hint=hint) from exc
    sx, sy = clip.width / sidecar.width, clip.height / sidecar.height
    if abs(sx - sy) > 0.01 * max(sx, sy):
        raise UserError(
            f"{path}: the boxes are in a {sidecar.width}x{sidecar.height} frame, but "
            f"{clip.id} is {clip.width}x{clip.height}",
            hint="set width and height to the size the clip was recorded at",
        )
    markers = [
        m.model_copy(
            update={
                "elements": [
                    e.model_copy(
                        update={
                            "x": round(e.x * sx, 2),
                            "y": round(e.y * sy, 2),
                            "w": round(e.w * sx, 2),
                            "h": round(e.h * sy, 2),
                        }
                    )
                    for e in m.elements
                ]
            }
        )
        for m in sorted(sidecar.markers, key=lambda m: m.t)
    ]
    duration = clip.duration_s or 0.0
    late = [m.name for m in markers if m.t > duration]
    if late:
        warnings.append(
            f"{clip.id}: marker {', '.join(late)} is after the clip's end ({duration:.2f} s)"
        )
    cursor = [
        c.model_copy(update={"x": round(c.x * sx, 2), "y": round(c.y * sy, 2)})
        for c in sidecar.cursor
    ]
    return analysis.model_copy(
        update={
            "markers_source": path.relative_to(project.root).as_posix(),
            "markers": markers,
            "cursor": cursor,
        }
    )


def _finalise_roles(project: ProjectPaths, media: list[ClipMedia]) -> list[ClipMedia]:
    """Store each analysed clip's classification; project.toml keeps creator overrides."""
    entries = load_clips(project)
    for c in media:
        path = analysis_path(project, c.id)
        if not path.exists():
            continue
        role = finalise_role(load_analysis(project, c.id), kind=c.kind)
        if entries[c.id].auto_role != role:
            entries[c.id] = record_auto_role(project, c.id, role)
    return [c.model_copy(update={"role": entries[c.id].role}) for c in media]


def _job(project: ProjectPaths, clip: ClipMedia, configured: str) -> SpeechJob:
    assert clip.audio_16k is not None
    codes = lang.available_languages()
    return SpeechJob(
        id=clip.id,
        wav=project.root / clip.audio_16k,
        language=None if configured == "auto" else configured,
        candidates=codes,
        prompts={code: lang.load_language(code).asr.initial_prompt for code in codes},
    )


def _clip_info(clip: ClipMedia) -> ClipInfo:
    return ClipInfo(
        id=clip.id,
        role=clip.role,
        source=clip.source,
        mezzanine=clip.mezzanine,
        audio=clip.audio,
        duration_s=clip.duration_s or 0.0,
        fps=clip.fps,
        width=clip.width,
        height=clip.height,
    )


def _clip_analysis(
    project: ProjectPaths, clip: ClipMedia, speech: SpeechResult | None
) -> ClipAnalysis:
    info = _clip_info(clip)
    if speech is None:
        return ClipAnalysis(clip=info)
    if speech.language is None:
        return ClipAnalysis(clip=info, vad=speech.vad)
    return analyse_transcript(
        info,
        speech.words,
        speech.vad,
        lang.load_language(speech.language.code),
        confidence=speech.language.confidence,
    )


def project_title(project: ProjectPaths) -> str:
    """The `[project] title` from project.toml, or the slug."""
    data = tomllib.loads(project.project_toml.read_text(encoding="utf-8"))
    title = data.get("project", {}).get("title")
    return title if isinstance(title, str) and title else project.slug


def _lang_data_hash() -> str:
    digest = hashlib.sha256()
    for code in lang.available_languages():
        digest.update((lang.LANG_DIR / f"{code}.toml").read_bytes())
    return digest.hexdigest()[:16]
