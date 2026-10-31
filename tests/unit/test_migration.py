"""Workspaces, caches and environment variables from before the rename keep working."""

import json
import os
import re
import shlex
import stat
import subprocess
from importlib.resources import files
from pathlib import Path

import platformdirs
import pytest
import typer
from conftest import FakeTools
from test_doctor_cli import FILTERS, fake_ffmpeg, fake_node
from typer.core import TyperGroup
from typer.testing import CliRunner

from motion_studio import APP_NAME
from motion_studio.cli import app
from motion_studio.migrate import OLD_APP_NAME, OLD_CACHE_ENV, OLD_COMMANDS

runner = CliRunner()

OLD_TOML = f"{OLD_APP_NAME}.toml"
NEW_TOML = f"{APP_NAME}.toml"
SKILL_DIRS = [".claude/skills", ".agents/skills"]
OLD_SKILLS = [f"{OLD_APP_NAME}-edit", f"{OLD_APP_NAME}-plan"]
# A skill the creator made, named like the shipped ones.
USER_SKILL = f"{OLD_APP_NAME}-brand"
SETTINGS = '[brand]\nprimary = "#ff3366"\n'
OLD_AGENTS_MD = Path(__file__).parents[1] / "fixtures" / "old_workspace" / "AGENTS.md"
NEW_AGENTS_MD = files("motion_studio") / "templates" / "workspace" / "AGENTS.md"


def invoke(*args: str | Path):
    return runner.invoke(app, [str(a) for a in args])


@pytest.fixture
def old_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A workspace the old name left: its toml and skill folders, plus a skill of the user's."""
    ws = tmp_path / "my reels"
    ws.mkdir()
    (ws / OLD_TOML).write_text(SETTINGS, encoding="utf-8")
    for skill_dir in SKILL_DIRS:
        for name in [*OLD_SKILLS, "my-own-skill", USER_SKILL]:
            (ws / skill_dir / name).mkdir(parents=True)
            (ws / skill_dir / name / "SKILL.md").write_text("---\n", encoding="utf-8")
    (ws / "AGENTS.md").write_bytes(OLD_AGENTS_MD.read_bytes())
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
        assert not set(OLD_SKILLS) & set(names)
        assert f"{APP_NAME}-edit" in names
        assert "my-own-skill" in names
        assert USER_SKILL in names
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
    assert payload["agents_md"] is None
    assert (old_workspace / NEW_TOML).read_text(encoding="utf-8") == SETTINGS


def test_agents_sync_rewrites_an_unedited_old_agents_md_from_the_template(
    old_workspace: Path,
) -> None:
    result = invoke("agents", "sync")

    assert result.exit_code == 0, result.output
    agents_md = old_workspace / "AGENTS.md"
    assert agents_md.read_text(encoding="utf-8") == NEW_AGENTS_MD.read_text(encoding="utf-8")
    assert f"rewrote {agents_md} from the template" in result.output


def test_agents_sync_renames_the_old_name_in_an_edited_agents_md(old_workspace: Path) -> None:
    agents_md = old_workspace / "AGENTS.md"
    house_style = f"\n## House style\nUse the skill `{USER_SKILL}` for colours.\n"
    settings = f"Settings live in {OLD_TOML}.\n"
    old_text = OLD_AGENTS_MD.read_text(encoding="utf-8") + settings + house_style
    agents_md.write_text(old_text, "utf-8")

    result = invoke("agents", "sync")

    assert result.exit_code == 0, result.output
    text = agents_md.read_text(encoding="utf-8")
    assert text.endswith(f"Settings live in {NEW_TOML}.\n{house_style}")
    assert f"`{APP_NAME}-edit`" in text
    assert f"{APP_NAME} agents sync" in text
    assert f"`{OLD_APP_NAME} " not in text
    assert f"{OLD_APP_NAME}-edit" not in text
    [line] = [x for x in result.output.splitlines() if str(agents_md) in x]
    assert f"renamed {OLD_APP_NAME} to {APP_NAME} in {agents_md}" in line


@pytest.mark.parametrize(
    "line",
    [
        f"Use `{OLD_APP_NAME}-edit-extra` for intros.",
        f"Use `my-{OLD_APP_NAME}-edit` for intros.",
        f"Models live in ~/Library/Caches/{OLD_APP_NAME}/models.",
        f"Source: https://github.com/pumpkit-io/{OLD_APP_NAME}",
        f"Presets are in {OLD_APP_NAME}.json.",
        f"Back up to {OLD_APP_NAME}.toml.bak first.",
    ],
)
def test_an_edited_agents_md_keeps_the_users_own_names_paths_and_urls(
    old_workspace: Path, line: str
) -> None:
    agents_md = old_workspace / "AGENTS.md"
    agents_md.write_text(OLD_AGENTS_MD.read_text(encoding="utf-8") + f"\n{line}\n", "utf-8")

    result = invoke("agents", "sync")

    assert result.exit_code == 0, result.output
    assert agents_md.read_text(encoding="utf-8").endswith(f"\n{line}\n")


def test_a_non_utf8_agents_md_is_left_alone_with_a_warning(old_workspace: Path) -> None:
    agents_md = old_workspace / "AGENTS.md"
    latin1 = f"Use `{OLD_APP_NAME} doctor` per caff\u00e8.\n".encode("latin-1")
    agents_md.write_bytes(latin1)

    result = invoke("agents", "sync")

    assert result.exit_code == 0, result.output
    assert agents_md.read_bytes() == latin1
    [line] = [x for x in result.stderr.splitlines() if x.startswith("warning:")]
    assert str(agents_md) in line
    assert (old_workspace / NEW_TOML).exists()


def test_the_json_output_carries_the_migration_warnings(old_workspace: Path) -> None:
    agents_md = old_workspace / "AGENTS.md"
    agents_md.write_bytes(f"Use `{OLD_APP_NAME} doctor` per caff\u00e8.\n".encode("latin-1"))

    result = invoke("agents", "sync", "--json")

    assert result.exit_code == 0, result.output
    [warning] = json.loads(result.stdout)["warnings"]
    assert str(agents_md) in warning


def test_the_old_commands_cover_the_old_agents_md_and_exist_in_the_cli() -> None:
    # The fixture is the frozen v0.1.0 template, so every command it names must be renamed;
    # a name the CLI does not have is a typo or a stale list.
    pattern = rf"(?<![-\w/.]){OLD_APP_NAME} ([a-z][a-z-]*)"
    in_fixture = set(re.findall(pattern, OLD_AGENTS_MD.read_text(encoding="utf-8")))
    root = typer.main.get_command(app)
    assert isinstance(root, TyperGroup)

    assert in_fixture <= set(OLD_COMMANDS)
    assert set(OLD_COMMANDS) <= set(root.commands)


@pytest.mark.skipif(os.geteuid() == 0, reason="root writes through a read-only directory")
def test_a_failed_skill_install_leaves_the_old_skills_in_place(old_workspace: Path) -> None:
    claude_skills = old_workspace / ".claude/skills"
    claude_skills.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        result = invoke("agents", "sync")
    finally:
        claude_skills.chmod(stat.S_IRWXU)

    assert result.exit_code != 0
    for skill_dir in SKILL_DIRS:
        assert set(OLD_SKILLS) <= set(skills_in(old_workspace, skill_dir))


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


def test_the_command_from_the_first_doctor_run_adopts_the_old_cache_without_nesting_it(
    fake_tools: FakeTools, default_caches: tuple[Path, Path]
) -> None:
    old, new = default_caches
    assert not new.exists()
    fake_ffmpeg(fake_tools, FILTERS)
    fake_node(fake_tools)
    payload = json.loads(invoke("doctor", "--json").output)
    [check] = [c for c in payload["checks"] if c["name"] == "old cache"]

    subprocess.run(["/bin/sh", "-c", check["fix"]], check=True, env={"PATH": "/usr/bin:/bin"})

    assert (new / "models" / "silero_vad.onnx").is_file()
    assert not (new / OLD_APP_NAME).exists()
    assert not old.exists()


def test_the_printed_command_refuses_to_nest_the_old_cache_in_a_new_one_that_holds_data(
    fake_tools: FakeTools, default_caches: tuple[Path, Path]
) -> None:
    old, new = default_caches
    fake_ffmpeg(fake_tools, FILTERS)
    fake_node(fake_tools)
    payload = json.loads(invoke("doctor", "--json").output)
    [check] = [c for c in payload["checks"] if c["name"] == "old cache"]
    (new / "models").mkdir(parents=True)
    (new / "models" / "downloaded-since.onnx").write_bytes(b"y")

    done = subprocess.run(["/bin/sh", "-c", check["fix"]], env={"PATH": "/usr/bin:/bin"})

    assert done.returncode != 0
    assert (old / "models" / "silero_vad.onnx").is_file()
    assert not (new / OLD_APP_NAME).exists()


def test_doctor_finds_the_old_cache_the_old_variable_points_at(
    fake_tools: FakeTools,
    default_caches: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    custom = tmp_path / "big disk" / "cache"
    (custom / "models").mkdir(parents=True)
    (custom / "models" / "silero_vad.onnx").write_bytes(b"x")
    monkeypatch.setenv(f"{OLD_APP_NAME.upper()}_CACHE_DIR", str(custom))
    fake_ffmpeg(fake_tools, FILTERS)
    fake_node(fake_tools)

    result = invoke("doctor")

    [line] = [x for x in result.output.splitlines() if "old cache" in x]
    assert shlex.quote(str(custom)) in line


def test_the_printed_command_adopts_the_old_cache_past_the_new_caches_locks(
    fake_tools: FakeTools, default_caches: tuple[Path, Path]
) -> None:
    old, new = default_caches
    (new / "locks").mkdir(parents=True)
    (new / "locks" / "heavy-model.lock").touch()
    fake_ffmpeg(fake_tools, FILTERS)
    fake_node(fake_tools)
    payload = json.loads(invoke("doctor", "--json").output)
    [check] = [c for c in payload["checks"] if c["name"] == "old cache"]

    subprocess.run(["/bin/sh", "-c", check["fix"]], check=True, env={"PATH": "/usr/bin:/bin"})

    assert (new / "models" / "silero_vad.onnx").is_file()
    assert not old.exists()


def test_a_set_cache_variable_skips_the_old_cache_check(
    fake_tools: FakeTools,
    default_caches: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MOTION_STUDIO_CACHE_DIR", str(tmp_path / "chosen"))
    fake_ffmpeg(fake_tools, FILTERS)
    fake_node(fake_tools)

    result = invoke("doctor")

    assert "old cache" not in result.output


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


def test_the_printed_command_adopts_the_old_cache_when_the_home_path_holds_glob_characters(
    fake_tools: FakeTools, default_caches: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    home = Path(os.environ["HOME"]).with_name("home [x]")
    Path(os.environ["HOME"]).rename(home)
    monkeypatch.setenv("HOME", str(home))
    old, new = platformdirs.user_cache_path(OLD_APP_NAME), platformdirs.user_cache_path(APP_NAME)
    (new / "locks").mkdir(parents=True)
    (new / "locks" / "heavy-model.lock").touch()
    fake_ffmpeg(fake_tools, FILTERS)
    fake_node(fake_tools)
    payload = json.loads(invoke("doctor", "--json").output)
    [check] = [c for c in payload["checks"] if c["name"] == "old cache"]

    subprocess.run(["/bin/sh", "-c", check["fix"]], check=True, env={"PATH": "/usr/bin:/bin"})

    assert (new / "models" / "silero_vad.onnx").is_file()
    assert not old.exists()


def test_a_custom_old_cache_is_adopted_by_pointing_the_new_variable_at_it(
    fake_tools: FakeTools,
    default_caches: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    custom = tmp_path / "big disk" / "cache"
    (custom / "models").mkdir(parents=True)
    monkeypatch.setenv(OLD_CACHE_ENV, str(custom))
    fake_ffmpeg(fake_tools, FILTERS)
    fake_node(fake_tools)

    result = invoke("doctor", "--json")

    [check] = [c for c in json.loads(result.stdout)["checks"] if c["name"] == "old cache"]
    assignment = f"MOTION_STUDIO_CACHE_DIR={shlex.quote(str(custom))}"
    assert "mv " not in check["fix"]
    assert assignment in check["fix"]
    [warning] = [x for x in result.stderr.splitlines() if "CACHE_DIR" in x]
    assert assignment in warning


def test_the_old_variable_set_to_the_old_default_is_unset_not_copied(
    fake_tools: FakeTools, default_caches: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    old, _ = default_caches
    monkeypatch.setenv(OLD_CACHE_ENV, str(old))
    fake_ffmpeg(fake_tools, FILTERS)
    fake_node(fake_tools)

    result = invoke("doctor", "--json")

    [check] = [c for c in json.loads(result.stdout)["checks"] if c["name"] == "old cache"]
    assert "mv " in check["fix"]
    [warning] = [x for x in result.stderr.splitlines() if OLD_CACHE_ENV in x]
    assert "unset" in warning
    assert "MOTION_STUDIO_CACHE_DIR=" not in warning
