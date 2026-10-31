"""`motion-studio render` of a product EDL with the real Remotion renderer.

A solid-green 1600x900 clip with a markers sidecar stands in for a `record web` take, so the
stills show whether the footage sits in its browser frame and the title cards on the backdrop.
Uses the repo's renderer (`just setup`) or the cache's (`motion-studio setup`).
"""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from PIL import Image
from typer.testing import CliRunner

from motion_studio.cli import app
from motion_studio.media.ffmpeg import run_ffmpeg, run_ffprobe
from motion_studio.render.renderer import find_renderer

pytestmark = [pytest.mark.slow, pytest.mark.renderer]

GREEN = (46, 160, 67)
MARKERS = {"open": 0.5, "typed": 2.5, "done": 4.5}
EDL: dict[str, Any] = {
    "kind": "product",
    "title": "Launch",
    "scenes": [
        {"id": "intro", "type": "title_card", "beats": 4, "headline": "Meet the app."},
        {
            "id": "step1",
            "type": "title_card",
            "beats": 4,
            "step": "01",
            "headline": "Pick who inspires you.",
            "accent": ["inspires"],
            "subline": "Up to three authors.",
        },
        {
            "id": "pick",
            "type": "footage",
            "clip": "c1",
            "from": "c1.m.open",
            "to": "c1.m.done",
            "beats": 8,
            "address": "example.com",
        },
    ],
    "music": {"mode": "none"},
    "rationale": "Intro, a numbered step, then its footage.",
}

runner = CliRunner()


def run(*args: str | Path) -> Any:
    result = runner.invoke(app, [*(str(a) for a in args), "--json"])
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


def recording(path: Path) -> Path:
    colour = "0x{:02X}{:02X}{:02X}".format(*GREEN)
    run_ffmpeg(
        [
            "-f", "lavfi", "-i", f"color=c={colour}:size=1600x900:rate=30:duration=5",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-y", path,
        ]
    )  # fmt: skip
    return path


@pytest.fixture(scope="module")
def launch(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    find_renderer()
    scratch = tmp_path_factory.mktemp("product")
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("MOTION_STUDIO_MIN_FREE_GB", "0")
        workspace = scratch / "videos"
        run("init", workspace)
        monkeypatch.chdir(workspace)
        run("new", "launch", "--kind", "product", "--from", recording(scratch / "take.mp4"))
        project = workspace / "projects" / "launch"
        sidecar = {
            "schema_version": 1,
            "width": 1600,
            "height": 900,
            "markers": [{"name": n, "t": t} for n, t in MARKERS.items()],
        }
        (project / "raw" / "take.markers.json").write_text(json.dumps(sidecar), encoding="utf-8")
        run("ingest", "launch")
        run("analyze", "launch")
        (project / "edl.json").write_text(json.dumps(EDL), encoding="utf-8")
        run("plan", "validate", "launch")
        yield project


def still(video: Path, seconds: float, out: Path) -> Image.Image:
    run_ffmpeg(["-ss", f"{seconds:.3f}", "-i", video, "-frames:v", "1", "-y", out])
    return Image.open(out).convert("RGB")


def at(image: Image.Image, x: int, y: int) -> tuple[int, ...]:
    value = image.getpixel((x, y))
    assert isinstance(value, tuple)
    return value


def near(pixel: tuple[int, ...], colour: tuple[int, int, int], tolerance: int = 24) -> bool:
    return all(abs(a - b) <= tolerance for a, b in zip(pixel, colour, strict=False))


def luminance(pixel: tuple[int, ...]) -> float:
    r, g, b = pixel[:3]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def frames_and_size(path: Path) -> tuple[int, int, int]:
    out = run_ffprobe(["-v", "error", "-count_frames", "-show_streams", "-of", "json", path])
    video = next(s for s in json.loads(out)["streams"] if s["codec_type"] == "video")
    return int(video["nb_read_frames"]), int(video["width"]), int(video["height"])


def test_preview_is_a_half_size_16x9_video_lasting_the_timeline(launch: Path) -> None:
    out = run("render", "launch")

    [item] = out["outputs"]
    frames, width, height = frames_and_size(Path(item["path"]))
    assert (width, height) == (960, 540)
    assert abs(frames - 240) <= 1


def test_final_stills_show_title_cards_on_the_backdrop_and_footage_in_its_frame(
    launch: Path, tmp_path: Path
) -> None:
    out = run("render", "launch", "--final")

    [item] = out["outputs"]
    video = Path(item["path"])
    _, width, height = frames_and_size(video)
    assert (width, height) == (1920, 1080)
    timeline = json.loads((launch / "build" / "timeline.json").read_text(encoding="utf-8"))
    mid = {s["id"]: (s["start"] + s["end"]) / 2 / timeline["fps"] for s in timeline["scenes"]}

    for card in ("intro", "step1"):
        image = still(video, mid[card], tmp_path / f"{card}.png")
        assert luminance(at(image, 40, 40)) < 80, card
        band = [at(image, x, y) for x in range(200, 1720, 4) for y in range(440, 640, 4)]
        assert max(luminance(p) for p in band) > 200, card
        assert not any(near(p, GREEN) for p in band), card

    footage = still(video, mid["pick"], tmp_path / "pick.png")
    # At rest the 1600x944 frame is centred: content from (160, 112) to (1760, 1012).
    assert near(at(footage, 960, 560), GREEN)
    assert near(at(footage, 200, 980), GREEN)
    assert luminance(at(footage, 960, 90)) > 200
    assert not near(at(footage, 80, 560), GREEN)
    assert Path(item["share"]["path"]).is_file()
