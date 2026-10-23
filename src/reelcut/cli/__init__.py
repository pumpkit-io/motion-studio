"""The Typer app behind the console script; one module per command group joins it here."""

from typing import Annotated

import typer

from reelcut import APP_NAME, __version__

app = typer.Typer(
    name=APP_NAME,
    help=f"{APP_NAME}: turn talking-head footage into finished short videos, driven by an agent.",
    no_args_is_help=True,
    add_completion=False,
)


def _print_version(value: bool) -> None:
    if value:
        typer.echo(f"{APP_NAME} {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_print_version,
            is_eager=True,
            help="Print the version and exit.",
        ),
    ] = False,
) -> None:
    """Edit talking-head footage into short videos from an EDL the host agent writes."""
