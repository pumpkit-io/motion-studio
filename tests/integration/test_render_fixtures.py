"""`motion-studio render` with the real Remotion renderer on the analysed EN and IT fixtures.

Uses the real cache; run `motion-studio setup` and `just fixtures` first. Set
MOTION_STUDIO_RENDER_STILLS=<dir> to also write stills of each preview (start, first cut, zoom).
"""

import json
import os
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from PIL import Image, ImageDraw
from typer.testing import CliRunner

from motion_studio.asr import DEFAULT_MODELS, model_path, resolve_backend
from motion_studio.asr.vad import vad_model_path
from motion_studio.audio.enhance import deep_filter_binary
from motion_studio.cli import app
from motion_studio.media.ffmpeg import run_ffmpeg, run_ffprobe
from motion_studio.render.renderer import find_renderer, remotion_bin

pytestmark = [pytest.mark.slow, pytest.mark.mac, pytest.mark.models, pytest.mark.renderer]

MEDIA = Path(__file__).resolve().parents[1] / "fixtures" / "media"
SIZES = {"9x16": (540, 960), "16x9": (960, 540)}

runner = CliRunner()


def run(*args: str) -> Any:
    result = runner.invoke(app, [*args, "--json"])
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


def frames_and_size(path: Path) -> tuple[int, int, int]:
    out = run_ffprobe(["-v", "error", "-count_frames", "-show_streams", "-of", "json", path])
    video = next(s for s in json.loads(out)["streams"] if s["codec_type"] == "video")
    return int(video["nb_read_frames"]), int(video["width"]), int(video["height"])


def ebur128(path: Path) -> tuple[float, float]:
    lines = run_ffmpeg(["-i", path, "-map", "0:a", "-af", "ebur128=peak=true", "-f", "null", "-"])
    summary = "\n".join(lines[-15:])
    integrated = re.search(r"I:\s+(-?[\d.]+) LUFS", summary)
    peak = re.search(r"Peak:\s+(-?[\d.]+) dBFS", summary)
    assert integrated and peak, summary
    return float(integrated.group(1)), float(peak.group(1))


def add_events(project: Path) -> dict[str, Any]:
    """A title over the first words, a zoom in the middle and a B-roll card later on."""
    timeline = json.loads((project / "build" / "timeline.json").read_text(encoding="utf-8"))
    ids = [w["id"] for w in timeline["words"]]
    edl = json.loads((project / "edl.json").read_text(encoding="utf-8"))
    edl["formats"] = ["9x16", "16x9"]
    edl["events"] = [
        {"type": "title", "text": "Fixture test", "start": ids[0], "end": ids[3]},
        {"type": "zoom", "at": ids[8], "hold_until": ids[12], "scale": 1.25, "ease": "snap"},
        {"type": "broll", "asset": "b1", "start": ids[16], "end": ids[20], "mode": "pip"},
    ]
    (project / "edl.json").write_text(json.dumps(edl, indent=2), encoding="utf-8")
    return edl


@pytest.fixture(scope="module", params=["en", "it"])
def planned(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[tuple[str, Path]]:
    language: str = request.param
    source = MEDIA / f"{language}_talking.mov"
    if not source.exists():
        pytest.skip("fixtures not generated; run `just fixtures`")
    backend = resolve_backend("auto")
    if not vad_model_path().is_file() or model_path(DEFAULT_MODELS[backend]) is None:  # type: ignore[index]
        pytest.skip("speech models not in the cache; run `motion-studio setup`")
    find_renderer()
    with pytest.MonkeyPatch.context() as monkeypatch:
        deep_filter = deep_filter_binary()
        if deep_filter:
            monkeypatch.setenv("MOTION_STUDIO_DEEP_FILTER", str(deep_filter))
        monkeypatch.setenv("MOTION_STUDIO_MIN_FREE_GB", "0")
        workspace = tmp_path_factory.mktemp(language) / "reels"
        run("init", str(workspace))
        logo = Image.new("RGBA", (240, 240), (0, 0, 0, 0))
        ImageDraw.Draw(logo).ellipse((8, 8, 232, 232), fill=(255, 212, 0, 255))
        logo.save(workspace / "library" / "brand" / "logo.png")
        monkeypatch.chdir(workspace)
        run("new", "demo", "--from", str(source), str(MEDIA / "broll.mp4"))
        run("ingest", "demo")
        run("analyze", "demo")
        run("plan", "draft", "demo")
        project = workspace / "projects" / "demo"
        run("plan", "validate", "demo")
        add_events(project)
        if language == "en":
            edl = json.loads((project / "edl.json").read_text(encoding="utf-8"))
            edl["music"]["mode"] = "none"
            (project / "edl.json").write_text(json.dumps(edl, indent=2), encoding="utf-8")
        run("plan", "validate", "demo")
        if language == "it":
            # A tone bed stands in for `motion-studio music` (#14) at the path the timeline names.
            run_ffmpeg(
                [
                    "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=48000", "-t", "5",
                    "-af", "volume=-6dB", "-ac", "2", project / "build" / "music.wav",
                ]
            )  # fmt: skip
        yield language, project


def test_preview_is_a_half_size_file_per_format_lasting_the_timeline(
    planned: tuple[str, Path],
) -> None:
    language, project = planned

    out = run("render", "demo", "--preview")

    timeline = json.loads((project / "build" / "timeline.json").read_text(encoding="utf-8"))
    for item in out["outputs"]:
        frames, width, height = frames_and_size(Path(item["path"]))
        assert (width, height) == SIZES[item["format"]]
        assert abs(frames - timeline["duration_frames"]) <= 1, (language, item)
    stills = os.environ.get("MOTION_STUDIO_RENDER_STILLS")
    if stills:
        write_stills(project, timeline, Path(stills) / language)


def test_final_measures_minus_14_lufs_and_under_minus_1_dbtp(planned: tuple[str, Path]) -> None:
    _, project = planned

    out = run("render", "demo", "--final", "--format", "9x16")

    [item] = out["outputs"]
    path = Path(item["path"])
    assert path == project / "final" / "demo_9x16.mp4"
    _, width, height = frames_and_size(path)
    assert (width, height) == (1080, 1920)
    integrated, peak = ebur128(path)
    print(f"{path.name}: {integrated} LUFS, {peak} dBTP")
    assert abs(integrated + 14) <= 1
    assert peak <= -1


def write_stills(project: Path, timeline: dict[str, Any], out_dir: Path) -> None:
    """Full-size stills of each format at the start, just after the first cut and mid-zoom."""
    import subprocess

    out_dir.mkdir(parents=True, exist_ok=True)
    renderer = find_renderer()
    zoom = next(e for e in timeline["events"] if e["type"] == "zoom")
    frames = {
        "start": 15,
        "cut": timeline["runs"][1]["out_in"] + 3,
        "zoom": (zoom["start"] + zoom["end"]) // 2,
    }
    for fmt in ("9x16", "16x9"):
        for name, frame in frames.items():
            argv = [
                str(remotion_bin(renderer)), "still", "src/index.ts", "Reel",
                str(out_dir / f"{fmt}_{name}.png"),
                f"--props={project / 'build' / f'props_{fmt}.json'}",
                f"--public-dir={project / 'build' / 'public'}",
                f"--frame={frame}", "--log=error",
            ]  # fmt: skip
            subprocess.run(argv, cwd=renderer, check=True, capture_output=True, timeout=600)
