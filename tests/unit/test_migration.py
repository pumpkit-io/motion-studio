"""Workspaces, caches and environment variables from before the rename keep working."""

import json
import shlex
import subprocess
from pathlib import Path

import platformdirs
import pytest
from conftest import FakeTools
from test_doctor_cli import FILTERS, fake_ffmpeg, fake_node
from typer.testing import CliRunner

from motion_studio import APP_NAME
from motion_studio.cli import app
from motion_studio.migrate import OLD_APP_NAME

runner = CliRunner()

OLD_TOML = f"{OLD_APP_NAME}.toml"
NEW_TOML = f"{APP_NAME}.toml"
SKILL_DIRS = [".claude/skills", ".agents/skills"]
OLD_SKILLS = [f"{OLD_APP_NAME}-edit", f"{OLD_APP_NAME}-plan"]
SETTINGS = '[brand]\nprimary = "#ff3366"\n'


def invoke(*args: str | Path):
    return runner.invoke(app, [str(a) for a in args])


@pytest.fixture
def old_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A workspace the old name left: its toml and skill folders, plus a skill of the user's."""
    ws = tmp_path / "my reels"
    ws.mkdir()
    (ws / OLD_TOML).write_text(SETTINGS, encoding="utf-8")
    for skill_dir in SKILL_DIRS:
        for name in [*OLD_SKILLS, "my-own-skill"]:
            (ws / skill_dir / name).mkdir(parents=True)
            (ws / skill_dir / name / "SKILL.md").write_text("---\n", encoding="utf-8")
    (ws / "projects").mkdir()
    monkeypatch.chdir(ws)
    return ws


def skills_in(ws: Path, skill_dir: str) -> list[str]:
    return sorted(p.name for p in (ws / skill_dir).iterdir())


def test_agents_sync_migrates_an_old_workspace_and_prints_each_change(old_workspace: Path) -> None:
    result = invoke("agents", "sync")

    assert result.exit_code == 0, result.output
    assert not (old_workspace / OLD_TOML).exists()
    assert (old_workspace / NEW_TOML).read_text(encoding="utf-8") == SETTINGS
    for skill_dir in SKILL_DIRS:
        names = skills_in(old_workspace, skill_dir)
        assert not [n for n in names if n.startswith(f"{OLD_APP_NAME}-")]
        assert f"{APP_NAME}-edit" in names
        assert "my-own-skill" in names
    assert f"renamed {old_workspace / OLD_TOML} -> {old_workspace / NEW_TOML}" in result.output
    for skill_dir in SKILL_DIRS:
        for name in OLD_SKILLS:
            assert f"removed {old_workspace / skill_dir / name}" in result.output


def test_a_second_agents_sync_migrates_nothing(old_workspace: Path) -> None:
    assert invoke("agents", "sync").exit_code == 0

    result = invoke("agents", "sync", "--json")

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["renamed"] == []
    assert payload["removed"] == []
    assert (old_workspace / NEW_TOML).read_text(encoding="utf-8") == SETTINGS


def test_agents_sync_refuses_when_both_workspace_files_exist(old_workspace: Path) -> None:
    (old_workspace / NEW_TOML).write_text("", encoding="utf-8")

    result = invoke("agents", "sync")

    assert result.exit_code == 1
    assert OLD_TOML in result.output
    assert NEW_TOML in result.output
    assert (old_workspace / OLD_TOML).exists()
    assert (old_workspace / ".claude/skills" / OLD_SKILLS[0]).exists()


def test_other_commands_in_an_old_workspace_point_at_agents_sync(old_workspace: Path) -> None:
    result = invoke("status", "demo")

    assert result.exit_code == 1
    assert f"{APP_NAME} agents sync" in result.output
    assert OLD_TOML in result.output


def test_a_set_old_environment_variable_warns_with_its_replacement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(f"{OLD_APP_NAME.upper()}_CACHE_DIR", "/somewhere")

    result = invoke("--version")

    assert result.exit_code == 0
    [line] = [x for x in result.stderr.splitlines() if "warning" in x]
    assert f"{OLD_APP_NAME.upper()}_CACHE_DIR" in line
    assert "MOTION_STUDIO_CACHE_DIR" in line


@pytest.fixture
def default_caches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """The platform cache locations under a scratch home, with the old one full of models."""
    monkeypatch.setenv("HOME", str(tmp_path / "home dir"))
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.delenv("MOTION_STUDIO_CACHE_DIR")
    old = platformdirs.user_cache_path(OLD_APP_NAME)
    (old / "models").mkdir(parents=True)
    (old / "models" / "silero_vad.onnx").write_bytes(b"x")
    return old, platformdirs.user_cache_path(APP_NAME)


def test_doctor_prints_the_command_that_adopts_the_old_cache(
    fake_tools: FakeTools, default_caches: tuple[Path, Path]
) -> None:
    old, new = default_caches
    fake_ffmpeg(fake_tools, FILTERS)
    fake_node(fake_tools)

    result = invoke("doctor")

    assert result.exit_code == 0, result.output
    [line] = [x for x in result.output.splitlines() if "old cache" in x]
    assert shlex.quote(str(old)) in line
    assert shlex.quote(str(new)) in line
    assert " mv " in line
    assert (old / "models" / "silero_vad.onnx").is_file()


def test_the_printed_command_adopts_the_old_cache(
    fake_tools: FakeTools, default_caches: tuple[Path, Path]
) -> None:
    old, new = default_caches
    fake_ffmpeg(fake_tools, FILTERS)
    fake_node(fake_tools)
    invoke("doctor")
    assert new.is_dir(), "the first doctor run lays down the new cache's empty folders"
    payload = json.loads(invoke("doctor", "--json").output)
    [check] = [c for c in payload["checks"] if c["name"] == "old cache"]

    subprocess.run(["/bin/sh", "-c", check["fix"]], check=True, env={"PATH": "/usr/bin:/bin"})

    assert (new / "models" / "silero_vad.onnx").is_file()
    assert not old.exists()


def test_doctor_says_nothing_once_the_new_cache_holds_files(
    fake_tools: FakeTools, default_caches: tuple[Path, Path]
) -> None:
    _, new = default_caches
    (new / "models").mkdir(parents=True)
    (new / "models" / "silero_vad.onnx").write_bytes(b"x")
    fake_ffmpeg(fake_tools, FILTERS)
    fake_node(fake_tools)

    result = invoke("doctor")

    assert "old cache" not in result.output


def test_setup_stops_before_downloading_and_prints_the_adopting_command(
    default_caches: tuple[Path, Path],
) -> None:
    old, new = default_caches

    result = invoke("setup")

    assert result.exit_code == 1
    assert "mv " in result.output
    assert shlex.quote(str(old)) in result.output
    assert not [p for p in new.rglob("*") if p.is_file()]
