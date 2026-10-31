"""`motion-studio render` on a product project, with a stand-in for the Remotion CLI.

The real Product composition is covered by tests/integration/test_product_render.py.
"""

import json
import shutil
import sys
import textwrap
from pathlib import Path
from typing import Any

import pytest
from product_fixtures import EDL, product_project, run_json, write_edl
from typer.testing import CliRunner

from motion_studio.cli import app
from motion_studio.media.ffmpeg import run_ffprobe

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")

runner = CliRunner()

BRAND_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "brand"

# Writes a grey video as long as the timeline, silent unless asked for an audio track.
FAKE_REMOTION = """
    import json, subprocess, sys
    from pathlib import Path

    args = sys.argv[1:]
    opts = dict(a[2:].split("=", 1) for a in args if a.startswith("--") and "=" in a)
    out = Path(args[3])
    props = json.loads(Path(opts["props"]).read_text())
    log = Path(__file__).resolve().parents[2] / "calls.jsonl"
    root = Path(opts["public-dir"])
    public = sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())
    with log.open("a") as f:
        f.write(json.dumps({"argv": args, "props": props, "public": public}) + "\\n")
    timeline = props["timeline"]
    spec = next(f for f in timeline["formats"] if f["name"] == props["format"])
    scale = float(opts.get("scale", "1"))
    w, h = round(spec["width"] * scale), round(spec["height"] * scale)
    seconds = timeline["duration_frames"] / timeline["fps"]
    grey = f"color=c=gray:size={w}x{h}:rate={timeline['fps']}:duration={seconds}"
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", grey]
    if "--enforce-audio-track" in args:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", str(seconds)]
        cmd += ["-c:a", "aac"]
    cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(out)]
    subprocess.run(cmd, check=True)
"""


@pytest.fixture(autouse=True)
def no_disk_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTION_STUDIO_MIN_FREE_GB", "0")


@pytest.fixture
def fake_renderer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    renderer = tmp_path / "renderer"
    bin_dir = renderer / "node_modules" / ".bin"
    bin_dir.mkdir(parents=True)
    script = bin_dir / "remotion"
    script.write_text(f"#!{sys.executable}\n{textwrap.dedent(FAKE_REMOTION)}", encoding="utf-8")
    script.chmod(0o755)
    monkeypatch.setenv("MOTION_STUDIO_RENDERER_DIR", str(renderer))
    return renderer


@pytest.fixture
def launch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    ws = tmp_path / "videos"
    run_json("init", ws)
    monkeypatch.chdir(ws)
    project = product_project(ws, tmp_path)
    write_edl(project)
    return project


def calls(renderer: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in (renderer / "calls.jsonl").read_text().splitlines()]


def streams(path: Path) -> list[dict[str, Any]]:
    out = run_ffprobe(["-v", "error", "-show_streams", "-of", "json", path])
    return json.loads(out)["streams"]


def test_render_composes_scenes_with_the_product_composition(
    launch: Path, fake_renderer: Path
) -> None:
    out = run_json("render", "launch")

    [call] = calls(fake_renderer)
    assert call["argv"][2] == "Product"
    assert "--enforce-audio-track" in call["argv"]
    assert [s["id"] for s in call["props"]["timeline"]["scenes"]] == ["intro", "step1", "pick"]
    assert "media/c1.mp4" in call["public"]
    assert not (launch / "build" / "assembled.mp4").exists()
    [output] = out["outputs"]
    assert (output["format"], output["width"], output["height"]) == ("16x9", 960, 540)
    # Four, four and eight beats at 120 bpm.
    assert output["duration_s"] == pytest.approx(8.0, abs=0.04)
    assert out["cuts_s"] == [2.0, 4.0]


def test_a_music_only_render_has_mastered_audio(launch: Path, fake_renderer: Path) -> None:
    out = run_json("render", "launch")

    kinds = sorted(s["codec_type"] for s in streams(Path(out["outputs"][0]["path"])))
    assert kinds == ["audio", "video"]


def test_render_final_writes_the_master_and_the_share_copy(
    launch: Path, fake_renderer: Path
) -> None:
    out = run_json("render", "launch", "--final")

    [output] = out["outputs"]
    assert Path(output["path"]) == launch / "final" / "launch_16x9.mp4"
    assert (output["width"], output["height"]) == (1920, 1080)
    assert Path(output["share"]["path"]).is_file()


def test_rendering_again_with_nothing_changed_does_nothing(
    launch: Path, fake_renderer: Path
) -> None:
    run_json("render", "launch")

    again = run_json("render", "launch")

    assert again["noop"] is True
    assert len(calls(fake_renderer)) == 1


def test_replacing_the_recording_renders_again(launch: Path, fake_renderer: Path) -> None:
    run_json("render", "launch")
    mezzanine = launch / "media" / "c1.mp4"
    mezzanine.write_bytes(mezzanine.read_bytes() + b"\0")

    again = run_json("render", "launch")

    assert again["noop"] is False


def test_the_props_carry_the_brand_font_and_logo_files(launch: Path, fake_renderer: Path) -> None:
    run_json("render", "launch")

    props = calls(fake_renderer)[0]["props"]
    assert props["format"] == "16x9"
    assert props["font_file"] is None
    assert props["logo_file"] is None


def test_render_without_a_valid_edl_exits_1(launch: Path, fake_renderer: Path) -> None:
    write_edl(
        launch, {"kind": "product", "scenes": [{"id": "x", "type": "title_card", "headline": "Hi"}]}
    )

    result = runner.invoke(app, ["render", "launch", "--json"])

    assert result.exit_code == 1
    assert "scene x has no length" in result.output


def test_the_props_carry_the_wordmark_and_mascot_sheet_of_a_logo_outro(
    launch: Path, fake_renderer: Path
) -> None:
    workspace = launch.parents[1]
    brand = workspace / "library" / "brand"
    for name in ("wordmark.svg", "mascot.png", "mascot.json"):
        shutil.copy(BRAND_FIXTURES / name, brand / name)
    (launch / "project.toml").open("a", encoding="utf-8").write(
        '\n[brand]\nwordmark = "library/brand/wordmark.svg"\n'
        'mascot = { sheet = "library/brand/mascot.png", timings = "library/brand/mascot.json" }\n'
    )
    outro = {"id": "outro", "type": "logo_outro", "bars": 1, "tagline": "Bye."}
    write_edl(launch, {**EDL, "scenes": [*EDL["scenes"], outro]})

    run_json("render", "launch")

    [call] = calls(fake_renderer)
    assert call["props"]["wordmark_file"] == "brand/wordmark.svg"
    assert call["props"]["mascot_file"] == "brand/mascot.png"
    assert {"brand/wordmark.svg", "brand/mascot.png"} <= set(call["public"])
    assert call["props"]["timeline"]["brand"]["mascot"]["frame_width"] == 544
