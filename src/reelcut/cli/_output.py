"""Shared CLI conventions: the `--json` and target options, and how output is printed."""

import json
from collections.abc import Iterable
from typing import Annotated, Any

import typer

from reelcut.errors import ReelcutError, UserError
from reelcut.target import RenderTarget

JsonOption = Annotated[bool, typer.Option("--json", help="Print machine-readable JSON.")]
PreviewOption = Annotated[
    bool, typer.Option("--preview", help="The half-resolution preview in preview/ (the default).")
]
FinalOption = Annotated[bool, typer.Option("--final", help="The full-resolution final in final/.")]


def pick_target(*, preview: bool, final: bool) -> RenderTarget:
    if preview and final:
        raise UserError("pass --preview or --final, not both")
    return RenderTarget.from_flags(final=final)


class Reporter:
    """Progress and warnings on stderr while a command runs; silent under `--json`."""

    def __init__(self, as_json: bool) -> None:
        self.quiet = as_json

    def step(self, message: str) -> None:
        if not self.quiet:
            typer.echo(f"{message} ...", err=True)

    def warn(self, message: str) -> None:
        if not self.quiet:
            typer.echo(f"warning: {message}", err=True)


def emit(as_json: bool, payload: dict[str, Any], lines: Iterable[str], *, ok: bool = True) -> None:
    """Print `payload` as JSON, or the short human `lines`; JSON always carries `ok`."""
    if as_json:
        typer.echo(json.dumps({"ok": ok, **payload}, indent=2, ensure_ascii=False, default=str))
    else:
        for line in lines:
            typer.echo(line)


def path_line(path: object, detail: str = "", written: bool = True) -> str:
    """Every command names its files the same way: `wrote <path> (detail)`, or `unchanged`."""
    verb = "wrote" if written else "unchanged"
    return f"{verb} {path} ({detail})" if detail else f"{verb} {path}"


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
