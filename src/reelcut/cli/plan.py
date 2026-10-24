"""`plan draft` and `plan validate`: the baseline EDL, and the summary after every change."""

from typing import Annotated

import typer

from reelcut import APP_NAME
from reelcut.cli._output import JsonOption, emit
from reelcut.cli.workspace import Slug
from reelcut.edl import EdlError
from reelcut.edl.summary import error_report
from reelcut.paths import find_workspace
from reelcut.plan import draft_project, validate_project

app = typer.Typer(help="Draft and validate the EDL.", no_args_is_help=True)


@app.command("draft")
def draft_command(
    slug: Slug,
    force: Annotated[bool, typer.Option("--force", help="Replace an existing edl.json.")] = False,
    as_json: JsonOption = False,
) -> None:
    """Write a deterministic baseline edl.json: all usable speech in source order."""
    report = draft_project(find_workspace(), slug, force=force)
    edl = report.edl
    emit(
        as_json,
        report.to_json(),
        [
            f"wrote {report.edl_path}",
            f"  {len(edl.segments)} segments, one per kept utterance; hard fillers dropped",
            f'  music: generate at {edl.music.bpm} bpm, "{edl.music.prompt}"',
            f"next: refine it (hook first), then `{APP_NAME} plan validate {slug}`",
        ],
    )


@app.command("validate")
def validate_command(slug: Slug, as_json: JsonOption = False) -> None:
    """Resolve edl.json into build/timeline.json and print a short summary."""
    try:
        report = validate_project(find_workspace(), slug)
    except EdlError as exc:
        lines, data = error_report(exc)
        emit(
            as_json,
            {**data, "error": exc.message, "hint": exc.hint, "exit_code": exc.exit_code},
            lines,
            ok=False,
        )
        raise typer.Exit(exc.exit_code) from exc
    emit(as_json, report.summary.to_json(), report.summary.lines())
