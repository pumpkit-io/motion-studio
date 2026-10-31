"""`motion-studio record web` without a browser: the checks that run before any recording."""

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from motion_studio.cli import app

runner = CliRunner()


def invoke(*args: str | Path):
    return runner.invoke(app, [str(a) for a in args])


def run_json(*args: str | Path) -> dict[str, Any]:
    result = invoke(*args, "--json")
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


@pytest.fixture(autouse=True)
def no_disk_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTION_STUDIO_MIN_FREE_GB", "0")


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    ws = tmp_path / "videos"
    assert invoke("init", ws).exit_code == 0
    monkeypatch.chdir(ws)
    return ws


@pytest.fixture
def script(tmp_path: Path) -> Path:
    path = tmp_path / "take.mjs"
    path.write_text("export default async function take(r) {}\n", encoding="utf-8")
    return path


def test_record_web_without_playwright_exits_2_naming_setup_record(
    workspace: Path, script: Path
) -> None:
    run_json("new", "launch", "--kind", "product")

    result = invoke("record", "web", "launch", script)

    assert result.exit_code == 2, result.output
    assert "Playwright" in result.output
    assert "setup --record" in result.output
    assert list((workspace / "projects" / "launch" / "raw").iterdir()) == []


def test_record_web_on_a_talk_project_exits_1(workspace: Path, script: Path) -> None:
    run_json("new", "talk")

    result = invoke("record", "web", "talk", script)

    assert result.exit_code == 1
    assert "product projects" in result.output


def test_record_web_with_a_missing_script_exits_1(workspace: Path, tmp_path: Path) -> None:
    run_json("new", "launch", "--kind", "product")

    result = invoke("record", "web", "launch", tmp_path / "nope.mjs")

    assert result.exit_code == 1
    assert "nope.mjs" in result.output
