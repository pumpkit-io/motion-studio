from pathlib import Path

import pytest

from reelcut.errors import UserError
from reelcut.paths import cache_dir, find_workspace, project_paths


def test_finds_the_workspace_from_a_nested_directory(tmp_path: Path) -> None:
    (tmp_path / "reelcut.toml").write_text("", encoding="utf-8")
    nested = tmp_path / "projects" / "demo" / "raw"
    nested.mkdir(parents=True)
    assert find_workspace(nested) == tmp_path.resolve()


def test_nearest_workspace_wins(tmp_path: Path) -> None:
    (tmp_path / "reelcut.toml").write_text("", encoding="utf-8")
    inner = tmp_path / "inner"
    inner.mkdir()
    (inner / "reelcut.toml").write_text("", encoding="utf-8")
    assert find_workspace(inner) == inner.resolve()


def test_no_workspace_is_a_user_error(tmp_path: Path) -> None:
    with pytest.raises(UserError, match=r"reelcut\.toml") as excinfo:
        find_workspace(tmp_path)
    assert excinfo.value.exit_code == 1


def test_directory_named_like_the_workspace_file_does_not_count(tmp_path: Path) -> None:
    (tmp_path / "reelcut.toml").mkdir()
    with pytest.raises(UserError):
        find_workspace(tmp_path)


def test_project_paths_follow_the_guide_layout(tmp_path: Path) -> None:
    project = project_paths(tmp_path, "demo")
    assert project.root == tmp_path / "projects" / "demo"
    assert project.raw == project.root / "raw"
    assert project.edl == project.root / "edl.json"
    assert project.state == project.root / "state.json"


@pytest.mark.parametrize("slug", ["", "Demo", "../escape", "a b", "-lead", "a/b"])
def test_bad_slugs_are_rejected(tmp_path: Path, slug: str) -> None:
    with pytest.raises(UserError, match="slug"):
        project_paths(tmp_path, slug)


def test_cache_dir_honours_the_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REELCUT_CACHE_DIR", str(tmp_path / "cache"))
    assert cache_dir() == tmp_path / "cache"
    assert cache_dir().is_dir()
