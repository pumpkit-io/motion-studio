"""The Typer app behind the console script; one module per command group joins it here."""

import os
import sys
import traceback
from collections.abc import Sequence
from typing import Annotated, Any

import typer

# Typer 0.27 vendors Click; its exceptions are only reachable through this private module.
from typer._click import exceptions as click
from typer.core import TyperGroup

from motion_studio import APP_NAME, ENV_PREFIX, __version__
from motion_studio.cli._output import emit_error
from motion_studio.errors import InternalError, MotionStudioError
from motion_studio.migrate import old_env_warnings

DEBUG_ENV = f"{ENV_PREFIX}_DEBUG"


class _Group(TyperGroup):
    """Maps every failure onto the exit codes 0 to 3 that host agents branch on.

    Click's own usage errors exit 2, which motion-studio reserves for a missing dependency.
    """

    def main(
        self,
        args: Sequence[str] | None = None,
        prog_name: str | None = None,
        complete_var: str | None = None,
        standalone_mode: bool = True,
        windows_expand_args: bool = True,
        **extra: Any,
    ) -> Any:
        argv = list(sys.argv[1:] if args is None else args)
        as_json = "--json" in argv
        for warning in old_env_warnings():
            typer.echo(f"warning: {warning}", err=True)
        try:
            code = super().main(argv, prog_name, complete_var, False, windows_expand_args, **extra)
        except click.UsageError as exc:
            exc.show()
            sys.exit(1)
        except click.ClickException as exc:
            exc.show()
            sys.exit(exc.exit_code)
        except typer.Abort:
            typer.echo("Aborted.", err=True)
            sys.exit(1)
        except MotionStudioError as exc:
            emit_error(as_json, exc)
            sys.exit(exc.exit_code)
        except Exception as exc:
            if os.environ.get(DEBUG_ENV):
                traceback.print_exc()
            emit_error(
                as_json,
                InternalError(
                    f"{type(exc).__name__}: {exc}",
                    hint=f"rerun with {DEBUG_ENV}=1 for the traceback",
                ),
            )
            sys.exit(InternalError.exit_code)
        sys.exit(code if isinstance(code, int) else 0)


app = typer.Typer(
    name=APP_NAME,
    cls=_Group,
    help=(
        f"{APP_NAME}: edit video with a coding agent, from talking-head videos for Reels and X"
        " to product videos made from screen recordings."
    ),
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
    """Edit talking-head videos and product videos from an EDL the host agent writes."""


def _register() -> None:
    from motion_studio.cli import (
        agents,
        analyze,
        check,
        config,
        docs,
        doctor,
        ingest,
        look,
        music,
        plan,
        record,
        render,
        setup,
        words,
        workspace,
    )

    workspace.register(app)
    ingest.register(app)
    analyze.register(app)
    words.register(app)
    look.register(app)
    app.add_typer(plan.app, name="plan")
    app.add_typer(record.app, name="record")
    music.register(app)
    app.add_typer(docs.app, name="docs")
    app.add_typer(agents.app, name="agents")
    app.add_typer(config.app, name="config")
    render.register(app)
    check.register(app)
    doctor.register(app)
    setup.register(app)


_register()
