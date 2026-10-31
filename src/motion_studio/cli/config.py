"""`config show`: print the effective merged config."""

from typing import Annotated

import tomli_w
import typer

from motion_studio.cli._output import JsonOption, emit
from motion_studio.config import load_config
from motion_studio.paths import find_workspace, project_paths
from motion_studio.workspace import read_edl_policy

app = typer.Typer(help="Inspect the effective config.", no_args_is_help=True)


@app.command()
def show(
    slug: Annotated[
        str | None, typer.Argument(help="Project slug; omit for the workspace level only.")
    ] = None,
    as_json: JsonOption = False,
) -> None:
    """Print defaults < motion-studio.toml < project.toml < EDL policy, merged."""
    workspace = find_workspace()
    policy = read_edl_policy(project_paths(workspace, slug).require()) if slug else None
    config = load_config(workspace, slug, edl_policy=policy)
    data = config.model_dump(mode="json")
    # Config sections sit at the top level next to `ok`, so a host agent reads `edit.pad_in_ms`.
    emit(as_json, data, [tomli_w.dumps(data).rstrip()])
