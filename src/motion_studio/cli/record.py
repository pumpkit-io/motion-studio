"""`record web`: turn a recording script into a screen recording in raw/."""

import re
from pathlib import Path
from typing import Annotated

import typer

from motion_studio import APP_NAME
from motion_studio.cli._output import JsonOption, Reporter, emit, path_line
from motion_studio.cli.workspace import Slug
from motion_studio.errors import UserError
from motion_studio.paths import find_workspace

app = typer.Typer(help="Record screen footage into a product project.", no_args_is_help=True)


def _viewport(value: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d+)x(\d+)", value)
    if match is None or int(match[1]) < 320 or int(match[2]) < 240:
        raise UserError(
            f"--viewport {value!r} is not WIDTHxHEIGHT", hint="e.g. --viewport 1600x900"
        )
    return int(match[1]), int(match[2])


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

    size = _viewport(viewport)
    with Reporter(as_json) as reporter:
        take = record_web(
            find_workspace(), slug, script, name=name, viewport=size, on_step=reporter.step
        )
    marks = ", ".join(take.markers) if take.markers else "none"
    emit(
        as_json,
        take.to_json(),
        [
            f"recorded {take.duration_s:.1f} s at {take.width}x{take.height}, {take.fps} fps "
            f"from {take.frames} frames",
            f"  markers: {marks}",
            path_line(take.clip),
            path_line(take.sidecar),
            f"next: `{APP_NAME} ingest {slug}`",
        ],
    )
