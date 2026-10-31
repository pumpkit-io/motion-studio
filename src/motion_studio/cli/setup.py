"""`motion-studio setup`: download models and tools into the cache once."""

from pathlib import Path
from typing import Annotated

import typer

from motion_studio import APP_NAME
from motion_studio.cli._output import JsonOption, Reporter, emit
from motion_studio.setup import run_setup


def setup(
    music: Annotated[
        bool, typer.Option("--music", help="Also create the ACE-Step music environment.")
    ] = False,
    crisper: Annotated[
        bool, typer.Option("--crisper", help="CrisperWhisper fillers backend (not in v0.1.0).")
    ] = False,
    as_json: JsonOption = False,
) -> None:
    """Download the speech, voice-activity and denoiser models and the renderer, for offline use."""
    with Reporter(as_json) as reporter:
        report = run_setup(music=music, crisper=crisper, workdir=Path.cwd(), on_step=reporter.step)
    lines: list[str] = []
    for item in report.items:
        lines.append(f"{item.status} {item.path} ({item.name})")
        if item.licence:
            lines.append(f"  weights licence: {item.licence}")
    lines.append(f"next: `{APP_NAME} doctor`")
    emit(as_json, report.to_json(), lines)


def register(app: typer.Typer) -> None:
    app.command()(setup)
