"""`reelcut render`: assemble, compose and mix the timeline into playable files."""

from typing import Annotated

import typer

from reelcut import APP_NAME
from reelcut.cli._output import (
    FinalOption,
    JsonOption,
    PreviewOption,
    Reporter,
    emit,
    path_line,
    pick_target,
)
from reelcut.cli.workspace import Slug
from reelcut.paths import find_workspace
from reelcut.render import DEFAULT_CONCURRENCY, render_project


def render(
    slug: Slug,
    preview: PreviewOption = False,
    final: FinalOption = False,
    formats: Annotated[
        list[str] | None,
        typer.Option("--format", help="Render only this format (repeatable); default all."),
    ] = None,
    concurrency: Annotated[
        int, typer.Option("--concurrency", help="Frames Remotion renders in parallel.")
    ] = DEFAULT_CONCURRENCY,
    as_json: JsonOption = False,
) -> None:
    """Cut the A-roll, compose each format with Remotion, then duck music and master loudness."""
    target = pick_target(preview=preview, final=final)
    reporter = Reporter(as_json)
    report = render_project(
        find_workspace(),
        slug,
        target=target,
        formats=formats or (),
        concurrency=concurrency,
        on_step=reporter.step,
        on_warning=reporter.warn,
    )
    lines = [f"{slug}: {report.stage} is up to date"] if report.noop else []
    for out in report.outputs:
        size = f"{out.format} {out.width}x{out.height}, {out.frames / out.fps:.2f} s"
        lines.append(path_line(out.path, size, written=not report.noop))
        lines.append(path_line(out.voice, "voice stem", written=not report.noop))
    lines.append(f"next: `{APP_NAME} check {slug} {target.flag}`")
    emit(as_json, report.to_json(), lines)


def register(app: typer.Typer) -> None:
    app.command()(render)
