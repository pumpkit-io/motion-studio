"""`reelcut analyze`: transcripts, fillers, utterances, retakes and the packed index."""

from typing import Annotated

import typer

from reelcut import APP_NAME
from reelcut.analyze import analyze_project
from reelcut.cli._output import JsonOption, emit
from reelcut.cli.workspace import Slug
from reelcut.paths import find_workspace

MAX_CLIP_LINES = 12


def analyze(
    slug: Slug,
    clip: Annotated[
        str | None, typer.Option("--clip", help="Re-analyse only this clip, e.g. c1.")
    ] = None,
    as_json: JsonOption = False,
) -> None:
    """Detect speech and language, transcribe word by word, and write analysis/packed.md."""

    def warn(message: str) -> None:
        if not as_json:
            typer.echo(f"warning: {message}", err=True)

    report = analyze_project(find_workspace(), slug, clip=clip, on_warning=warn)
    lines = [f"{slug}: nothing changed since the last analyze"] if report.noop else []
    for c in report.clips[:MAX_CLIP_LINES]:
        heard = f"{c.language} ({c.confidence:.2f})" if c.language else "no speech"
        status = "analysed" if c.analysed else "unchanged"
        lines.append(
            f"  {c.id:<4} {c.role:<6} {heard:<11} {c.words} words, "
            f"{c.utterances} utterances, {status}: {c.path}"
        )
    if len(report.clips) > MAX_CLIP_LINES:
        lines.append(
            f"  ... and {len(report.clips) - MAX_CLIP_LINES} more in {report.packed.parent}"
        )
    lines.append(f"language {report.language} ({report.language_source})")
    lines.append(f"retakes {report.retake_clusters} clusters: {report.retakes}")
    lines.append(f"packed index (~{report.packed_tokens} tokens): {report.packed}")
    lines.append(f"next: read {report.packed.name}, then `{APP_NAME} plan draft {slug}`")
    emit(as_json, report.to_json(), lines)


def register(app: typer.Typer) -> None:
    app.command()(analyze)
