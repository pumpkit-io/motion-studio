"""`doctor`: check the machine for everything reelcut needs."""

from pathlib import Path
from typing import Annotated

import typer

from reelcut.cli._output import JsonOption, Reporter, emit
from reelcut.doctor import fix_machine, run_doctor
from reelcut.errors import DependencyError

LABELS = {"ok": "ok     ", "warn": "warn   ", "missing": "MISSING"}


def doctor(
    fix: Annotated[
        bool,
        typer.Option(
            "--fix", help="Download what `setup` installs when it is missing, then check again."
        ),
    ] = False,
    as_json: JsonOption = False,
) -> None:
    """Check ffmpeg and its filters, node, the ASR backend, caches, free disk and RAM.

    Exits 2 when something required is missing; warnings alone exit 0.
    """
    lines: list[str] = []
    if fix:
        fixed = fix_machine(Path.cwd(), on_step=Reporter(as_json).step)
        report, payload = fixed.report, fixed.to_json()
        if not fixed.ran_setup:
            lines.append("fix: nothing to install; any other fix is printed after its check")
        lines += [f"{i.status} {i.path} ({i.name})" for i in fixed.installed]
        if fixed.error:
            lines.append(f"fix: setup stopped: {fixed.error}")
    else:
        report = run_doctor(Path.cwd())
        payload = report.to_json()
    for check in report.checks:
        line = f"{LABELS[check.status]} {check.name}: {check.detail}"
        lines.append(f"{line} (fix: {check.fix})" if check.fix else line)
    lines.append(
        "all required dependencies present" if report.ok else "required dependencies missing"
    )
    ok = payload.pop("ok")
    emit(as_json, payload, lines, ok=ok)
    if not ok:
        raise typer.Exit(DependencyError.exit_code)


def register(app: typer.Typer) -> None:
    app.command()(doctor)
