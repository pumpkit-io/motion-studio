"""`motion-studio record web` and `record terminal` without a browser or vhs: the checks that
run before any recording."""

import json
from pathlib import Path
from typing import Any

import pytest
from conftest import FakeTools
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


def write_tape(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "demo.tape"
    path.write_text(body, encoding="utf-8")
    return path


TRIVIAL_TAPE = 'Set FontSize 24\nLaunch claude --mcp-config ./mcp.json\nMark ready\nType "hi"\n'


def test_record_terminal_without_vhs_or_ttyd_exits_2_naming_both(
    workspace: Path, tmp_path: Path, fake_tools: FakeTools
) -> None:
    run_json("new", "launch", "--kind", "product")

    result = invoke("record", "terminal", "launch", write_tape(tmp_path, TRIVIAL_TAPE))

    assert result.exit_code == 2, result.output
    assert "vhs and ttyd" in result.output
    assert "brew install vhs" in result.output
    assert "ffmpeg" in result.output
    assert list((workspace / "projects" / "launch" / "raw").iterdir()) == []


def test_record_terminal_names_only_the_missing_tool(
    workspace: Path, tmp_path: Path, fake_tools: FakeTools
) -> None:
    run_json("new", "launch", "--kind", "product")
    fake_tools.add("vhs", 'print("vhs version 0.12.1")\n')

    result = invoke("record", "terminal", "launch", write_tape(tmp_path, TRIVIAL_TAPE))

    assert result.exit_code == 2, result.output
    assert "ttyd not found" in result.output


def test_record_terminal_on_a_talk_project_exits_1(workspace: Path, tmp_path: Path) -> None:
    run_json("new", "talk")

    result = invoke("record", "terminal", "talk", write_tape(tmp_path, TRIVIAL_TAPE))

    assert result.exit_code == 1
    assert "product projects" in result.output


def test_record_terminal_with_a_missing_tape_exits_1(workspace: Path, tmp_path: Path) -> None:
    run_json("new", "launch", "--kind", "product")

    result = invoke("record", "terminal", "launch", tmp_path / "nope.tape")

    assert result.exit_code == 1
    assert "nope.tape" in result.output


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ('Output "take.mp4"\nType "hi"\n', "line 1: the recorder sets the Output"),
        ("Set Framerate 60\n", "line 1: the recorder sets Framerate"),
        ("Set Width 1280\n", "--size"),
        ('Mark ready\nType "hi"\nMark ready\n', "line 3: marker ready is already placed"),
        ("Mark not.ok\n", "line 1: marker name"),
        ("Mark\n", "line 1: Mark needs a name"),
        ('Type "hi"\nLaunch claude\n', "line 2: Launch must come before"),
        ("Launch claude\nLaunch claude\n", "line 2: only one Launch"),
        ("Launch\n", "line 1: Launch needs a command"),
        ("Launch ./missing-cli --flag\n", "missing-cli"),
        ('Hide\nMark gone\nShow\nType "hi"\n', "line 2: Mark gone is in a hidden part"),
    ],
)
def test_record_terminal_rejects_a_bad_tape_with_its_line(
    workspace: Path, tmp_path: Path, fake_tools: FakeTools, body: str, message: str
) -> None:
    run_json("new", "launch", "--kind", "product")

    result = invoke("record", "terminal", "launch", write_tape(tmp_path, body))

    assert result.exit_code == 1, result.output
    assert message in result.output


@pytest.mark.parametrize("name", ["../escape", "sub/take", "..", ".hidden", "a..b"])
@pytest.mark.parametrize("command", ["web", "terminal"])
def test_a_name_that_is_not_a_plain_file_stem_exits_1(
    workspace: Path, tmp_path: Path, script: Path, name: str, command: str
) -> None:
    run_json("new", "launch", "--kind", "product")
    source = script if command == "web" else write_tape(tmp_path, TRIVIAL_TAPE)

    result = invoke("record", command, "launch", source, "--name", name, "--json")

    assert result.exit_code == 1, result.output
    assert "plain file name" in json.loads(result.stdout)["error"]
    assert not (workspace / "projects" / "launch" / "build" / "record").exists()


def test_a_script_whose_name_is_not_a_plain_stem_needs_name(
    workspace: Path, tmp_path: Path
) -> None:
    run_json("new", "launch", "--kind", "product")
    odd = tmp_path / "..take.mjs"
    odd.write_text("export default async function take(r) {}\n", encoding="utf-8")

    result = invoke("record", "web", "launch", odd, "--json")

    assert result.exit_code == 1, result.output
    assert "--name" in json.loads(result.stdout)["hint"]


@pytest.mark.parametrize(
    ("value", "message"),
    [("big", "is not WIDTHxHEIGHT"), ("200x100", "is smaller than 320x240")],
)
def test_a_bad_viewport_says_whether_it_is_malformed_or_too_small(
    workspace: Path, script: Path, value: str, message: str
) -> None:
    run_json("new", "launch", "--kind", "product")

    result = invoke("record", "web", "launch", script, "--viewport", value, "--json")

    assert result.exit_code == 1
    assert message in json.loads(result.stdout)["error"]
