"""`agents sync`: reinstall the skills where each host agent looks for them."""

from typing import Annotated

import typer

from motion_studio.agents import TARGETS, parse_targets, sync_skills
from motion_studio.cli._output import JsonOption, emit
from motion_studio.paths import find_workspace

app = typer.Typer(help="Install the editing skills for host agents.", no_args_is_help=True)


@app.command()
def sync(
    targets: Annotated[
        str | None,
        typer.Option(
            "--targets",
            help=f"Comma-separated agents ({','.join(TARGETS)}). Default: all.",
            show_default=False,
        ),
    ] = None,
    as_json: JsonOption = False,
) -> None:
    """Copy the current skills into the workspace for each agent (run after an upgrade)."""
    chosen = parse_targets(targets)
    workspace = find_workspace()
    written = sync_skills(workspace, chosen)
    emit(
        as_json,
        {"workspace": str(workspace), "targets": chosen, "written": [str(p) for p in written]},
        [f"skills for {', '.join(chosen)}", *(f"  wrote {p}" for p in written)],
    )
