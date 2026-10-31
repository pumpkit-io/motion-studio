"""`motion-studio ingest` on the generated EN and IT fixtures with the real DeepFilterNet binary."""

import json
import platform
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from motion_studio.audio.enhance import deep_filter_binary, install_deep_filter
from motion_studio.cli import app
from motion_studio.media.ffmpeg import run_ffprobe

pytestmark = [pytest.mark.slow, pytest.mark.mac]

MEDIA = Path(__file__).resolve().parents[1] / "fixtures" / "media"
FIXTURES = ["en_talking.mov", "it_talking.mov", "prova clip è.mov", "broll.mp4", "image.png"]
FPS = 30

runner = CliRunner()


def video_stream(path: Path) -> dict[str, Any]:
    out = run_ffprobe(["-v", "error", "-show_streams", "-of", "json", path])
    return next(s for s in json.loads(out)["streams"] if s["codec_type"] == "video")


def duration(path: Path) -> float:
    out = run_ffprobe(["-v", "error", "-show_entries", "format=duration", "-of", "json", path])
    return float(json.loads(out)["format"]["duration"])


@pytest.fixture(scope="module")
def deep_filter() -> Path:
    assert platform.machine() == "arm64", "the DeepFilterNet check is for arm64 macOS"
    # The real cache, so the binary downloads once per machine, not once per run.
    return deep_filter_binary() or install_deep_filter()


@pytest.fixture
def ingested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, deep_filter: Path
) -> tuple[Path, dict[str, Any], str]:
    missing = [name for name in FIXTURES if not (MEDIA / name).exists()]
    if missing:
        pytest.skip(f"fixtures not generated ({', '.join(missing)}); run `just fixtures`")
    monkeypatch.setenv("MOTION_STUDIO_DEEP_FILTER", str(deep_filter))
    monkeypatch.setenv("MOTION_STUDIO_MIN_FREE_GB", "0")
    workspace = tmp_path / "reels"
    assert runner.invoke(app, ["init", str(workspace)]).exit_code == 0
    monkeypatch.chdir(workspace)
    sources = [str(MEDIA / name) for name in FIXTURES]
    assert runner.invoke(app, ["new", "fixtures", "--from", *sources]).exit_code == 0
    result = runner.invoke(app, ["ingest", "fixtures", "--json"])
    assert result.exit_code == 0, result.output
    return workspace / "projects" / "fixtures", json.loads(result.stdout), result.stderr


def test_fixture_mezzanines_are_cfr_sdr_and_keep_their_duration(
    ingested: tuple[Path, dict[str, Any], str],
) -> None:
    _, report, _ = ingested
    by_source = {Path(c["source"]).name: c for c in report["clips"]}
    assert set(by_source) == set(FIXTURES)
    assert by_source["broll.mp4"]["role"] == "broll"
    assert by_source["image.png"]["role"] == "image"
    for name in ["en_talking.mov", "it_talking.mov", "prova clip è.mov", "broll.mp4"]:
        clip = by_source[name]
        mezzanine = Path(clip["mezzanine"])
        video = video_stream(mezzanine)
        assert Fraction(video["avg_frame_rate"]) == FPS, name
        assert Fraction(video["r_frame_rate"]) == FPS, name
        assert video.get("color_transfer") not in ("arib-std-b67", "smpte2084"), name
        assert abs(duration(mezzanine) - duration(MEDIA / name)) <= 1 / FPS, name
        assert abs(duration(Path(clip["audio"])) - duration(MEDIA / name)) <= 1 / FPS, name
    assert by_source["prova clip è.mov"]["id"].startswith("c")


def test_the_voice_is_cleaned_by_deepfilternet_on_arm64_macos(
    ingested: tuple[Path, dict[str, Any], str],
) -> None:
    _, report, stderr = ingested
    talking = [c for c in report["clips"] if c["role"] == "aroll"]
    assert len(talking) == 3
    assert {c["denoiser"] for c in talking} == {"deepfilternet"}
    assert report["warnings"] == []
    assert "warning" not in stderr
