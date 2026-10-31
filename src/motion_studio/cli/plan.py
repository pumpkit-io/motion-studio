"""`plan draft` and `plan validate`: the baseline EDL, and the summary after every change."""

from typing import Annotated

import typer

from motion_studio import APP_NAME
from motion_studio.cli._output import JsonOption, emit
from motion_studio.cli.workspace import Slug
from motion_studio.edl import EdlError
from motion_studio.edl.summary import error_report
from motion_studio.paths import find_workspace
from motion_studio.plan import ProductDraftReport, draft_project, validate_project

app = typer.Typer(help="Draft and validate the EDL.", no_args_is_help=True)


@app.command("draft")
def draft_command(
    slug: Slug,
    force: Annotated[bool, typer.Option("--force", help="Replace an existing edl.json.")] = False,
    as_json: JsonOption = False,
) -> None:
    """Write a deterministic baseline edl.json: all usable speech, or a scene per recording."""
    report = draft_project(find_workspace(), slug, force=force)
    if isinstance(report, ProductDraftReport):
        emit(as_json, report.to_json(), _product_lines(report, slug))
        return
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


def _product_lines(report: ProductDraftReport, slug: str) -> list[str]:
    grid = report.grid
    source = "from the music" if grid.from_music else "steady (no music yet)"
    music = report.edl.music
    return [
        f"wrote {report.edl_path}",
        f"  {len(report.edl.scenes)} scenes: " + " · ".join(s.id for s in report.edl.scenes),
        f"  grid {grid.bpm:.4g} bpm, {source}",
        f"  music: generate, preset {music.preset}",
        "  rationale in edl.json says what to change first",
        f"next: write the headlines, then `{APP_NAME} plan validate {slug}`",
    ]


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
