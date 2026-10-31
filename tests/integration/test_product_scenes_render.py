"""`render --final` of kinetic text, terminal footage, a proof shot and a logo outro, in Remotion.

Synthetic inputs keep the stills checkable: a solid-green recording, a solid-magenta proof image,
and a 4x4 pixel mascot of red and blue squares whose frames swap the colours.
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
MAGENTA = (220, 30, 140)
RED = (230, 30, 30)
BLUE = (30, 30, 230)
YELLOW = (255, 212, 0)
TERMINAL_BAR = (42, 42, 60)
BRAND_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "brand"
# Each frame is 4x4 pixels; frame 0 has red in its top-left corner, frame 1 blue.
MASCOT_TIMINGS = {
    "frame_width": 4,
    "frame_height": 4,
    "frames": [{"x": 0, "y": 0, "ms": 700}, {"x": 4, "y": 0, "ms": 700}],
}
BRAND_TOML = """
[brand]
wordmark = "library/brand/wordmark.svg"
mascot = { sheet = "library/brand/mascot.png", timings = "library/brand/mascot.json" }
"""
EDL: dict[str, Any] = {
    "kind": "product",
    "title": "Launch",
    "scenes": [
        {
            "id": "intro",
            "type": "kinetic_text",
            "beats": 6,
            "lines": ["Got an idea?", "Turning it into a post…", "…is the hard part."],
            "accent": ["idea?", "hard"],
        },
        {
            "id": "term",
            "type": "footage",
            "clip": "c1",
            "from": "c1.m.open",
            "to": "c1.m.done",
            "beats": 8,
            "device_frame": "terminal",
            "address": "claude",
        },
        {
            "id": "posted",
            "type": "proof",
            "beats": 6,
            "image": "i1",
            "headline": "Live on X.",
            "accent": ["X."],
            "subline": "One click.",
            "badge": "Posted",
        },
        {
            "id": "outro",
            "type": "logo_outro",
            "bars": 2,
            "tagline": "Write like the people you admire.",
            "accent": ["admire."],
            "url": "example.com",
        },
    ],
    "music": {"mode": "none"},
    "rationale": "Every scene type #35 adds.",
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
    sidecar = {
        "schema_version": 1,
        "width": 1600,
        "height": 900,
        "markers": [{"name": "open", "t": 0.5}, {"name": "done", "t": 4.5}],
    }
    path.with_suffix(".markers.json").write_text(json.dumps(sidecar), encoding="utf-8")
    return path


def mascot_sheet(path: Path) -> None:
    sheet = Image.new("RGB", (8, 4))
    for x in range(8):
        for y in range(4):
            sheet.putpixel((x, y), RED if (x // 4 + x + y) % 2 == 0 else BLUE)
    sheet.save(path)


@pytest.fixture(scope="module")
def video(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[Path, dict[str, float]]]:
    find_renderer()
    scratch = tmp_path_factory.mktemp("scenes")
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("MOTION_STUDIO_MIN_FREE_GB", "0")
        workspace = scratch / "videos"
        run("init", workspace)
        monkeypatch.chdir(workspace)
        clip = recording(scratch / "take.mp4")
        run("new", "launch", "--kind", "product", "--from", clip)
        project = workspace / "projects" / "launch"
        shutil.copy(clip.with_suffix(".markers.json"), project / "raw" / "take.markers.json")
        Image.new("RGB", (1200, 900), MAGENTA).save(project / "raw" / "post.png")
        brand = workspace / "library" / "brand"
        shutil.copy(BRAND_FIXTURES / "wordmark.svg", brand / "wordmark.svg")
        mascot_sheet(brand / "mascot.png")
        (brand / "mascot.json").write_text(json.dumps(MASCOT_TIMINGS), encoding="utf-8")
        (project / "project.toml").open("a", encoding="utf-8").write(BRAND_TOML)
        run("ingest", "launch")
        run("analyze", "launch")
        (project / "edl.json").write_text(json.dumps(EDL), encoding="utf-8")
        run("plan", "validate", "launch")
        out = run("render", "launch", "--final")
        timeline = json.loads((project / "build" / "timeline.json").read_text(encoding="utf-8"))
        mid = {s["id"]: (s["start"] + s["end"]) / 2 / timeline["fps"] for s in timeline["scenes"]}
        yield Path(out["outputs"][0]["path"]), mid


def still(video: Path, seconds: float, out: Path) -> Image.Image:
    run_ffmpeg(["-ss", f"{seconds:.3f}", "-i", video, "-frames:v", "1", "-y", out])
    return Image.open(out).convert("RGB")


def at(image: Image.Image, x: int, y: int) -> tuple[int, int, int]:
    value = image.getpixel((x, y))
    assert isinstance(value, tuple)
    return value[0], value[1], value[2]


def near(pixel: tuple[int, ...], colour: tuple[int, int, int], tolerance: int = 24) -> bool:
    return all(abs(a - b) <= tolerance for a, b in zip(pixel, colour, strict=False))


def luminance(pixel: tuple[int, ...]) -> float:
    r, g, b = pixel[:3]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def region(image: Image.Image, x0: int, y0: int, x1: int, y1: int, step: int = 4):
    return [at(image, x, y) for x in range(x0, x1, step) for y in range(y0, y1, step)]


def test_kinetic_text_draws_its_line_on_the_backdrop(
    video: tuple[Path, dict[str, float]], tmp_path: Path
) -> None:
    path, mid = video
    image = still(path, mid["intro"], tmp_path / "intro.png")

    assert luminance(at(image, 40, 40)) < 80
    assert max(luminance(p) for p in region(image, 200, 400, 1720, 680)) > 200


def test_terminal_footage_sits_under_a_dark_title_bar(
    video: tuple[Path, dict[str, float]], tmp_path: Path
) -> None:
    path, mid = video
    image = still(path, mid["term"], tmp_path / "term.png")

    # At rest the 1600x944 frame is centred: bar from y 68 to 112, content to 1012.
    assert near(at(image, 960, 560), GREEN)
    assert near(at(image, 400, 90), TERMINAL_BAR)


def test_a_proof_shows_its_image_right_of_the_headline_with_its_badge(
    video: tuple[Path, dict[str, float]], tmp_path: Path
) -> None:
    path, mid = video
    image = still(path, mid["posted"], tmp_path / "posted.png")

    assert near(at(image, 1320, 540), MAGENTA)
    assert not any(near(p, MAGENTA) for p in region(image, 130, 300, 760, 780))
    assert max(luminance(p) for p in region(image, 130, 300, 760, 780)) > 200
    assert any(near(p, YELLOW, 40) for p in region(image, 1500, 60, 1900, 320, 2))


def test_the_logo_outro_draws_the_pixel_art_mascot_crisp_at_its_frame_timing(
    video: tuple[Path, dict[str, float]], tmp_path: Path
) -> None:
    path, mid = video
    image = still(path, mid["outro"], tmp_path / "outro.png")

    sprite = [
        (x, y)
        for x in range(0, 1920, 2)
        for y in range(0, 1080, 2)
        if near(at(image, x, y), RED, 40) or near(at(image, x, y), BLUE, 40)
    ]
    xs, ys = [x for x, _ in sprite], [y for _, y in sprite]
    left, top, right, bottom = min(xs), min(ys), max(xs), max(ys)
    # 300 px tall at rest, 4 px squares scaled to 75 px.
    assert 280 <= bottom - top <= 320
    assert 280 <= right - left <= 320
    # Smoothing would blend the squares into purple ramps; nearest-neighbour keeps them pure.
    box = region(image, left + 2, top + 2, right - 2, bottom - 2, 3)
    pure = sum(1 for p in box if near(p, RED, 40) or near(p, BLUE, 40))
    assert pure / len(box) > 0.9
    # 1.87 s into the sprite (it starts 4 frames late) is frame 0, red in the top-left corner.
    assert near(at(image, left + 37, top + 37), RED, 40)
    assert near(at(image, right - 37, top + 37), BLUE, 40)
