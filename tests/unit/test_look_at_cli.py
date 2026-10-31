"""`motion-studio look --at`: stills of the latest render, with a stand-in for the Remotion CLI.

The stand-in paints each frame a colour that encodes its frame number, so a still says which
frame of the render it is.
"""

import json
import shutil
import sys
import textwrap
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image
from product_fixtures import EDL, product_project, run_json, write_edl
from typer.testing import CliRunner

from motion_studio.cli import app

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")

runner = CliRunner()

# Red counts frames modulo 8, green the eights, blue the sixty-fours, in steps of 32.
FAKE_REMOTION = """
    import json, subprocess, sys
    from pathlib import Path

    args = sys.argv[1:]
    opts = dict(a[2:].split("=", 1) for a in args if a.startswith("--") and "=" in a)
    out = Path(args[3])
    props = json.loads(Path(opts["props"]).read_text())
    timeline = props["timeline"]
    spec = next(f for f in timeline["formats"] if f["name"] == props["format"])
    scale = float(opts.get("scale", "1"))
    w, h = round(spec["width"] * scale), round(spec["height"] * scale)
    seconds = timeline["duration_frames"] / timeline["fps"]
    coded = (
        f"color=c=black:size={w}x{h}:rate={timeline['fps']}:duration={seconds},format=rgb24,"
        "geq=r='mod(N,8)*32+16':g='mod(floor(N/8),8)*32+16':b='floor(N/64)*32+16'"
    )
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", coded]
    cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", str(seconds), "-c:a", "aac"]
    cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(out)]
    subprocess.run(cmd, check=True)
"""


@pytest.fixture(autouse=True)
def no_disk_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTION_STUDIO_MIN_FREE_GB", "0")


@pytest.fixture
def launch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """`launch` with the fixture EDL: intro 0-2 s, step1 2-4 s, then c1 open..done 4-8 s."""
    renderer = tmp_path / "renderer"
    bin_dir = renderer / "node_modules" / ".bin"
    bin_dir.mkdir(parents=True)
    script = bin_dir / "remotion"
    script.write_text(f"#!{sys.executable}\n{textwrap.dedent(FAKE_REMOTION)}", encoding="utf-8")
    script.chmod(0o755)
    monkeypatch.setenv("MOTION_STUDIO_RENDERER_DIR", str(renderer))
    ws = tmp_path / "videos"
    run_json("init", ws)
    monkeypatch.chdir(ws)
    project = product_project(ws, tmp_path)
    write_edl(project)
    return project


@pytest.fixture
def rendered(launch: Path) -> Path:
    run_json("render", "launch")
    return launch


def look_at(*ats: str) -> dict[str, Any]:
    return run_json("look", "launch", *(arg for at in ats for arg in ("--at", at)))


def frame_number(path: Path) -> int:
    with Image.open(path) as image:
        rgb = np.asarray(image.convert("RGB"))
    r, g, b = (int(v) for v in rgb[rgb.shape[0] // 2, rgb.shape[1] // 2])
    return round((r - 16) / 32) + 8 * round((g - 16) / 32) + 64 * round((b - 16) / 32)


@pytest.mark.parametrize(
    ("at", "frame", "scene"),
    [
        # The middle of step1's frames 60 to 120.
        ("step1", 90, "step1"),
        # typed is 2 s after open, where pick starts at 4 s.
        ("c1.m.typed", 180, "pick"),
        ("1.5", 45, "intro"),
        ("1.5s", 45, "intro"),
    ],
)
def test_look_at_writes_the_frame_of_the_render_it_names(
    rendered: Path, at: str, frame: int, scene: str
) -> None:
    out = look_at(at)

    [still] = out["stills"]
    assert (still["at"], still["frame"], still["scene"]) == (at, frame, scene)
    assert still["t"] == pytest.approx(frame / 30)
    path = Path(still["path"])
    assert path.parent == rendered / "contact"
    assert frame_number(path) == frame
    with Image.open(path) as image:
        assert image.size == (960, 540)
    assert out["render"] == str(rendered / "preview" / "16x9.mp4")


def test_several_stills_in_one_call_count_once_against_the_look_budget(rendered: Path) -> None:
    first = look_at("intro", "c1.m.done")
    second = look_at("7")

    assert [frame_number(Path(s["path"])) for s in first["stills"]] == [30, 239]
    assert (first["look_count"], second["look_count"]) == (1, 2)
    assert first["look_budget"] == 8


def test_past_the_look_budget_look_at_warns_and_still_writes(rendered: Path) -> None:
    toml = rendered.parents[1] / "motion-studio.toml"
    toml.write_text(
        toml.read_text(encoding="utf-8").replace("look_budget = 8", "look_budget = 1", 1),
        encoding="utf-8",
    )
    look_at("intro")

    result = runner.invoke(app, ["look", "launch", "--at", "step1"])

    assert result.exit_code == 0, result.output
    assert "warning: look budget exceeded (2 of 1 sheets)" in result.stderr
    assert Path(result.stdout.splitlines()[-1].removeprefix("wrote ")).is_file()


def test_the_latest_render_is_the_one_looked_at(rendered: Path) -> None:
    run_json("render", "launch", "--final")

    out = look_at("step1")

    assert out["render"] == str(rendered / "final" / "launch_16x9.mp4")
    [still] = out["stills"]
    assert frame_number(Path(still["path"])) == 90
    with Image.open(still["path"]) as image:
        assert image.size[0] <= 1600


def test_without_a_render_look_at_exits_1_with_the_render_hint(launch: Path) -> None:
    result = runner.invoke(app, ["look", "launch", "--at", "step1", "--json"])

    assert result.exit_code == 1, result.output
    out = json.loads(result.stdout)
    assert "render launch" in out["hint"]


def test_a_render_older_than_the_edl_exits_1_with_the_render_hint(rendered: Path) -> None:
    edl = json.loads(json.dumps(EDL))
    edl["scenes"][0]["beats"] = 8
    write_edl(rendered, edl)
    run_json("plan", "validate", "launch")

    result = runner.invoke(app, ["look", "launch", "--at", "step1", "--json"])

    assert result.exit_code == 1, result.output
    out = json.loads(result.stdout)
    assert "out of date" in out["error"]
    assert "render launch" in out["hint"]


@pytest.mark.parametrize(
    ("args", "hint"),
    [
        (("--at", "nowhere"), "intro, step1, pick"),
        (("--at", "c1.m.nope"), "c1.m.open"),
        (("--at", "c9.m.open"), "c1"),
        (("--at", "8"), "0 to 8.00 s"),
        (("--at", "-1"), "0 to 8.00 s"),
        (("c1", "0", "1", "--at", "step1"), "--at"),
    ],
)
def test_a_moment_that_is_not_in_the_render_is_a_user_error_with_a_hint(
    rendered: Path, args: tuple[str, ...], hint: str
) -> None:
    result = runner.invoke(app, ["look", "launch", *args, "--json"])

    assert result.exit_code == 1, result.output
    out = json.loads(result.stdout)
    assert hint in out["hint"]


def test_a_marker_outside_every_footage_scene_names_the_scenes_that_play_its_clip(
    launch: Path,
) -> None:
    edl = json.loads(json.dumps(EDL))
    edl["scenes"][2]["from"] = "c1.m.typed"
    write_edl(launch, edl)
    run_json("render", "launch")

    result = runner.invoke(app, ["look", "launch", "--at", "c1.m.open", "--json"])

    assert result.exit_code == 1, result.output
    out = json.loads(result.stdout)
    assert "not on screen" in out["error"]
    assert "pick" in out["hint"]


def test_look_without_at_or_a_range_is_a_user_error(rendered: Path) -> None:
    result = runner.invoke(app, ["look", "launch", "--json"])

    assert result.exit_code == 1, result.output
    assert "--at" in json.loads(result.stdout)["hint"]
