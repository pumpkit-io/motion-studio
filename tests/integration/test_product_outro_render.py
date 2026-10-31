"""`render --final` of a logo outro with a GIF mascot and no wordmark, in Remotion.

The GIF is 4x4 pixels: frame 0 is red on the left half and blue on the right, frame 1 swapped.
"""

import json
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

RED = (230, 30, 30)
BLUE = (30, 30, 230)
EDL: dict[str, Any] = {
    "kind": "product",
    "title": "Pumpkit",
    "scenes": [{"id": "outro", "type": "logo_outro", "bars": 2, "url": "example.com"}],
    "music": {"mode": "none"},
}

runner = CliRunner()


def run(*args: str | Path) -> Any:
    result = runner.invoke(app, [*(str(a) for a in args), "--json"])
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


def mascot_gif(path: Path) -> None:
    frames = []
    for left, right in ((RED, BLUE), (BLUE, RED)):
        frame = Image.new("RGB", (4, 4))
        for x in range(4):
            for y in range(4):
                frame.putpixel((x, y), left if x < 2 else right)
        frames.append(frame)
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=700, loop=0)


@pytest.fixture(scope="module")
def outro(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Image.Image]:
    find_renderer()
    scratch = tmp_path_factory.mktemp("outro")
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("MOTION_STUDIO_MIN_FREE_GB", "0")
        workspace = scratch / "videos"
        run("init", workspace)
        monkeypatch.chdir(workspace)
        run("new", "launch", "--kind", "product")
        project = workspace / "projects" / "launch"
        mascot_gif(workspace / "library" / "brand" / "mascot.gif")
        (project / "project.toml").open("a", encoding="utf-8").write(
            '\n[brand]\nmascot = { gif = "library/brand/mascot.gif" }\n'
        )
        # Analysis needs one clip, though the outro draws none.
        Image.new("RGB", (1200, 900), (90, 90, 90)).save(project / "raw" / "post.png")
        run("ingest", "launch")
        run("analyze", "launch")
        (project / "edl.json").write_text(json.dumps(EDL), encoding="utf-8")
        run("plan", "validate", "launch")
        out = run("render", "launch", "--final")
        timeline = json.loads((project / "build" / "timeline.json").read_text(encoding="utf-8"))
        (scene,) = timeline["scenes"]
        mid = (scene["start"] + scene["end"]) / 2 / timeline["fps"]
        image = scratch / "outro.png"
        run_ffmpeg(
            ["-ss", f"{mid:.3f}", "-i", out["outputs"][0]["path"], "-frames:v", "1", "-y", image]
        )
        yield Image.open(image).convert("RGB")


def at(image: Image.Image, x: int, y: int) -> tuple[int, int, int]:
    value = image.getpixel((x, y))
    assert isinstance(value, tuple)
    return value[0], value[1], value[2]


def near(pixel: tuple[int, int, int], colour: tuple[int, int, int], tolerance: int = 40) -> bool:
    return all(abs(a - b) <= tolerance for a, b in zip(pixel, colour, strict=True))


def mascot_box(image: Image.Image) -> tuple[int, int, int, int]:
    sprite = [
        (x, y)
        for x in range(0, 1920, 2)
        for y in range(0, 1080, 2)
        if near(at(image, x, y), RED) or near(at(image, x, y), BLUE)
    ]
    xs, ys = [x for x, _ in sprite], [y for _, y in sprite]
    return min(xs), min(ys), max(xs), max(ys)


def test_the_gif_mascot_is_drawn_crisp_at_its_own_delays(outro: Image.Image) -> None:
    left, top, right, bottom = mascot_box(outro)

    # 300 px tall at rest, 4 px squares scaled to 75 px.
    assert 280 <= bottom - top <= 320
    assert 280 <= right - left <= 320
    box = [
        at(outro, x, y)
        for x in range(left + 2, right - 2, 3)
        for y in range(top + 2, bottom - 2, 3)
    ]
    pure = sum(1 for p in box if near(p, RED) or near(p, BLUE))
    assert pure / len(box) > 0.9
    # 1.87 s into the GIF (it starts 4 frames late) is frame 0, red on the left.
    assert near(at(outro, left + 37, top + 150), RED)
    assert near(at(outro, right - 37, top + 150), BLUE)


def test_without_a_wordmark_the_title_is_set_in_type_beside_the_mascot(
    outro: Image.Image,
) -> None:
    _, top, right, bottom = mascot_box(outro)

    text = [at(outro, x, y) for x in range(right + 20, 1900, 3) for y in range(top, bottom, 3)]
    assert sum(1 for r, g, b in text if min(r, g, b) > 200) > 200
