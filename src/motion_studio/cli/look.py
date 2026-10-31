"""`motion-studio look` and `motion-studio look-asset`: one PNG to make a visual decision from.

`look --at` writes one still per moment of the render instead.
"""

from pathlib import Path
from typing import Annotated

import typer

from motion_studio import APP_NAME
from motion_studio.cli._output import JsonOption, emit, path_line
from motion_studio.cli.workspace import Slug
from motion_studio.errors import UserError
from motion_studio.look import DEFAULT_FRAMES, LookReport, look_asset, look_range
from motion_studio.look.at import StillsReport, look_at
from motion_studio.paths import find_workspace


def look(
    slug: Slug,
    clip: Annotated[str | None, typer.Argument(help="Clip ID, e.g. c1.")] = None,
    t0: Annotated[float | None, typer.Argument(help="Start, in source seconds.")] = None,
    t1: Annotated[float | None, typer.Argument(help="End, in source seconds.")] = None,
    at: Annotated[
        list[str] | None,
        typer.Option(
            "--at",
            help="A scene ID, marker or output time of the latest render; repeat for more stills.",
        ),
    ] = None,
    frames: Annotated[int, typer.Option("--frames", help="Frames across the range.")] = (
        DEFAULT_FRAMES
    ),
    out: Annotated[
        Path | None, typer.Option("--out", help="Write the PNG here instead of contact/.")
    ] = None,
    as_json: JsonOption = False,
) -> None:
    """Draw T0 to T1 of CLIP (frames, waveform, words, faces), or stills of the render with --at."""
    if at:
        if clip is not None:
            raise UserError(
                "pass a clip range or --at, not both",
                hint="--at takes stills of the render; the range form draws a source clip",
            )
        _print_stills(look_at(find_workspace(), slug, at), as_json)
        return
    if clip is None or t0 is None or t1 is None:
        raise UserError(
            "say what to look at",
            hint=f"pass <clip> <t0> <t1> for source footage, or --at <scene | marker | time> "
            f"for the render, e.g. `{APP_NAME} look {slug} --at 12.5`",
        )
    report = look_range(find_workspace(), slug, clip, t0, t1, frames=frames, out=out)
    _print(report, as_json)


def look_asset_command(
    slug: Slug,
    asset: Annotated[str, typer.Argument(help="B-roll or image ID, e.g. b1 or i1.")],
    as_json: JsonOption = False,
) -> None:
    """Redraw the contact sheet of a B-roll clip or image into contact/<id>.png."""
    _print(look_asset(find_workspace(), slug, asset), as_json)


def _print(report: LookReport, as_json: bool) -> None:
    if not as_json:
        for message in report.warnings:
            typer.echo(f"warning: {message}", err=True)
    lines = [report.description]
    if report.look_count is not None:
        lines.append(f"look budget: {report.look_count} of {report.look_budget} sheets used")
    lines.append(path_line(report.sheet))
    emit(as_json, report.to_json(), lines)


def _print_stills(report: StillsReport, as_json: bool) -> None:
    if not as_json:
        for message in report.warnings:
            typer.echo(f"warning: {message}", err=True)
    lines = [f"{report.stage} {report.fmt}: {report.render}"]
    for still in report.stills:
        scene = f", scene {still.scene}" if still.scene else ""
        lines.append(f"{still.at}: frame {still.frame} ({still.t:.2f} s{scene})")
    lines.append(f"look budget: {report.look_count} of {report.look_budget} sheets used")
    lines += [path_line(still.path) for still in report.stills]
    emit(as_json, report.to_json(), lines)


def register(app: typer.Typer) -> None:
    app.command()(look)
    app.command("look-asset")(look_asset_command)
