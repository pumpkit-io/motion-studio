"""The plan stage: draft `edl.json`, resolve it to `build/timeline.json`, and list words.

The EDL logic itself is pure and lives in `motion_studio.edl`; this module reads and writes the
project's files around it.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from motion_studio import APP_NAME
from motion_studio.analysis import (
    ClipAnalysis,
    Retakes,
    Utterance,
    Word,
    find_retakes,
    project_language,
)
from motion_studio.analyze import RETAKES, project_title
from motion_studio.brand import load_brand_assets
from motion_studio.config import load_config
from motion_studio.edl import (
    Edl,
    EdlError,
    Issue,
    Resolution,
    draft,
    parse_edl,
    resolve,
    summarize,
)
from motion_studio.edl.grid import DEFAULT_BEATS_PER_BAR
from motion_studio.edl.issues import Problems
from motion_studio.edl.models import ProductEdl, TalkEdl
from motion_studio.edl.refs import RefIndex
from motion_studio.edl.summary import ProductSummary, Summary
from motion_studio.errors import UserError
from motion_studio.kind import ProjectKind, require_kind
from motion_studio.paths import ProjectPaths, project_paths
from motion_studio.state import mark_done, mark_failed, project_lock

STAGE = "plan"
TIMELINE = "timeline.json"
# Written by the music stage; its `beats` are output seconds that B-roll and image starts snap
# to, and that product scenes are laid on.
MUSIC_JSON = "music.json"

_CLIP_FILE = re.compile(r"(?P<kind>[cbi])(?P<n>[1-9][0-9]*)\.json")


@dataclass
class DraftReport:
    edl_path: Path
    edl: TalkEdl

    def to_json(self) -> dict[str, Any]:
        return {
            "edl": str(self.edl_path),
            "segments": len(self.edl.segments),
            "language": self.edl.language,
            "music": self.edl.music.model_dump(exclude_none=True),
        }


@dataclass
class ValidateReport:
    summary: Summary | ProductSummary
    timeline_path: Path


def timeline_path(project: ProjectPaths) -> Path:
    return project.build / TIMELINE


def load_analyses(project: ProjectPaths) -> list[ClipAnalysis]:
    """Every `analysis/<clip>.json`, in clip ID order (A-roll, then B-roll, then images)."""
    found: list[tuple[tuple[int, int], Path]] = []
    if project.analysis.is_dir():
        for path in project.analysis.iterdir():
            match = _CLIP_FILE.fullmatch(path.name)
            if match:
                found.append((("cbi".index(match["kind"]), int(match["n"])), path))
    if not found:
        raise UserError(
            f"{project.slug!r} has no analysis", hint=f"run `{APP_NAME} analyze {project.slug}`"
        )
    return [
        ClipAnalysis.model_validate_json(path.read_text(encoding="utf-8"))
        for _, path in sorted(found)
    ]


def load_edl(project: ProjectPaths) -> Edl:
    """Read and schema-check `edl.json`. Raises EdlError naming each invalid field."""
    if not project.edl.exists():
        raise UserError(
            f"{project.edl} does not exist",
            hint=f"run `{APP_NAME} plan draft {project.slug}` for a baseline to refine",
        )
    try:
        data = json.loads(project.edl.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise UserError(f"{project.edl} is not valid JSON: {exc}") from exc
    return parse_edl(data)


def resolve_project(workspace: Path, slug: str) -> tuple[Edl, Resolution]:
    """Resolve the project's EDL without writing anything. Raises EdlError on any error."""
    project = project_paths(workspace, slug).require()
    edl = load_edl(project)
    config = load_config(workspace, slug)
    beats, beats_per_bar = _beat_grid(project)
    brand = load_brand_assets(workspace, config.brand) if isinstance(edl, ProductEdl) else None
    resolution = resolve(
        load_analyses(project), edl, config, beats, beats_per_bar=beats_per_bar, brand=brand
    )
    return edl, resolution


def draft_project(workspace: Path, slug: str, *, force: bool = False) -> DraftReport:
    project = project_paths(workspace, slug).require()
    with project_lock(project):
        if project.edl.exists() and not force:
            raise UserError(
                f"{project.edl} already exists; the draft would replace your edits",
                hint=f"edit it and run `{APP_NAME} plan validate {slug}`, "
                f"or pass --force to start over",
            )
        analyses = load_analyses(project)
        configured = load_config(workspace, slug).defaults.language
        edl = draft(
            analyses,
            _retakes(project, analyses),
            title=project_title(project),
            language=project_language(analyses, configured),
        )
        project.edl.write_text(
            json.dumps(edl.model_dump(by_alias=True), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return DraftReport(edl_path=project.edl, edl=edl)


def validate_project(workspace: Path, slug: str) -> ValidateReport:
    """Resolve `edl.json` and write `build/timeline.json`. Raises EdlError on any error."""
    project = project_paths(workspace, slug).require()
    with project_lock(project):
        try:
            edl, resolution = resolve_project(workspace, slug)
        except UserError as exc:
            mark_failed(project, STAGE, exc.message)
            raise
        out = timeline_path(project)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(resolution.timeline.model_dump_json(indent=2) + "\n", encoding="utf-8")
        summary = summarize(edl, resolution, load_config(workspace, slug), str(out))
        mark_done(
            project,
            STAGE,
            [project.edl, project.analysis, project.project_toml],
            outputs=[out],
            warnings=[w.message for w in resolution.warnings],
        )
    return ValidateReport(summary=summary, timeline_path=out)


def word_range(
    workspace: Path, slug: str, start: str, end: str | None = None
) -> tuple[list[Word], list[Utterance]]:
    """The words from `start` to `end` (or just `start`), and the utterances they belong to.

    Both ends are word or utterance IDs in one clip; an utterance end means its last word.
    """
    project = project_paths(workspace, slug).require()
    require_kind(
        project,
        ProjectKind.TALK,
        "words",
        hint="screen recordings have no transcript: address them by the markers in "
        "analysis/packed.md",
    )
    index = RefIndex(load_analyses(project))
    problems = Problems()
    first = index.word_index(start, "words", problems, end="first")
    last = index.word_index(end or start, "words", problems, end="last")
    problems.raise_errors()
    assert first is not None and last is not None
    if first[0] != last[0]:
        raise EdlError(
            [Issue(code="cross_clip", message=f"words: {start} and {end} are in different clips")]
        )
    if first[1] > last[1]:
        raise EdlError(
            [
                Issue(
                    code="reversed_range",
                    message=f"words: {start} comes after {end}",
                    hint="swap the two",
                )
            ]
        )
    analysis = index.clips[first[0]]
    words = analysis.words[first[1] : last[1] + 1]
    touched = {w.utt for w in words}
    return words, [u for u in analysis.utterances if u.id in touched]


def _retakes(project: ProjectPaths, analyses: list[ClipAnalysis]) -> Retakes:
    path = project.analysis / RETAKES
    if path.exists():
        return Retakes.model_validate_json(path.read_text(encoding="utf-8"))
    return find_retakes(analyses)


def _beat_grid(project: ProjectPaths) -> tuple[list[float] | None, int]:
    """The bed's beat times and beats per bar, from music.json when the bed exists."""
    path = project.build / MUSIC_JSON
    if not path.exists():
        return None, DEFAULT_BEATS_PER_BAR
    data = json.loads(path.read_text(encoding="utf-8"))
    beats = data.get("beats")
    per_bar = data.get("beats_per_bar")
    return (
        [float(b) for b in beats] if isinstance(beats, list) else None,
        per_bar if isinstance(per_bar, int) and per_bar > 0 else DEFAULT_BEATS_PER_BAR,
    )
