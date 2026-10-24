"""`reelcut check`: QA a preview or final render before it is delivered."""

from typing import Annotated

import typer

from reelcut import APP_NAME
from reelcut.check import check_project
from reelcut.cli._output import JsonOption, emit
from reelcut.cli.workspace import Slug
from reelcut.errors import UserError
from reelcut.paths import find_workspace

SHOWN_ISSUES = 10


def check(
    slug: Slug,
    preview: Annotated[
        bool, typer.Option("--preview", help="Check the preview render (the default).")
    ] = False,
    final: Annotated[bool, typer.Option("--final", help="Check the final render.")] = False,
    as_json: JsonOption = False,
) -> None:
    """Re-transcribe, measure and look at a render; exit 1 when anything blocks delivery."""
    if preview and final:
        raise UserError("pass --preview or --final, not both")

    def step(message: str) -> None:
        if not as_json:
            typer.echo(f"{message} ...", err=True)

    def warn(message: str) -> None:
        if not as_json:
            typer.echo(f"warning: {message}", err=True)

    report = check_project(find_workspace(), slug, final=final, on_step=step, on_warning=warn)
    body = report.to_json()
    lines = [body["summary"]]
    blocking = [f for f in report.findings if f.severity == "blocking"]
    lines += [f"  ✗ {f.line()}" for f in blocking[:SHOWN_ISSUES]]
    if len(blocking) > SHOWN_ISSUES:
        lines.append(f"  (and {len(blocking) - SHOWN_ISSUES} more in the report)")
    warnings = sum(f.severity == "warning" for f in report.findings)
    infos = sum(f.severity == "info" for f in report.findings)
    lines.append(f"{warnings} warnings, {infos} notes; metrics in the report")
    lines.append(f"wrote {report.report}")
    lines.append(f"wrote {report.cuts_sheet} (look at it once per loop)")
    if report.blocked:
        lines.append(
            f"next: edit edl.json, then `{APP_NAME} plan validate {slug}` and render again"
        )
    elif not final:
        lines.append(f"next: `{APP_NAME} render {slug} --final`")
    emit(as_json, body, lines, ok=not report.blocked)
    if report.blocked:
        raise typer.Exit(1)


def register(app: typer.Typer) -> None:
    app.command()(check)
