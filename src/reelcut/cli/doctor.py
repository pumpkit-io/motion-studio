"""`doctor`: check the machine for everything reelcut needs."""

from pathlib import Path

import typer

from reelcut.cli._output import JsonOption, emit
from reelcut.doctor import run_doctor

LABELS = {"ok": "ok     ", "warn": "warn   ", "missing": "MISSING"}


def doctor(as_json: JsonOption = False) -> None:
    """Check ffmpeg and its filters, node, the ASR backend, caches, free disk and RAM.

    Exits 2 when something required is missing; warnings alone exit 0.
    """
    report = run_doctor(Path.cwd())
    lines = []
    for check in report.checks:
        line = f"{LABELS[check.status]} {check.name}: {check.detail}"
        lines.append(f"{line} (fix: {check.fix})" if check.fix else line)
    lines.append(
        "all required dependencies present" if report.ok else "required dependencies missing"
    )
    payload = report.to_json()
    ok = payload.pop("ok")
    emit(as_json, payload, lines, ok=ok)
    if not ok:
        raise typer.Exit(2)


def register(app: typer.Typer) -> None:
    app.command()(doctor)
