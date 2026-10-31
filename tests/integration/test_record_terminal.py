"""`motion-studio record terminal` end to end: a tape run by the real vhs and ttyd.

The tape launches a stand-in Claude Code (`tests/fixtures/record/terminal/claude`) from a
folder named like a scratchpad, with an MCP config holding a key, while CLAUDE* variables are
set. Stills of the take are read with tesseract to prove none of that reaches the screen.
"""

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from motion_studio.cli import app
from motion_studio.media.ffmpeg import run_ffmpeg, run_ffprobe

pytestmark = [
    pytest.mark.record,
    pytest.mark.mac,
    pytest.mark.skipif(
        not (shutil.which("vhs") and shutil.which("ttyd")), reason="needs vhs and ttyd"
    ),
]

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "record" / "terminal"

runner = CliRunner()


def invoke(*args: str | Path):
    return runner.invoke(app, [str(a) for a in args])


def run_json(*args: str | Path) -> dict[str, Any]:
    result = invoke(*args, "--json")
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


@pytest.fixture
def product(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("MOTION_STUDIO_MIN_FREE_GB", "0")
    monkeypatch.setenv("CLAUDE_CODE_CHILD_SESSION", "1")
    ws = tmp_path / "vidéos de démo"
    assert invoke("init", ws).exit_code == 0
    monkeypatch.chdir(ws)
    run_json("new", "launch", "--kind", "product")
    return ws / "projects" / "launch"


@pytest.fixture
def takes(tmp_path: Path) -> Path:
    folder = tmp_path / "scratchpad" / "term takes"
    shutil.copytree(FIXTURES, folder)
    return folder


@pytest.fixture
def take(product: Path, takes: Path) -> dict[str, Any]:
    out = run_json("record", "terminal", "launch", takes / "take.tape")
    out["markers_json"] = json.loads(Path(out["sidecar"]).read_text(encoding="utf-8"))
    return out


def read_text(clip: Path, t: float, out: Path) -> str:
    run_ffmpeg(["-ss", f"{t:.3f}", "-i", clip, "-frames:v", "1", "-y", out])
    result = subprocess.run(
        ["tesseract", str(out), "-"], capture_output=True, text=True, check=True
    )
    return result.stdout


def marker(take: dict[str, Any], name: str) -> float:
    return next(m["t"] for m in take["markers_json"]["markers"] if m["name"] == name)


def test_the_take_is_a_constant_frame_rate_clip_with_its_markers(
    product: Path, take: dict[str, Any]
) -> None:
    clip = Path(take["clip"])
    assert clip == product / "raw" / "take.mp4"
    stream = json.loads(
        run_ffprobe(["-v", "error", "-count_frames", "-show_streams", "-of", "json", clip])
    )["streams"][0]

    assert (stream["width"], stream["height"]) == (1600, 900)
    assert stream["r_frame_rate"] == stream["avg_frame_rate"] == "30/1"
    assert int(stream["nb_read_frames"]) == pytest.approx(take["duration_s"] * 30, abs=2)
    sidecar = take["markers_json"]
    assert (sidecar["width"], sidecar["height"]) == (1600, 900)
    assert [m["name"] for m in sidecar["markers"]] == ["ready", "answered"]
    # Between the marks: a 1 s sleep, 11 keys at 40 ms, Enter and another 1 s sleep.
    gap = marker(take, "answered") - marker(take, "ready")
    assert 2.2 <= gap <= 2.9
    assert marker(take, "answered") < take["duration_s"]
    assert sorted(p.name for p in (product / "raw").iterdir()) == ["take.markers.json", "take.mp4"]


def test_the_marker_lands_on_the_frame_that_shows_its_moment(
    take: dict[str, Any], tmp_path: Path
) -> None:
    clip = Path(take["clip"])
    ready = marker(take, "ready")

    assert "you said: hello there" not in read_text(clip, ready, tmp_path / "ready.png")
    assert "you said: hello there" in read_text(
        clip, marker(take, "answered"), tmp_path / "answered.png"
    )


def test_no_claude_variable_path_or_key_reaches_the_frames(
    take: dict[str, Any], tmp_path: Path
) -> None:
    clip = Path(take["clip"])
    stills = [0.0, marker(take, "ready"), marker(take, "answered"), take["duration_s"] - 0.1]
    text = "\n".join(read_text(clip, t, tmp_path / f"{i}.png") for i, t in enumerate(stills))

    assert "trusted" in text
    assert "mcp servers: demo" in text
    assert "exited" not in text
    for leak in ("CLAUDE", "scratchpad", "takes", "secret", "SECRETKEY", "mcp-config", "compgen"):
        assert leak not in text, text


def test_a_tape_vhs_cannot_parse_exits_1_with_vhs_message(product: Path, takes: Path) -> None:
    tape = takes / "typo.tape"
    tape.write_text('Mark start\nTyp "hello"\n', "utf-8")

    result = invoke("record", "terminal", "launch", tape)

    assert result.exit_code == 1, result.output
    assert "Invalid command: Typ" in result.output
    assert "2 │" in result.output
    assert list((product / "raw").iterdir()) == []
