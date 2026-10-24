"""`reelcut ingest`: clip IDs, mezzanines and enhanced audio."""

import typer

from reelcut import APP_NAME
from reelcut.cli._output import JsonOption, emit
from reelcut.cli.workspace import Slug
from reelcut.ingest import ingest_project
from reelcut.paths import find_workspace


def ingest(slug: Slug, as_json: JsonOption = False) -> None:
    """Give each raw file a clip ID, normalise it to a CFR SDR mezzanine and clean its audio."""

    def warn(message: str) -> None:
        if not as_json:
            typer.echo(f"warning: {message}", err=True)

    report = ingest_project(find_workspace(), slug, on_warning=warn)
    root = report.project.root
    lines = [f"{slug}: nothing changed since the last ingest"] if report.noop else []
    for clip in report.clips[:12]:
        status = "ingested" if clip.id in report.ingested else "unchanged"
        size = f"{clip.width}x{clip.height}"
        timing = f" {clip.fps:g} fps {clip.duration_s:.1f} s" if clip.kind == "video" else ""
        lines.append(f"  {clip.id:<4} {clip.role:<6} {clip.source} ({size}{timing}) {status}")
        if clip.id in report.ingested:
            written = [clip.mezzanine, clip.audio, clip.audio_16k]
            lines.append("       wrote " + ", ".join(str(root / p) for p in written if p))
    if len(report.clips) > 12:
        lines.append(f"  ... and {len(report.clips) - 12} more in {report.project.media}")
    lines.append(f"manifest {report.project.media / 'manifest.json'}")
    lines.append(f"next: `{APP_NAME} analyze {slug}`")
    emit(as_json, report.to_json(), lines)


def register(app: typer.Typer) -> None:
    app.command()(ingest)
