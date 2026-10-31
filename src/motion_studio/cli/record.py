"""`record web` and `record terminal`: turn a script or a tape into a screen recording in raw/."""

import re
from pathlib import Path
from typing import Annotated

import typer

from motion_studio import APP_NAME
from motion_studio.cli._output import JsonOption, Reporter, emit, path_line
from motion_studio.cli.workspace import Slug
from motion_studio.errors import UserError
from motion_studio.paths import find_workspace
from motion_studio.record.take import Take

app = typer.Typer(help="Record screen footage into a product project.", no_args_is_help=True)


def _size(option: str, value: str, *, even: bool = False) -> tuple[int, int]:
    match = re.fullmatch(r"(\d+)x(\d+)", value)
    if match is None:
        raise UserError(f"{option} {value!r} is not WIDTHxHEIGHT", hint=f"e.g. {option} 1600x900")
    width, height = int(match[1]), int(match[2])
    if width < 320 or height < 240:
        raise UserError(
            f"{option} {value!r} is smaller than 320x240", hint=f"e.g. {option} 1600x900"
        )
    if even and (width % 2 or height % 2):
        raise UserError(
            f"{option} {value!r} must be even on both sides", hint=f"e.g. {option} 1600x900"
        )
    return width, height


def _take_lines(take: Take, slug: str) -> list[str]:
    marks = ", ".join(take.markers) if take.markers else "none"
    return [
        *(f"warning: {w}" for w in take.warnings),
        f"recorded {take.duration_s:.1f} s at {take.width}x{take.height}, {take.fps} fps "
        f"({take.frames} frames)",
        f"  markers: {marks}",
        path_line(take.clip),
        path_line(take.sidecar),
        f"next: `{APP_NAME} ingest {slug}`",
    ]


@app.command("web")
def web_command(
    slug: Slug,
    script: Annotated[Path, typer.Argument(help="Recording script: an ES module (.mjs).")],
    name: Annotated[
        str | None,
        typer.Option("--name", help="Clip name in raw/; defaults to the script's file name."),
    ] = None,
    viewport: Annotated[
        str, typer.Option("--viewport", help="Browser viewport, WIDTHxHEIGHT.")
    ] = "1600x900",
    as_json: JsonOption = False,
) -> None:
    """Run a recording script in headless Chromium; write raw/<name>.mp4 and its markers."""
    from motion_studio.record.web import record_web

    size = _size("--viewport", viewport)
    with Reporter(as_json) as reporter:
        take = record_web(
            find_workspace(), slug, script, name=name, viewport=size, on_step=reporter.step
        )
    emit(as_json, take.to_json(), _take_lines(take, slug))


@app.command("terminal")
def terminal_command(
    slug: Slug,
    tape: Annotated[Path, typer.Argument(help="vhs tape (.tape), with Launch and Mark lines.")],
    name: Annotated[
        str | None,
        typer.Option("--name", help="Clip name in raw/; defaults to the tape's file name."),
    ] = None,
    size: Annotated[
        str, typer.Option("--size", help="Terminal frame, WIDTHxHEIGHT, both even.")
    ] = "1600x900",
    cwd: Annotated[
        Path | None,
        typer.Option("--cwd", help="Folder the shell starts in; defaults to the tape's folder."),
    ] = None,
    as_json: JsonOption = False,
) -> None:
    """Run a vhs tape in a clean shell; write raw/<name>.mp4 and its markers."""
    from motion_studio.record.terminal import record_terminal

    frame = _size("--size", size, even=True)
    with Reporter(as_json) as reporter:
        take = record_terminal(
            find_workspace(), slug, tape, name=name, size=frame, cwd=cwd, on_step=reporter.step
        )
    emit(as_json, take.to_json(), _take_lines(take, slug))
