"""`motion-studio record web` end to end: the static fixture page recorded in headless Chromium.

Uses the real cache and installs Playwright there with `setup --record` when it is missing.
"""

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image
from typer.testing import CliRunner

from motion_studio.cli import app
from motion_studio.media.ffmpeg import run_ffmpeg, run_ffprobe

pytestmark = [pytest.mark.record]

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "record"
# The boxes page.html lays out with absolute positions, in CSS pixels of the 1600x900 viewport.
LAYOUT = {
    "title": (100, 80, 600, 60),
    "body": (100, 180, 700, 120),
    "go": (1200, 600, 200, 60),
    "result": (900, 200, 400, 150),
}

runner = CliRunner()


def invoke(*args: str | Path):
    return runner.invoke(app, [str(a) for a in args])


def run_json(*args: str | Path) -> dict[str, Any]:
    result = invoke(*args, "--json")
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


@pytest.fixture(scope="module", autouse=True)
def recorder() -> None:
    result = invoke("setup", "--record", "--json")
    assert result.exit_code == 0, result.output


@pytest.fixture
def product(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("MOTION_STUDIO_MIN_FREE_GB", "0")
    ws = tmp_path / "vidéos de démo"
    assert invoke("init", ws).exit_code == 0
    monkeypatch.chdir(ws)
    run_json("new", "launch", "--kind", "product")
    return ws / "projects" / "launch"


@pytest.fixture
def take(product: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    reference = tmp_path / "reference.png"
    monkeypatch.setenv("RECORD_REFERENCE", str(reference))
    out = run_json("record", "web", "launch", FIXTURES / "take.mjs")
    out["reference"] = reference
    out["markers_json"] = json.loads(Path(out["sidecar"]).read_text(encoding="utf-8"))
    return out


def still(clip: Path, t: float, out: Path) -> np.ndarray:
    run_ffmpeg(["-i", clip, "-ss", f"{t:.3f}", "-frames:v", "1", "-y", out])
    return np.asarray(Image.open(out).convert("RGB"), dtype=np.float64)


def marker(take: dict[str, Any], name: str) -> dict[str, Any]:
    return next(m for m in take["markers_json"]["markers"] if m["name"] == name)


def test_the_take_is_a_constant_frame_rate_clip_in_raw(product: Path, take: dict[str, Any]) -> None:
    clip = Path(take["clip"])
    assert clip == product / "raw" / "take.mp4"
    stream = json.loads(
        run_ffprobe(["-v", "error", "-count_frames", "-show_streams", "-of", "json", clip])
    )["streams"][0]

    assert (stream["width"], stream["height"]) == (1600, 900)
    assert stream["r_frame_rate"] == stream["avg_frame_rate"] == "30/1"
    assert int(stream["nb_read_frames"]) == pytest.approx(take["duration_s"] * 30, abs=2)
    assert take["frames"] == int(stream["nb_read_frames"])
    assert sorted(p.name for p in (product / "raw").iterdir()) == ["take.markers.json", "take.mp4"]
    assert not (product / "build" / "record").exists() or not any(
        (product / "build" / "record").iterdir()
    )


def test_the_sidecar_boxes_match_the_page_layout(take: dict[str, Any]) -> None:
    sidecar = take["markers_json"]

    assert (sidecar["width"], sidecar["height"]) == (1600, 900)
    assert [m["name"] for m in sidecar["markers"]] == ["start", "clicked", "shown", "end"]
    boxes = {
        e["name"]: (e["x"], e["y"], e["w"], e["h"])
        for m in sidecar["markers"]
        for e in m["elements"]
    }
    assert boxes == LAYOUT


def test_markers_are_on_the_frames_clock(
    product: Path, take: dict[str, Any], tmp_path: Path
) -> None:
    clip = Path(take["clip"])
    x, y, w, h = LAYOUT["result"]
    press = next(s["t"] for s in take["markers_json"]["cursor"] if s["down"])

    before = still(clip, press - 0.15, tmp_path / "before.png")[y : y + h, x : x + w]
    after = still(clip, marker(take, "clicked")["t"], tmp_path / "after.png")[y : y + h, x : x + w]

    assert before.mean() > 200
    assert after.mean() < 40


def test_the_cursor_track_is_in_the_sidecar_and_the_cursor_is_in_the_frames(
    take: dict[str, Any], tmp_path: Path
) -> None:
    cursor = take["markers_json"]["cursor"]
    gx, gy, gw, gh = LAYOUT["go"]
    press = next(s for s in cursor if s["down"])
    assert gx <= press["x"] <= gx + gw and gy <= press["y"] <= gy + gh

    last = cursor[-1]
    frame = still(Path(take["clip"]), marker(take, "end")["t"], tmp_path / "end.png")
    x, y = round(last["x"]), round(last["y"])
    arrow = frame[y + 5 : y + 10, x + 2 : x + 6]
    assert arrow.mean() < 90


def test_park_moves_the_cursor_off_the_region(take: dict[str, Any]) -> None:
    x, y, w, h = LAYOUT["result"]
    last = take["markers_json"]["cursor"][-1]

    inside_x = x - 40 <= last["x"] <= x + w + 40
    inside_y = y - 40 <= last["y"] <= y + h + 40
    assert not (inside_x and inside_y)


def test_text_stays_sharp_at_2x_zoom(take: dict[str, Any], tmp_path: Path) -> None:
    x, y, w, h = LAYOUT["body"]
    frame = still(Path(take["clip"]), marker(take, "end")["t"] - 0.05, tmp_path / "text.png")
    reference = np.asarray(Image.open(take["reference"]).convert("RGB"), dtype=np.float64)

    def zoomed(pixels: np.ndarray) -> np.ndarray:
        crop = Image.fromarray(pixels[y : y + h, x : x + w].astype(np.uint8))
        return np.asarray(crop.resize((w * 2, h * 2), Image.Resampling.LANCZOS), dtype=np.float64)

    mse = np.mean((zoomed(frame) - zoomed(reference)) ** 2)
    psnr = 10 * np.log10(255**2 / max(mse, 1e-9))
    assert psnr > 30


def test_a_script_that_throws_exits_1_with_its_error_and_adds_no_clip(product: Path) -> None:
    result = invoke("record", "web", "launch", FIXTURES / "fails.mjs")

    assert result.exit_code == 1
    assert "the product is down" in result.output
    assert "fails.mjs" in result.output
    assert list((product / "raw").iterdir()) == []
    assert not any((product / "build").rglob("*.jpg"))


def test_the_take_ingests_with_its_markers(product: Path, take: dict[str, Any]) -> None:
    run_json("ingest", "launch")
    run_json("analyze", "launch")

    analysis = json.loads((product / "analysis" / "c1.json").read_text(encoding="utf-8"))
    assert analysis["clip"]["role"] == "screen"
    assert [m["name"] for m in analysis["markers"]] == ["start", "clicked", "shown", "end"]
    assert "c1.e.result" in (product / "analysis" / "packed.md").read_text(encoding="utf-8")


def test_an_element_whose_box_rounds_to_zero_is_dropped_and_the_take_kept(
    product: Path, tmp_path: Path
) -> None:
    script = tmp_path / "tiny.mjs"
    script.write_text(
        "export default async function take(r) {\n"
        f"  await r.goto({json.dumps((FIXTURES / 'page.html').as_uri())});\n"
        "  await r.wait(400);\n"
        "  await r.mark('start', { title: '#title', sliver: { x: 10, y: 10, w: 0.04, h: 20 } });\n"
        "  await r.wait(400);\n"
        "}\n",
        encoding="utf-8",
    )

    result = invoke("record", "web", "launch", script)

    assert result.exit_code == 0, result.output
    (warning,) = [line for line in result.output.splitlines() if line.startswith("warning:")]
    assert "sliver" in warning
    sidecar = json.loads((product / "raw" / "tiny.markers.json").read_text(encoding="utf-8"))
    assert [e["name"] for e in sidecar["markers"][0]["elements"]] == ["title"]
    state = json.loads((product / "state.json").read_text(encoding="utf-8"))
    assert state["stages"]["record.tiny"]["warnings"] == [warning.removeprefix("warning: ")]
