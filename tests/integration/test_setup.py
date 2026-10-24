"""`reelcut setup` against the real cache: every download is present afterwards."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from reelcut.cli import app

pytestmark = [pytest.mark.slow, pytest.mark.models]


def test_setup_leaves_the_denoiser_vad_and_speech_model_in_the_cache() -> None:
    result = CliRunner().invoke(app, ["setup", "--json"])

    assert result.exit_code == 0, result.output
    items = {item["name"].split()[0]: item for item in json.loads(result.stdout)["items"]}
    assert {"deepfilternet", "silero-vad"} <= items.keys()
    assert any(name in items for name in ("mlx-whisper", "faster-whisper"))
    assert all(Path(item["path"]).exists() for item in items.values())

    again = json.loads(CliRunner().invoke(app, ["setup", "--json"]).stdout)
    assert {item["status"] for item in again["items"]} == {"present"}


@pytest.mark.music
def test_setup_music_installs_acestep_and_prints_the_weights_licence() -> None:
    result = CliRunner().invoke(app, ["setup", "--music"])

    assert result.exit_code == 0, result.output
    assert "weights licence: mit" in result.output
    data = json.loads(CliRunner().invoke(app, ["setup", "--music", "--json"]).stdout)
    (ace,) = [item for item in data["items"] if item["name"].startswith("ace-step")]
    assert ace["status"] == "present"
    assert ace["licence"] == "mit"
    assert (Path(ace["path"]) / "install.json").is_file()
