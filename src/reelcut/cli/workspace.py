"""Workspace and project commands: init, new, status, clean."""

from pathlib import Path
from typing import Annotated

import typer

from reelcut import APP_NAME
from reelcut.cli._output import JsonOption, emit, path_line
from reelcut.errors import UserError
from reelcut.paths import find_workspace, project_paths
from reelcut.workspace import clean_project, init_workspace, new_project, project_status

Slug = Annotated[str, typer.Argument(help="Project slug: lowercase letters, digits, hyphens.")]


def init(
    directory: Annotated[Path, typer.Argument(help="Directory to turn into a workspace.")],
    as_json: JsonOption = False,
) -> None:
    """Create a workspace: AGENTS.md, CLAUDE.md, reelcut.toml, library/ and projects/."""
    written = init_workspace(directory)
    root = directory.expanduser().resolve()
    emit(
        as_json,
        {"workspace": str(root), "written": [str(p) for p in written]},
        [
            f"workspace {root}",
            *(path_line(p) for p in written),
            f"next: cd {root} and run `{APP_NAME} new <slug> --from <files>`",
        ],
    )


def new(
    slug: Slug,
    more: Annotated[
        list[Path] | None,
        typer.Argument(
            help="More files or directories, as in `--from a.mov b.mov`.", show_default=False
        ),
    ] = None,
    sources: Annotated[
        list[Path] | None,
        typer.Option("--from", help="A file or directory to put in raw/. Repeatable."),
    ] = None,
    title: Annotated[str | None, typer.Option(help="Human title; defaults to the slug.")] = None,
    as_json: JsonOption = False,
) -> None:
    """Create a project and hard-link (or copy) the given clips into its raw/ directory."""
    workspace = find_workspace()
    project, raw = new_project(workspace, slug, [*(sources or []), *(more or [])], title=title)
    hint = f"`{APP_NAME} ingest {slug}`" if raw else f"copy clips into {project.raw}"
    emit(
        as_json,
        {"project": str(project.root), "raw": [str(p) for p in raw]},
        [
            f"project {project.root}",
            *(path_line(p, "linked into raw/") for p in raw),
            f"next: {hint}",
        ],
    )


def status(slug: Slug, as_json: JsonOption = False) -> None:
    """Show each stage, which are stale, and the next command to run."""
    report = project_status(find_workspace(), slug)
    width = max(len(s.name) for s in report.stages)
    emit(
        as_json,
        report.to_json(),
        [
            f"{report.slug}: {report.clips} clip(s) in raw/",
            *(f"  {s.name.ljust(width)}  {s.status}" for s in report.stages),
            f"next: {report.next}" if report.next else f"next: {report.hint}",
        ],
    )


def clean(
    slug: Slug,
    everything: Annotated[
        bool,
        typer.Option(
            "--all",
            help="Also delete analysis, checks, final/, edl.json and notes.md (never raw/).",
        ),
    ] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Skip the confirmation for --all.")] = False,
    as_json: JsonOption = False,
) -> None:
    """Delete caches (media/, build/, preview/) to reclaim disk. raw/ is never touched."""
    project = project_paths(find_workspace(), slug).require()
    if everything and not yes:
        confirmed = typer.confirm(
            f"Delete final/, edl.json, notes.md and all analysis of {slug!r}?", default=False
        )
        if not confirmed:
            raise UserError("nothing deleted", hint="pass --yes to confirm --all")
    removed = clean_project(project, everything=everything)
    emit(
        as_json,
        {"removed": [str(p) for p in removed]},
        [f"removed {len(removed)} item(s) from {project.root}"]
        + [f"  {p}" for p in removed[:25]]
        + ([f"  ... and {len(removed) - 25} more"] if len(removed) > 25 else []),
    )


def register(app: typer.Typer) -> None:
    app.command()(init)
    app.command()(new)
    app.command()(status)
    app.command()(clean)
