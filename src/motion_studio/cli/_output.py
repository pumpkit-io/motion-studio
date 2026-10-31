"""Shared CLI conventions: the `--json` and target options, and how output is printed."""

import json
import sys
from collections.abc import Iterable
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)

from motion_studio.errors import MotionStudioError, UserError
from motion_studio.target import RenderTarget

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
    """Progress and warnings on stderr while a command runs; silent under `--json`.

    On a terminal each step is a Rich progress line (a bar once `progress` reports a length,
    else a spinner with the elapsed time); elsewhere a step is one plain `<step> ...` line.
    Use it as a context manager so the live display stops before the result is printed.
    """

    def __init__(self, as_json: bool, *, console: Console | None = None) -> None:
        self.quiet = as_json
        live = console is not None or (sys.stdout.isatty() and sys.stderr.isatty())
        self._progress: Progress | None = None
        self._task: TaskID | None = None
        if live and not as_json:
            self._progress = Progress(
                SpinnerColumn(),
                TextColumn("{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                TimeElapsedColumn(),
                console=console or Console(stderr=True),
                transient=True,
            )

    def __enter__(self) -> "Reporter":
        if self._progress is not None:
            self._progress.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        if self._progress is not None:
            self._progress.stop()

    def step(self, message: str) -> None:
        if self.quiet:
            return
        if self._progress is None:
            typer.echo(f"{message} ...", err=True)
            return
        if self._task is not None:
            self._progress.remove_task(self._task)
        self._task = self._progress.add_task(message, total=None)

    def progress(self, done: float, total: float) -> None:
        """How far the current step is, in any unit (ffmpeg reports output seconds)."""
        if self._progress is not None and self._task is not None and total > 0:
            self._progress.update(self._task, completed=min(done, total), total=total)

    def warn(self, message: str) -> None:
        if self.quiet:
            return
        if self._progress is None:
            typer.echo(f"warning: {message}", err=True)
        else:
            self._progress.console.print(f"warning: {message}", markup=False, highlight=False)


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


def emit_error(as_json: bool, error: MotionStudioError) -> None:
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
