from pathlib import Path

import pytest

from reelcut.config import Config, load_config
from reelcut.errors import DependencyError, UserError


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    write(tmp_path / "reelcut.toml", "")
    (tmp_path / "projects" / "demo").mkdir(parents=True)
    return tmp_path


def test_defaults_match_the_guide() -> None:
    config = Config()
    assert config.defaults.formats == ["9x16"]
    assert config.defaults.fps == 30
    assert config.edit.pad_in_ms == 80
    assert config.edit.pad_out_ms == 120
    assert config.asr.fillers_backend == "prompted"
    assert config.master.integrated_lufs == -14
    assert config.master.true_peak_db == -1.5
    assert config.music.mode == "generate"


def test_each_level_overrides_the_one_below(workspace: Path) -> None:
    write(
        workspace / "reelcut.toml",
        "[edit]\npad_in_ms = 60\npad_out_ms = 100\nmax_pause_ms = 300\n"
        '[brand]\naccent = "#00FF00"\n',
    )
    write(
        workspace / "projects" / "demo" / "project.toml",
        '[project]\ntitle = "Demo"\n[edit]\npad_out_ms = 90\nmax_pause_ms = 250\n',
    )

    config = load_config(workspace, "demo", edl_policy={"max_pause_ms": 200})

    assert config.edit.pad_in_ms == 60  # workspace beats default
    assert config.edit.pad_out_ms == 90  # project beats workspace
    assert config.edit.max_pause_ms == 200  # EDL policy beats project
    assert config.edit.min_segment_ms == 400  # untouched default survives
    assert config.brand.accent == "#00FF00"
    assert config.brand.primary == "#111111"


def test_project_level_ignores_project_metadata_and_clips(workspace: Path) -> None:
    write(
        workspace / "projects" / "demo" / "project.toml",
        '[project]\ntitle = "Demo"\n[clips.c1]\nfile = "a.mov"\nrole = "aroll"\n'
        '[defaults]\nlanguage = "it"\n',
    )
    assert load_config(workspace, "demo").defaults.language == "it"


def test_workspace_only_config_without_a_project(workspace: Path) -> None:
    write(workspace / "reelcut.toml", "[defaults]\nfps = 25\n")
    assert load_config(workspace).defaults.fps == 25


def test_unknown_key_is_a_user_error_naming_the_file(workspace: Path) -> None:
    write(workspace / "reelcut.toml", "[edit]\npad_inn_ms = 10\n")
    with pytest.raises(UserError, match=r"reelcut\.toml.*pad_inn_ms"):
        load_config(workspace)


def test_invalid_toml_is_a_user_error(workspace: Path) -> None:
    write(workspace / "reelcut.toml", "[edit\n")
    with pytest.raises(UserError, match=r"reelcut\.toml"):
        load_config(workspace)


def test_unknown_policy_key_is_a_user_error(workspace: Path) -> None:
    with pytest.raises(UserError, match="policy"):
        load_config(workspace, "demo", edl_policy={"pad_in": 10})


def test_missing_project_is_a_user_error(workspace: Path) -> None:
    with pytest.raises(UserError, match="nope"):
        load_config(workspace, "nope")


def test_crisper_is_valid_in_config_but_not_implemented_at_runtime(workspace: Path) -> None:
    write(workspace / "reelcut.toml", '[asr]\nfillers_backend = "crisper"\n')
    config = load_config(workspace)
    assert config.asr.fillers_backend == "crisper"
    with pytest.raises(DependencyError, match=r"not implemented in v0\.1\.0") as excinfo:
        config.ensure_supported()
    assert excinfo.value.exit_code == 2


def test_short_hex_colours_are_normalised(workspace: Path) -> None:
    write(
        workspace / "reelcut.toml",
        '[brand]\nprimary = "#1a2"\naccent = "ffd400"\n[captions]\ntext_color = "#fff"\n',
    )
    config = load_config(workspace)
    assert config.brand.primary == "#11AA22"
    assert config.brand.accent == "#FFD400"
    assert config.captions.text_color == "#FFFFFF"


@pytest.mark.parametrize("value", ["red", "#12345", "#GGGGGG", "rgb(0,0,0)", ""])
def test_a_colour_that_is_not_hex_is_a_user_error(workspace: Path, value: str) -> None:
    write(workspace / "reelcut.toml", f'[brand]\nprimary = "{value}"\n')
    with pytest.raises(UserError, match=r"brand\.primary.*#RRGGBB") as excinfo:
        load_config(workspace)
    assert excinfo.value.exit_code == 1
