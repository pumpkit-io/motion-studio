"""The Remotion CLI renders a hand-made timeline over test media (guide phase 7b).

Set MOTION_STUDIO_RENDER_STILLS=<dir> to also write the start, cut, zoom and overlay stills there.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from motion_studio.edl import Timeline
from motion_studio.media.ffmpeg import run_ffmpeg, run_ffprobe

pytestmark = [pytest.mark.slow, pytest.mark.renderer]

ROOT = Path(__file__).resolve().parents[2]
RENDERER = ROOT / "renderer"
FIXTURES = ROOT / "tests" / "fixtures"
TIMELINE = FIXTURES / "renderer" / "timeline.json"
FACE = FIXTURES / "faces" / "neil_armstrong_960.jpg"
# The photo scaled to 1536x1920 and cropped 200 px from the left puts the face at (0.689, 0.267).
SOURCE = {"width": 1080, "height": 1920}
STILLS = {"start": 20, "cut": 46, "zoom": 70, "image": 110}


def remotion(*args: str | Path) -> None:
    npx = shutil.which("npx")
    assert npx, "node is not installed"
    cmd = [npx, "remotion", *map(str, args), "--log=error"]
    result = subprocess.run(cmd, cwd=RENDERER, capture_output=True, text=True, timeout=600)
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]


def video_stream(path: Path) -> dict[str, Any]:
    out = run_ffprobe(["-v", "error", "-count_frames", "-show_streams", "-of", "json", path])
    return next(s for s in json.loads(out)["streams"] if s["codec_type"] == "video")


@pytest.fixture(scope="module")
def public(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if not (RENDERER / "node_modules").exists():
        pytest.skip("renderer dependencies missing; run `just setup`")
    public = tmp_path_factory.mktemp("public")
    (public / "media").mkdir()
    run_ffmpeg(
        [
            "-loop", "1", "-framerate", "30", "-i", FACE,
            "-f", "lavfi", "-i", "sine=frequency=330:sample_rate=48000", "-t", "4",
            "-vf", "scale=1536:1920,crop=1080:1920:200:0,format=yuv420p",
            "-c:v", "libx264", "-crf", "20", "-c:a", "aac", "-shortest", public / "assembled.mp4",
        ]
    )  # fmt: skip
    run_ffmpeg(
        [
            "-f", "lavfi", "-i", "testsrc2=size=1920x1080:rate=30", "-t", "3",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", public / "media" / "b1.mp4",
        ]
    )  # fmt: skip
    run_ffmpeg(
        [
            "-f",
            "lavfi",
            "-i",
            "mandelbrot=size=1600x1200",
            "-frames:v",
            "1",
            public / "media" / "i1.png",
        ]
    )
    return public


def props(tmp_path: Path, fmt: str) -> Path:
    timeline = json.loads(TIMELINE.read_text())
    Timeline.model_validate(timeline)
    path = tmp_path / f"props_{fmt}.json"
    data = {
        "timeline": timeline,
        "format": fmt,
        "source": SOURCE,
        "regions": {"c1": {"x": 0, "y": 0, **SOURCE}},
        "video": "assembled.mp4",
        "font_file": None,
        "bundled_font": "Inter",
        "logo_file": None,
    }
    path.write_text(json.dumps(data))
    return path


@pytest.mark.parametrize(
    ("fmt", "scale", "size"),
    [("9x16", "1", (1080, 1920)), ("16x9", "1", (1920, 1080)), ("16x9", "0.5", (960, 540))],
)
def test_renders_each_format_at_its_size_and_frame_count(
    tmp_path: Path, public: Path, fmt: str, scale: str, size: tuple[int, int]
) -> None:
    out = tmp_path / f"composed_{fmt}.mp4"
    remotion(
        "render", "src/index.ts", "Reel", out,
        f"--props={props(tmp_path, fmt)}", f"--public-dir={public}",
        "--concurrency=4", "--codec=h264", "--crf=16", f"--scale={scale}",
    )  # fmt: skip
    video = video_stream(out)
    assert (video["width"], video["height"]) == size
    assert int(video["nb_read_frames"]) == json.loads(TIMELINE.read_text())["duration_frames"]
    assert video["avg_frame_rate"] == "30/1"

    stills = os.environ.get("MOTION_STUDIO_RENDER_STILLS")
    if stills and scale == "1":
        Path(stills).mkdir(parents=True, exist_ok=True)
        for name, frame in STILLS.items():
            png = Path(stills) / f"{fmt}_{name}.png"
            remotion(
                "still", "src/index.ts", "Reel", png,
                f"--props={props(tmp_path, fmt)}", f"--public-dir={public}", f"--frame={frame}",
            )  # fmt: skip
