"""`plan draft` on a product project with two recordings and an image, rendered in Remotion.

A solid-green and a solid-blue recording and a solid-magenta image keep the stills checkable.
"""

import json
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from PIL import Image
from typer.testing import CliRunner

from motion_studio.cli import app
from motion_studio.media.ffmpeg import run_ffmpeg
from motion_studio.render.renderer import find_renderer

pytestmark = [pytest.mark.slow, pytest.mark.renderer]

GREEN = (46, 160, 67)
BLUE = (40, 90, 220)
MAGENTA = (220, 30, 140)
BRAND_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "brand"

runner = CliRunner()


def run(*args: str | Path) -> Any:
    result = runner.invoke(app, [*(str(a) for a in args), "--json"])
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


def recording(path: Path, colour: tuple[int, int, int], markers: dict[str, float]) -> Path:
    hex_colour = "0x{:02X}{:02X}{:02X}".format(*colour)
    run_ffmpeg(
        [
            "-f", "lavfi", "-i", f"color=c={hex_colour}:size=1600x900:rate=30:duration=4",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-y", path,
        ]
    )  # fmt: skip
    sidecar = {
        "schema_version": 1,
        "width": 1600,
        "height": 900,
        "markers": [{"name": n, "t": t} for n, t in markers.items()],
        "cursor": [{"t": 0.0, "x": 1500, "y": 800}],
    }
    path.with_suffix(".markers.json").write_text(json.dumps(sidecar), encoding="utf-8")
    return path


@pytest.fixture(scope="module")
def video(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[Path, dict[str, float]]]:
    find_renderer()
    scratch = tmp_path_factory.mktemp("draft")
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("MOTION_STUDIO_MIN_FREE_GB", "0")
        workspace = scratch / "videos"
        run("init", workspace)
        monkeypatch.chdir(workspace)
        first = recording(scratch / "pick.mp4", GREEN, {"open": 0.5, "done": 3.5})
        second = recording(scratch / "post.mp4", BLUE, {"start": 0.5, "posted": 3.0})
        run("new", "launch", "--kind", "product", "--from", first)
        project = workspace / "projects" / "launch"
        shutil.copy(second, project / "raw" / "post.mp4")
        for clip in (first, second):
            sidecar = clip.with_suffix(".markers.json")
            shutil.copy(sidecar, project / "raw" / sidecar.name)
        Image.new("RGB", (1200, 900), MAGENTA).save(project / "raw" / "proof.png")
        shutil.copy(BRAND_FIXTURES / "wordmark.svg", workspace / "library" / "brand")
        with (project / "project.toml").open("a", encoding="utf-8") as toml:
            toml.write('\n[brand]\nwordmark = "library/brand/wordmark.svg"\n')
        run("ingest", "launch")
        run("analyze", "launch")
        run("plan", "draft", "launch")
        edl = json.loads((project / "edl.json").read_text(encoding="utf-8"))
        (project / "edl.json").write_text(
            json.dumps({**edl, "music": {"mode": "none"}}), encoding="utf-8"
        )
        assert run("plan", "validate", "launch")["warnings"] == []
        out = run("render", "launch", "--final")
        timeline = json.loads((project / "build" / "timeline.json").read_text(encoding="utf-8"))
        mid = {s["id"]: (s["start"] + s["end"]) / 2 / timeline["fps"] for s in timeline["scenes"]}
        yield Path(out["outputs"][0]["path"]), mid


def still(video: Path, seconds: float, out: Path) -> tuple[int, int, int]:
    run_ffmpeg(["-ss", f"{seconds:.3f}", "-i", video, "-frames:v", "1", "-y", out])
    value = Image.open(out).convert("RGB").getpixel((960, 560))
    assert isinstance(value, tuple)
    return value[0], value[1], value[2]


def near(pixel: tuple[int, int, int], colour: tuple[int, int, int], tolerance: int = 24) -> bool:
    return all(abs(a - b) <= tolerance for a, b in zip(pixel, colour, strict=True))


def test_the_draft_renders_every_scene_in_order(video: tuple[Path, dict[str, float]]) -> None:
    _, mid = video

    assert list(mid) == ["intro", "step1", "demo1", "step2", "demo2", "proof1", "outro"]


def test_each_recording_plays_in_its_own_footage_scene(
    video: tuple[Path, dict[str, float]], tmp_path: Path
) -> None:
    path, mid = video

    assert near(still(path, mid["demo1"], tmp_path / "demo1.png"), GREEN)
    assert near(still(path, mid["demo2"], tmp_path / "demo2.png"), BLUE)


def test_the_image_is_the_proof_shot(video: tuple[Path, dict[str, float]], tmp_path: Path) -> None:
    path, mid = video
    image = tmp_path / "proof.png"
    still(path, mid["proof1"], image)

    pixels = Image.open(image).convert("RGB")
    assert any(
        near(pixels.getpixel((x, 540)), MAGENTA)  # type: ignore[arg-type]
        for x in range(600, 1500, 20)
    )
