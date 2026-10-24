"""`reelcut ingest`: clip IDs, mezzanines and enhanced audio."""

import typer

from reelcut import APP_NAME
from reelcut.cli._output import JsonOption, Reporter, emit, path_line
from reelcut.cli.workspace import Slug
from reelcut.ingest import MANIFEST, ingest_project
from reelcut.paths import find_workspace


def ingest(slug: Slug, as_json: JsonOption = False) -> None:
    """Give each raw file a clip ID, normalise it to a CFR SDR mezzanine and clean its audio."""
    with Reporter(as_json) as reporter:
        report = ingest_project(
            find_workspace(),
            slug,
            on_warning=reporter.warn,
            on_step=reporter.step,
            on_progress=reporter.progress,
        )
    root = report.project.root
    lines = [f"{slug}: nothing changed since the last ingest"] if report.noop else []
    for clip in report.clips:
        fresh = clip.id in report.ingested
        size = f"{clip.width}x{clip.height}"
        timing = f" {clip.fps:g} fps {clip.duration_s:.1f} s" if clip.kind == "video" else ""
        detail = f"{clip.id} {clip.role} from {clip.source}, {size}{timing}"
        lines.append(path_line(root / clip.mezzanine, detail, written=fresh))
        if fresh:
            lines += [path_line(root / p) for p in (clip.audio, clip.audio_16k) if p]
    lines.append(path_line(report.project.media / MANIFEST, "manifest", written=not report.noop))
    lines.append(f"next: `{APP_NAME} analyze {slug}`")
    emit(as_json, report.to_json(), lines)


def register(app: typer.Typer) -> None:
    app.command()(ingest)
