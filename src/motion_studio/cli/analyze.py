"""`motion-studio analyze`: transcripts, fillers, retakes, shots, faces, roles and the indexes."""

from typing import Annotated

import typer

from motion_studio import APP_NAME
from motion_studio.analyze import analyze_project
from motion_studio.cli._output import JsonOption, Reporter, emit, path_line
from motion_studio.cli.workspace import Slug
from motion_studio.paths import find_workspace


def analyze(
    slug: Slug,
    clip: Annotated[
        str | None, typer.Option("--clip", help="Re-analyse only this clip, e.g. c1.")
    ] = None,
    as_json: JsonOption = False,
) -> None:
    """Transcribe speech, find shots, static stretches and faces, and write the indexes."""
    with Reporter(as_json) as reporter:
        report = analyze_project(find_workspace(), slug, clip=clip, on_warning=reporter.warn)
    written = not report.noop
    lines = [f"{slug}: nothing changed since the last analyze"] if report.noop else []
    for c in report.clips:
        heard = f"{c.language} {c.confidence:.2f}" if c.language else "no speech"
        detail = f"{c.id} {c.role}, {heard}, {c.words} words, {c.utterances} utterances"
        lines.append(path_line(c.path, detail, written=c.analysed))
    lines.append(f"language {report.language} ({report.language_source})")
    lines.append(path_line(report.retakes, f"{report.retake_clusters} retake clusters", written))
    lines.append(path_line(report.packed, f"packed index, ~{report.packed_tokens} tokens", written))
    lines.append(path_line(report.assets, "asset catalogue", written))
    lines += [path_line(sheet, "contact sheet") for sheet in report.sheets]
    lines.append(f"next: read {report.packed.name}, then `{APP_NAME} plan draft {slug}`")
    emit(as_json, report.to_json(), lines)


def register(app: typer.Typer) -> None:
    app.command()(analyze)
