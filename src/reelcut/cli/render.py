"""`reelcut render`: assemble, compose and mix the timeline into playable files."""

from typing import Annotated

import typer

from reelcut import APP_NAME
from reelcut.cli._output import JsonOption, emit
from reelcut.cli.workspace import Slug
from reelcut.errors import UserError
from reelcut.paths import find_workspace
from reelcut.render import DEFAULT_CONCURRENCY, render_project


def render(
    slug: Slug,
    preview: Annotated[
        bool, typer.Option("--preview", help="Half resolution into preview/ (the default).")
    ] = False,
    final: Annotated[bool, typer.Option("--final", help="Full resolution into final/.")] = False,
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
    if preview and final:
        raise UserError("pass --preview or --final, not both")

    def step(message: str) -> None:
        if not as_json:
            typer.echo(f"{message} ...", err=True)

    def warn(message: str) -> None:
        if not as_json:
            typer.echo(f"warning: {message}", err=True)

    report = render_project(
        find_workspace(),
        slug,
        final=final,
        formats=formats or (),
        concurrency=concurrency,
        on_step=step,
        on_warning=warn,
    )
    lines = [f"{slug}: {report.stage} is up to date"] if report.noop else []
    for out in report.outputs:
        lines.append(f"wrote {out.path} ({out.width}x{out.height}, {out.frames / out.fps:.2f} s)")
        lines.append(f"      voice {out.voice}")
    flag = "--final" if final else "--preview"
    lines.append(f"next: `{APP_NAME} check {slug} {flag}`")
    emit(as_json, report.to_json(), lines)


def register(app: typer.Typer) -> None:
    app.command()(render)
