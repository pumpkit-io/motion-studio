"""`reelcut setup` against the real cache: every download is present afterwards."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from reelcut.cli import app

pytestmark = [pytest.mark.slow, pytest.mark.models]


def test_setup_leaves_the_denoiser_vad_face_and_speech_models_in_the_cache() -> None:
    result = CliRunner().invoke(app, ["setup", "--json"])

    assert result.exit_code == 0, result.output
    items = {item["name"].split()[0]: item for item in json.loads(result.stdout)["items"]}
    assert {
        "deepfilternet",
        "silero-vad",
        "blaze_face_short_range-float16-1.tflite",
        "face_detection_yunet_2023mar.onnx",
    } <= items.keys()
    assert any(name in items for name in ("mlx-whisper", "faster-whisper"))
    assert all(Path(item["path"]).exists() for item in items.values())

    again = json.loads(CliRunner().invoke(app, ["setup", "--json"]).stdout)
    assert {item["status"] for item in again["items"]} == {"present"}
