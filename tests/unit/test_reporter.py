"""Progress while a command runs: Rich bars on a terminal, plain lines elsewhere, none for JSON."""

import io
import json
import shutil
from pathlib import Path

import pytest
from rich.console import Console
from typer.testing import CliRunner

from motion_studio.cli import app
from motion_studio.cli._output import Reporter


def terminal() -> tuple[Console, io.StringIO]:
    buffer = io.StringIO()
    return Console(file=buffer, force_terminal=True, width=100), buffer


def test_on_a_terminal_a_step_with_a_known_length_draws_a_rich_bar() -> None:
    console, buffer = terminal()
    with Reporter(False, console=console) as reporter:
        reporter.step("encoding c1")
        reporter.progress(5, 10)
    out = buffer.getvalue()
    assert "encoding c1" in out
    assert "50%" in out
    assert "━" in out


def test_on_a_terminal_warnings_print_above_the_bar() -> None:
    console, buffer = terminal()
    with Reporter(False, console=console) as reporter:
        reporter.step("composing 9x16 with Remotion")
        reporter.warn("Inter used instead of Montserrat")
    assert "warning: Inter used instead of Montserrat" in buffer.getvalue()


def test_json_output_draws_no_progress_at_all() -> None:
    console, buffer = terminal()
    with Reporter(True, console=console) as reporter:
        reporter.step("encoding c1")
        reporter.progress(5, 10)
        reporter.warn("x")
    assert buffer.getvalue() == ""


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_without_a_terminal_ingest_prints_plain_step_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MOTION_STUDIO_MIN_FREE_GB", "0")
    runner = CliRunner()
    ws = tmp_path / "ws"
    assert runner.invoke(app, ["init", str(ws)]).exit_code == 0
    monkeypatch.chdir(ws)
    tiny = Path(__file__).resolve().parents[1] / "fixtures" / "tiny.mp4"
    assert runner.invoke(app, ["new", "demo", "--from", str(tiny)]).exit_code == 0

    result = runner.invoke(app, ["ingest", "demo"])

    assert result.exit_code == 0, result.output
    assert "normalising c1 (raw/tiny.mp4) ..." in result.stderr
    assert "━" not in result.stderr
    quiet = runner.invoke(app, ["ingest", "demo", "--json"])
    assert json.loads(quiet.stdout)["ok"] is True
