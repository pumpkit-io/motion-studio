"""`agents sync`: reinstall the skills where each host agent looks for them."""

from typing import Annotated

import typer

from motion_studio.agents import TARGETS, parse_targets, sync_skills
from motion_studio.cli._output import JsonOption, emit
from motion_studio.migrate import migrate_workspace, remove_old_skills
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
    """Copy the current skills into the workspace for each agent (run after an upgrade).

    Also migrates a workspace from before the rename: the old toml, AGENTS.md and skill folders.
    """
    chosen = parse_targets(targets)
    workspace = find_workspace(unmigrated=True)
    migration = migrate_workspace(workspace)
    written = sync_skills(workspace, chosen)
    removed = remove_old_skills(workspace)
    agents_md = migration.agents_md
    emit(
        as_json,
        {
            "workspace": str(workspace),
            "targets": chosen,
            "renamed": [{"from": str(a), "to": str(b)} for a, b in migration.renamed],
            "agents_md": None
            if agents_md is None
            else {"path": str(agents_md.path), "rewritten": agents_md.rewritten},
            "removed": [str(p) for p in removed],
            "written": [str(p) for p in written],
        },
        [
            *(f"renamed {a} -> {b}" for a, b in migration.renamed),
            *([agents_md.line] if agents_md else []),
            *(f"removed {p}" for p in removed),
            f"skills for {', '.join(chosen)}",
            *(f"  wrote {p}" for p in written),
        ],
    )
