"""The analyze stage: speech, language and transcript analysis per clip, then the packed index.

Writes `analysis/<clip>.json`, `analysis/retakes.json` and `analysis/packed.md`. Each clip has
its own state record (`analyze.<id>`), so only clips whose audio or settings changed go back
through the speech-to-text worker.
"""

import hashlib
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from reelcut import APP_NAME, lang
from reelcut.analysis import (
    ClipAnalysis,
    ClipInfo,
    analyse_transcript,
    find_retakes,
    pack_project,
    project_language,
)
from reelcut.asr import SpeechJob, SpeechResult, model_ref, resolve_backend, transcribe_clips
from reelcut.config import load_config
from reelcut.errors import UserError
from reelcut.ingest import ClipMedia, load_clips, load_manifest
from reelcut.paths import ProjectPaths, project_paths
from reelcut.state import mark_done, mark_failed, project_lock, stage_is_fresh

STAGE = "analyze"
# Bump when the analysis output changes for the same audio, so existing projects re-analyse.
RECIPE = 1

RETAKES = "retakes.json"
PACKED = "packed.md"


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


@dataclass
class AnalyzeReport:
    project: ProjectPaths
    language: str
    language_source: str
    clips: list[ClipSummary]
    retake_clusters: int
    packed: Path
    retakes: Path
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
                    "analysis": str(c.path),
                    "status": "analysed" if c.analysed else "unchanged",
                }
                for c in self.clips
            ],
            "retake_clusters": self.retake_clusters,
            "packed": str(self.packed),
            "packed_tokens": self.packed_tokens,
            "retakes": str(self.retakes),
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
    backend = resolve_backend(config.asr.backend)
    ref = model_ref(backend, config.asr.model)
    configured = config.defaults.language
    params = {
        "recipe": RECIPE,
        "backend": backend,
        "model": f"{ref.repo}@{ref.revision}",
        "language": configured,
        "lang_data": _lang_data_hash(),
    }
    manifest_path = project.media / "manifest.json"
    stage_inputs = [manifest_path, project.project_toml]
    project.analysis.mkdir(exist_ok=True)
    outputs = [project.analysis / PACKED, project.analysis / RETAKES]

    if only is None and stage_is_fresh(project, STAGE, stage_inputs, params=params):
        analyses = [load_analysis(project, c.id) for c in media]
        return _report(project, media, analyses, set(), configured, noop=True)

    stale = [
        c
        for c in media
        if (only is None or c.id == only) and (c.id == only or not _clip_fresh(project, c, params))
    ]
    jobs = [_job(project, c, configured) for c in stale if c.audio_16k]
    speech: dict[str, SpeechResult] = {}
    run = None
    warnings: list[str] = []
    if jobs:

        def waiting(holder: str) -> None:
            message = f"waiting for the heavy-model lock ({holder})"
            on_warning(message)

        run = transcribe_clips(jobs, backend=backend, model=config.asr.model, on_wait=waiting)
        speech = {r.id: r for r in run.results}

    for c in stale:
        analysis = _clip_analysis(project, c, speech.get(c.id))
        path = analysis_path(project, c.id)
        path.write_text(analysis.model_dump_json(indent=2) + "\n", encoding="utf-8")
        inputs = [project.root / c.audio_16k] if c.audio_16k else [project.root / c.mezzanine]
        mark_done(
            project, f"{STAGE}.{c.id}", inputs, outputs=[path], params=_clip_params(c, params)
        )

    analyses: list[ClipAnalysis] = []
    for c in media:
        if not analysis_path(project, c.id).exists():
            warnings.append(f"{c.id} is not analysed yet; run `{APP_NAME} analyze {project.slug}`")
            continue
        loaded = load_analysis(project, c.id)
        analyses.append(
            loaded.model_copy(update={"clip": loaded.clip.model_copy(update={"role": c.role})})
        )
    for message in warnings:
        on_warning(message)

    report = _report(project, media, analyses, {c.id for c in stale}, configured)
    if only is None:
        mark_done(
            project,
            STAGE,
            stage_inputs,
            outputs=[*outputs, *(analysis_path(project, c.id) for c in media)],
            params=params,
        )
    if run is not None:
        report.backend, report.model = run.backend, run.model
        report.worker_pid, report.worker_peak_rss_mb = run.worker_pid, run.worker_peak_rss_mb
    report.warnings = warnings
    return report


def _report(
    project: ProjectPaths,
    media: list[ClipMedia],
    analyses: list[ClipAnalysis],
    analysed: set[str],
    configured: str,
    *,
    noop: bool = False,
) -> AnalyzeReport:
    language = project_language(analyses, configured)
    retakes = find_retakes(analyses)
    retakes_path = project.analysis / RETAKES
    packed_path = project.analysis / PACKED
    if not noop:
        retakes_path.write_text(retakes.model_dump_json(indent=2) + "\n", encoding="utf-8")
        packed_path.write_text(
            pack_project(_title(project), language, analyses, retakes), encoding="utf-8"
        )
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
            )
            for a in analyses
        ],
        retake_clusters=len(retakes.clusters),
        packed=packed_path,
        retakes=retakes_path,
        noop=noop,
    )


def _clip_params(clip: ClipMedia, params: dict[str, Any]) -> dict[str, Any]:
    return {**params, "kind": clip.kind}


def _clip_fresh(project: ProjectPaths, clip: ClipMedia, params: dict[str, Any]) -> bool:
    inputs = [project.root / (clip.audio_16k or clip.mezzanine)]
    return stage_is_fresh(project, f"{STAGE}.{clip.id}", inputs, params=_clip_params(clip, params))


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


def _title(project: ProjectPaths) -> str:
    data = tomllib.loads(project.project_toml.read_text(encoding="utf-8"))
    title = data.get("project", {}).get("title")
    return title if isinstance(title, str) and title else project.slug


def _lang_data_hash() -> str:
    digest = hashlib.sha256()
    for code in lang.available_languages():
        digest.update((lang.LANG_DIR / f"{code}.toml").read_bytes())
    return digest.hexdigest()[:16]
