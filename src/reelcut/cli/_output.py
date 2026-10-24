"""Shared CLI conventions: the `--json` option and how results and errors are printed."""

import json
from collections.abc import Iterable
from typing import Annotated, Any

import typer

from reelcut.errors import ReelcutError

JsonOption = Annotated[bool, typer.Option("--json", help="Print machine-readable JSON.")]


def emit(as_json: bool, payload: dict[str, Any], lines: Iterable[str], *, ok: bool = True) -> None:
    """Print `payload` as JSON, or the short human `lines`; JSON always carries `ok`."""
    if as_json:
        typer.echo(json.dumps({"ok": ok, **payload}, indent=2, ensure_ascii=False, default=str))
    else:
        for line in lines:
            typer.echo(line)


def emit_error(as_json: bool, error: ReelcutError) -> None:
    if as_json:
        body = {
            "ok": False,
            "error": error.message,
            "hint": error.hint,
            "exit_code": error.exit_code,
        }
        typer.echo(json.dumps(body, indent=2, ensure_ascii=False))
        return
    typer.echo(f"error: {error.message}", err=True)
    if error.hint:
        typer.echo(f"hint: {error.hint}", err=True)
