"""The fixture script, driven as a command, checked with ffprobe and the decoded audio."""

from __future__ import annotations

import array
import json
import math
import subprocess
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "make_fixtures.py"
COMMITTED_TRUTH = ROOT / "tests" / "fixtures" / "ground_truth"
TALKING = ("en_talking.mov", "it_talking.mov", "prova clip è.mov")
SAMPLE_RATE = 48_000

pytestmark = [pytest.mark.slow, pytest.mark.mac]


def generate(out: Path) -> Path:
    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--media-dir",
            str(out / "media"),
            "--ground-truth-dir",
            str(out / "ground_truth"),
            "--tiny",
            str(out / "tiny.mp4"),
        ],
        check=True,
        capture_output=True,
    )
    return out


@pytest.fixture(scope="module")
def run_a(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return generate(tmp_path_factory.mktemp("fixtures_a"))


@pytest.fixture(scope="module")
def run_b(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return generate(tmp_path_factory.mktemp("fixtures_b"))


def probe(path: Path, *args: str) -> dict[str, list[dict[str, object]]]:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-of", "json", *args, str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def video_stream(path: Path) -> dict[str, object]:
    return probe(path, "-select_streams", "v:0", "-show_streams")["streams"][0]


def decoded_audio(path: Path) -> array.array[int]:
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-f", "s16le", "-ac", "1", "-ar", "48000", "-"],
        check=True,
        capture_output=True,
    ).stdout
    return array.array("h", raw)


def window(pcm: array.array[int], start_ms: float, end_ms: float) -> array.array[int]:
    return pcm[int(start_ms * SAMPLE_RATE / 1000) : int(end_ms * SAMPLE_RATE / 1000)]


def dbfs_rms(samples: array.array[int]) -> float:
    rms = math.sqrt(sum(s * s for s in samples) / len(samples))
    return 20 * math.log10(max(rms, 1e-9) / 32768)


def load_truth(run: Path, name: str) -> Any:
    return json.loads((run / "ground_truth" / f"{name}.json").read_text())


@pytest.mark.parametrize("name", TALKING)
def test_talking_clips_are_vertical_and_variable_frame_rate(run_a: Path, name: str) -> None:
    clip = run_a / "media" / name
    stream = video_stream(clip)
    assert (stream["width"], stream["height"]) == (1080, 1920)
    assert Fraction(str(stream["avg_frame_rate"])) == 30
    # A constant-frame-rate file has one packet duration; these must have several.
    packets = probe(clip, "-select_streams", "v:0", "-show_entries", "packet=duration")["packets"]
    assert len({p["duration"] for p in packets}) > 1


@pytest.mark.parametrize(
    ("name", "language", "filler"), [("en_talking", "en", "um"), ("it_talking", "it", "ehm")]
)
def test_ground_truth_records_the_scripted_silences_filler_and_retake(
    run_a: Path, name: str, language: str, filler: str
) -> None:
    truth = load_truth(run_a, name)
    assert truth["language"] == language
    silences = truth["silences"]
    lengths = [s["end_ms"] - s["start_ms"] for s in silences]
    # The script inserts these gaps; the tail is padded up to a whole frame.
    assert lengths[:-1] == [800, 1500, 300, 300, 1200, 900, 1500]
    assert 1000 <= lengths[-1] < 1000 + 34
    fillers = truth["fillers"]
    assert [(f["text"], f["kind"]) for f in fillers] == [(filler, "hard")]
    utterances = truth["utterances"]
    retake = truth["retake"]
    abandoned, winner = utterances[retake["abandoned"]], utterances[retake["winner"]]
    assert abandoned["complete"] is False
    assert winner["complete"] is True
    assert winner["text"].startswith(abandoned["text"])
    assert abandoned["end_ms"] < winner["start_ms"]


@pytest.mark.parametrize("name", ["en_talking", "it_talking"])
def test_ground_truth_matches_the_audio_in_the_clip(run_a: Path, name: str) -> None:
    truth = load_truth(run_a, name)
    pcm = decoded_audio(run_a / "media" / f"{name}.mov")
    assert abs(len(pcm) * 1000 / SAMPLE_RATE - truth["duration_ms"]) < 34
    # Keep clear of the edges, where AAC smears a little energy across the boundary.
    margin = 40
    for span in truth["silences"]:
        assert dbfs_rms(window(pcm, span["start_ms"] + margin, span["end_ms"] - margin)) < -60
    for span in [*truth["utterances"], *truth["fillers"]]:
        assert dbfs_rms(window(pcm, span["start_ms"], span["end_ms"])) > -40


def test_committed_ground_truth_is_what_the_script_generates(run_a: Path) -> None:
    for name in ("en_talking", "it_talking"):
        generated = (run_a / "ground_truth" / f"{name}.json").read_text()
        assert generated == (COMMITTED_TRUTH / f"{name}.json").read_text()


def test_broll_image_and_tiny_clip_have_the_expected_shape(run_a: Path) -> None:
    broll = video_stream(run_a / "media" / "broll.mp4")
    assert (broll["width"], broll["height"]) == (1920, 1080)
    assert float(str(broll["duration"])) == pytest.approx(6, abs=0.05)
    image = video_stream(run_a / "media" / "image.png")
    assert image["codec_name"] == "png"
    tiny = probe(run_a / "tiny.mp4", "-show_streams")["streams"]
    assert sorted(str(s["codec_type"]) for s in tiny) == ["audio", "video"]


def stream_hashes(path: Path) -> str:
    return subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-map", "0", "-f", "streamhash", "-"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def test_regenerating_gives_the_same_streams_and_ground_truth(run_a: Path, run_b: Path) -> None:
    files_a = sorted(p.relative_to(run_a) for p in run_a.rglob("*") if p.is_file())
    files_b = sorted(p.relative_to(run_b) for p in run_b.rglob("*") if p.is_file())
    assert files_a == files_b
    for rel in files_a:
        if rel.suffix == ".json":
            assert (run_a / rel).read_text() == (run_b / rel).read_text()
        else:
            assert stream_hashes(run_a / rel) == stream_hashes(run_b / rel), rel
