"""`reelcut analyze` on the EN and IT fixtures with the real VAD and both Whisper backends.

Uses the real cache (models and the heavy-model lock are machine-wide); run `reelcut setup`
first. Each backend gets its own project; faster-whisper is forced through project.toml.
"""

import json
import subprocess
import sys
import threading
import time
import tomllib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from reelcut.asr import DEFAULT_MODELS, model_path
from reelcut.asr.vad import vad_model_path
from reelcut.audio.enhance import deep_filter_binary
from reelcut.cli import app
from reelcut.state import heavy_model_lock
from reelcut.text import normalise_words

pytestmark = [pytest.mark.slow, pytest.mark.mac, pytest.mark.models]

ROOT = Path(__file__).resolve().parents[1] / "fixtures"
MEDIA = ROOT / "media"
TRUTH = ROOT / "ground_truth"
TALKING = {"en_talking.mov": "en", "it_talking.mov": "it", "prova clip è.mov": "en"}
FIXTURES = [*TALKING, "broll.mp4", "image.png"]
BACKENDS = ["mlx-whisper", "faster-whisper"]
TOLERANCE_S = 0.15
FIVE_MINUTES_REPEATS = 15

runner = CliRunner()


def require_setup(backend: str) -> None:
    missing = [name for name in FIXTURES if not (MEDIA / name).exists()]
    if missing:
        pytest.skip(f"fixtures not generated ({', '.join(missing)}); run `just fixtures`")
    if not vad_model_path().is_file() or model_path(DEFAULT_MODELS[backend]) is None:  # type: ignore[index]
        pytest.skip("speech models not in the cache; run `reelcut setup`")


def make_project(
    root: Path, monkeypatch: pytest.MonkeyPatch, backend: str, sources: list[Path]
) -> Path:
    deep_filter = deep_filter_binary()
    if deep_filter:
        monkeypatch.setenv("REELCUT_DEEP_FILTER", str(deep_filter))
    monkeypatch.setenv("REELCUT_MIN_FREE_GB", "0")
    workspace = root / "reels"
    assert runner.invoke(app, ["init", str(workspace)]).exit_code == 0
    monkeypatch.chdir(workspace)
    result = runner.invoke(app, ["new", "fixtures", "--from", *map(str, sources)])
    assert result.exit_code == 0, result.output
    project = workspace / "projects" / "fixtures"
    toml = project / "project.toml"
    toml.write_text(
        toml.read_text(encoding="utf-8") + f'\n[asr]\nbackend = "{backend}"\n', encoding="utf-8"
    )
    result = runner.invoke(app, ["ingest", "fixtures", "--json"])
    assert result.exit_code == 0, result.output
    return project


def analyze(*extra: str) -> tuple[dict[str, Any], str]:
    result = runner.invoke(app, ["analyze", "fixtures", "--json", *extra])
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout), result.stderr


def sources(project: Path) -> dict[str, str]:
    """Clip ID to the fixture file name it came from."""
    clips = tomllib.loads((project / "project.toml").read_text(encoding="utf-8"))["clips"]
    return {clip_id: Path(entry["source"]).name for clip_id, entry in clips.items()}


def analysis(project: Path, clip_id: str) -> dict[str, Any]:
    return json.loads((project / "analysis" / f"{clip_id}.json").read_text(encoding="utf-8"))


def silences(clip: dict[str, Any]) -> list[tuple[float, float]]:
    """Gaps between VAD regions, including the head and the tail of the clip."""
    edges = [0.0]
    for region in clip["vad"]:
        edges += [region["start"], region["end"]]
    edges.append(clip["clip"]["duration_s"])
    return [(a, b) for a, b in zip(edges[::2], edges[1::2], strict=True) if b > a]


@pytest.fixture(scope="module", params=BACKENDS)
def analysed(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[tuple[Path, dict[str, Any], str]]:
    backend: str = request.param
    require_setup(backend)
    with pytest.MonkeyPatch.context() as monkeypatch:
        project = make_project(
            tmp_path_factory.mktemp(backend), monkeypatch, backend, [MEDIA / n for n in FIXTURES]
        )
        out, _ = analyze()
        yield project, out, backend


def test_each_talking_fixture_is_detected_in_its_language(
    analysed: tuple[Path, dict[str, Any], str],
) -> None:
    project, out, backend = analysed
    assert out["asr"]["backend"] == backend
    names = sources(project)
    detected = {names[c["id"]]: c["language"] for c in out["clips"] if names[c["id"]] in TALKING}
    assert detected == TALKING
    assert out["language"] == "en"


def test_at_least_90_percent_of_the_known_silences_are_found_within_150_ms(
    analysed: tuple[Path, dict[str, Any], str],
) -> None:
    project, _, _ = analysed
    found = total = 0
    misses: list[str] = []
    for clip_id, name in sources(project).items():
        if name not in ("en_talking.mov", "it_talking.mov"):
            continue
        truth = json.loads((TRUTH / name.replace(".mov", ".json")).read_text(encoding="utf-8"))
        gaps = silences(analysis(project, clip_id))
        for silence in truth["silences"]:
            start, end = silence["start_ms"] / 1000, silence["end_ms"] / 1000
            total += 1
            if any(abs(a - start) <= TOLERANCE_S and abs(b - end) <= TOLERANCE_S for a, b in gaps):
                found += 1
            else:
                misses.append(f"{name} {silence}")
    assert found / total >= 0.9, f"{found}/{total} found; missed {misses}"


def test_the_known_retake_pair_is_clustered_with_the_complete_take_winning(
    analysed: tuple[Path, dict[str, Any], str],
) -> None:
    project, _, _ = analysed
    retakes = json.loads((project / "analysis" / "retakes.json").read_text(encoding="utf-8"))
    for clip_id, name in sources(project).items():
        if name not in ("en_talking.mov", "it_talking.mov"):
            continue
        truth = json.loads((TRUTH / name.replace(".mov", ".json")).read_text(encoding="utf-8"))
        lines = truth["utterances"]
        abandoned = tuple(normalise_words(lines[truth["retake"]["abandoned"]]["text"]))
        winner = tuple(normalise_words(lines[truth["retake"]["winner"]]["text"]))
        utterances = {
            tuple(normalise_words(u["text"])): u for u in analysis(project, clip_id)["utterances"]
        }
        lost, won = utterances[abandoned], utterances[winner]
        assert lost["complete"] is False
        assert won["complete"] is True
        cluster = next(c for c in retakes["clusters"] if lost["id"] in c["members"])
        assert won["id"] in cluster["members"]
        winning = next(
            u
            for c in sources(project)
            if (project / "analysis" / f"{c}.json").exists()
            for u in analysis(project, c)["utterances"]
            if u["id"] == cluster["winner"]
        )
        assert winning["complete"] is True


def test_assets_have_no_transcript(analysed: tuple[Path, dict[str, Any], str]) -> None:
    project, _, _ = analysed
    names = {name: clip_id for clip_id, name in sources(project).items()}
    for asset in ("broll.mp4", "image.png"):
        clip = analysis(project, names[asset])
        assert clip["words"] == [], asset
        assert clip["language"] is None, asset


def test_the_model_runs_in_a_worker_that_has_exited_and_waits_for_the_lock(
    analysed: tuple[Path, dict[str, Any], str],
) -> None:
    project, out, _ = analysed
    assert out["asr"]["worker_peak_rss_mb"] > 300
    probe = subprocess.run(["ps", "-p", str(out["asr"]["worker_pid"])], capture_output=True)
    assert probe.returncode != 0, "the worker process is still alive"
    assert "mlx_whisper" not in sys.modules and "faster_whisper" not in sys.modules

    clip_id = next(c for c, name in sources(project).items() if name == "en_talking.mov")
    held = threading.Event()

    def hold() -> None:
        with heavy_model_lock("test-holder"):
            held.set()
            time.sleep(2)

    holder = threading.Thread(target=hold)
    holder.start()
    held.wait()
    result = runner.invoke(app, ["analyze", "fixtures", "--clip", clip_id])
    holder.join()
    assert result.exit_code == 0, result.output
    assert "waiting for the heavy-model lock (test-holder" in result.stderr


def test_packed_index_of_a_five_minute_clip_stays_under_2500_tokens(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = "mlx-whisper"
    require_setup(backend)
    listing = tmp_path / "list.txt"
    listing.write_text(
        f"file '{MEDIA / 'en_talking.mov'}'\n" * FIVE_MINUTES_REPEATS, encoding="utf-8"
    )
    long_clip = tmp_path / "long take.mov"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(listing),
            "-c",
            "copy",
            str(long_clip),
        ],
        check=True,
    )
    project = make_project(tmp_path, monkeypatch, backend, [long_clip])
    out, _ = analyze()
    [clip] = out["clips"]
    assert clip["language"] == "en"
    duration = analysis(project, clip["id"])["clip"]["duration_s"]
    assert duration >= 300
    packed = (project / "analysis" / "packed.md").read_text(encoding="utf-8")
    assert len(packed) / 4 < 2500, f"{len(packed) / 4:.0f} tokens"
