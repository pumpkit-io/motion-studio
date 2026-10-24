"""`reelcut look` and `reelcut look-asset`: one PNG to make a visual decision from."""

from pathlib import Path
from typing import Annotated

import typer

from reelcut.cli._output import JsonOption, emit, path_line
from reelcut.cli.workspace import Slug
from reelcut.look import DEFAULT_FRAMES, LookReport, look_asset, look_range
from reelcut.paths import find_workspace


def look(
    slug: Slug,
    clip: Annotated[str, typer.Argument(help="Clip ID, e.g. c1.")],
    t0: Annotated[float, typer.Argument(help="Start, in source seconds.")],
    t1: Annotated[float, typer.Argument(help="End, in source seconds.")],
    frames: Annotated[int, typer.Option("--frames", help="Frames across the range.")] = (
        DEFAULT_FRAMES
    ),
    out: Annotated[
        Path | None, typer.Option("--out", help="Write the PNG here instead of contact/.")
    ] = None,
    as_json: JsonOption = False,
) -> None:
    """Draw frames, waveform, word labels and face boxes for T0 to T1 of CLIP into one PNG."""
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


def register(app: typer.Typer) -> None:
    app.command()(look)
    app.command("look-asset")(look_asset_command)
