import json
import tomllib
from pathlib import Path

import pytest
from typer.testing import CliRunner

from motion_studio.cli import app
from motion_studio.config import Config

runner = CliRunner()

PROJECT_TREE = ["raw", "media", "analysis", "contact", "build", "preview", "check", "final"]


def invoke(*args: str | Path, input: str | None = None):
    return runner.invoke(app, [str(a) for a in args], input=input)


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    ws = tmp_path / "reels"
    result = invoke("init", ws)
    assert result.exit_code == 0, result.output
    monkeypatch.chdir(ws)
    return ws


@pytest.fixture
def take(tmp_path: Path) -> Path:
    clip = tmp_path / "prova clip è.mov"
    clip.write_bytes(b"not really a movie")
    return clip


@pytest.fixture
def demo(workspace: Path, take: Path) -> Path:
    result = invoke("new", "demo", "--from", take)
    assert result.exit_code == 0, result.output
    return workspace / "projects" / "demo"


def test_init_creates_the_workspace_tree(tmp_path: Path) -> None:
    ws = tmp_path / "reels"
    result = invoke("init", ws)
    assert result.exit_code == 0, result.output
    for name in ["AGENTS.md", "CLAUDE.md", "motion-studio.toml"]:
        assert (ws / name).is_file()
        assert str(ws / name) in result.output
    for name in ["library/music", "library/brand", "projects"]:
        assert (ws / name).is_dir()
    assert (ws / "CLAUDE.md").read_text(encoding="utf-8").strip() == "@AGENTS.md"
    assert not list(ws.rglob(".gitkeep"))


def test_init_template_config_is_the_built_in_default(workspace: Path) -> None:
    data = tomllib.loads((workspace / "motion-studio.toml").read_text(encoding="utf-8"))
    assert Config.model_validate(data) == Config()


def test_init_refuses_an_existing_workspace(workspace: Path) -> None:
    result = invoke("init", workspace)
    assert result.exit_code == 1
    assert "already" in result.output


def test_new_creates_the_project_tree_with_the_file_in_raw(demo: Path, take: Path) -> None:
    for name in PROJECT_TREE:
        assert (demo / name).is_dir(), name
    for name in ["project.toml", "notes.md", "state.json"]:
        assert (demo / name).is_file(), name
    copied = demo / "raw" / take.name
    assert copied.read_bytes() == take.read_bytes()
    assert take.exists()
    meta = tomllib.loads((demo / "project.toml").read_text(encoding="utf-8"))
    assert meta["project"]["title"] == "demo"


def test_new_takes_several_files_and_directories(workspace: Path, tmp_path: Path) -> None:
    folder = tmp_path / "takes"
    folder.mkdir()
    (folder / "b.mov").write_bytes(b"b")
    (folder / ".DS_Store").write_bytes(b"x")
    single = tmp_path / "a.mov"
    single.write_bytes(b"a")
    result = invoke("new", "multi", "--title", "Launch teaser", "--from", single, folder)
    assert result.exit_code == 0, result.output
    raw = workspace / "projects" / "multi" / "raw"
    assert sorted(p.name for p in raw.iterdir()) == ["a.mov", "b.mov"]
    meta = tomllib.loads((raw.parent / "project.toml").read_text(encoding="utf-8"))
    assert meta["project"]["title"] == "Launch teaser"


def test_new_refuses_an_existing_project(demo: Path, take: Path) -> None:
    result = invoke("new", "demo", "--from", take)
    assert result.exit_code == 1
    assert "already exists" in result.output


def test_new_with_a_missing_source_is_a_user_error_and_creates_nothing(
    workspace: Path, tmp_path: Path
) -> None:
    result = invoke("new", "ghost", "--from", tmp_path / "nope.mov")
    assert result.exit_code == 1
    assert not (workspace / "projects" / "ghost").exists()


def test_new_outside_a_workspace_is_a_user_error(
    tmp_path: Path, take: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = invoke("new", "demo", "--from", take, "--json")
    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert "motion-studio.toml" in payload["error"]


def test_new_json_lists_the_written_paths(workspace: Path, take: Path) -> None:
    result = invoke("new", "demo", "--from", take, "--json")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert str(workspace / "projects" / "demo" / "raw" / take.name) in payload["raw"]


def test_config_show_json_prints_the_merged_config(demo: Path, workspace: Path) -> None:
    (workspace / "motion-studio.toml").write_text("[edit]\npad_in_ms = 60\n", encoding="utf-8")
    (demo / "project.toml").write_text(
        '[project]\ntitle = "demo"\n[edit]\npad_out_ms = 90\n', encoding="utf-8"
    )
    (demo / "edl.json").write_text(json.dumps({"policy": {"max_pause_ms": 200}}), encoding="utf-8")
    result = invoke("config", "show", "demo", "--json")
    assert result.exit_code == 0, result.output
    config = json.loads(result.output)
    assert config["edit"]["pad_in_ms"] == 60
    assert config["edit"]["pad_out_ms"] == 90
    assert config["edit"]["max_pause_ms"] == 200
    assert config["captions"]["max_words_per_page"] == 3


def test_config_show_human_output_is_toml(demo: Path) -> None:
    result = invoke("config", "show", "demo")
    assert result.exit_code == 0, result.output
    assert tomllib.loads(result.output)["defaults"]["fps"] == 30


def test_config_show_unknown_project_is_a_user_error(workspace: Path) -> None:
    result = invoke("config", "show", "nope")
    assert result.exit_code == 1
    assert "nope" in result.output


def test_status_lists_stages_and_a_next_command(demo: Path) -> None:
    result = invoke("status", "demo")
    assert result.exit_code == 0, result.output
    for stage in ["ingest", "analyze", "plan", "music", "preview", "check", "final"]:
        assert stage in result.output
    assert "motion-studio ingest demo" in result.output


def test_status_json(demo: Path) -> None:
    result = invoke("status", "demo", "--json")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert [s["name"] for s in payload["stages"]][:2] == ["ingest", "analyze"]
    assert {s["status"] for s in payload["stages"]} == {"pending"}
    assert payload["next"] == "motion-studio ingest demo"


def test_status_on_an_empty_project_says_to_add_clips(workspace: Path) -> None:
    result = invoke("new", "empty", "--json")
    assert result.exit_code == 0, result.output
    payload = json.loads(invoke("status", "empty", "--json").output)
    assert payload["next"] is None
    assert "raw" in payload["hint"]


def fill(project: Path) -> None:
    for name in ["media", "build", "preview", "analysis", "check", "final", "contact"]:
        (project / name / "file.bin").write_bytes(b"x")
    (project / "edl.json").write_text("{}", encoding="utf-8")
    (project / "notes.md").write_text("decisions", encoding="utf-8")


def test_clean_removes_caches_and_never_touches_the_creative_files(demo: Path, take: Path) -> None:
    fill(demo)
    result = invoke("clean", "demo")
    assert result.exit_code == 0, result.output
    for name in ["media", "build", "preview"]:
        assert (demo / name).is_dir()
        assert not any((demo / name).iterdir()), name
    assert (demo / "raw" / take.name).exists()
    assert (demo / "edl.json").read_text(encoding="utf-8") == "{}"
    assert (demo / "notes.md").read_text(encoding="utf-8") == "decisions"
    assert (demo / "final" / "file.bin").exists()
    assert (demo / "analysis" / "file.bin").exists()


def test_clean_all_needs_confirmation(demo: Path) -> None:
    fill(demo)
    result = invoke("clean", "demo", "--all", input="n\n")
    assert result.exit_code == 1
    assert (demo / "final" / "file.bin").exists()
    assert (demo / "edl.json").exists()


def test_clean_all_confirmed_removes_everything_but_raw(demo: Path, take: Path) -> None:
    fill(demo)
    result = invoke("clean", "demo", "--all", "--yes")
    assert result.exit_code == 0, result.output
    assert not (demo / "final" / "file.bin").exists()
    assert not (demo / "edl.json").exists()
    assert not (demo / "notes.md").exists()
    assert (demo / "raw" / take.name).exists()
    assert (demo / "project.toml").exists()


def test_usage_errors_exit_with_code_1() -> None:
    result = invoke("status")
    assert result.exit_code == 1
