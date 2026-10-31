"""`motion-studio check` on a product project, with a stand-in for the Remotion CLI.

The stand-in renders grey frames and, when a test asks for it, a scripted soundtrack, so these
tests drive the metrics, the masked-regions list, the cursor check and the exit code.
"""

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from PIL import Image
from product_fixtures import EDL, product_project, run_json, write_edl
from test_product_render_cli import fake_renderer
from typer.testing import CliRunner

from motion_studio.cli import app

__all__ = ["fake_renderer"]

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")

runner = CliRunner()

# A 60 Hz hum with a 2 kHz tone 26 dB under it: far more than 10 dB of bass over the top.
BASS_HEAVY = "0.5*sin(2*PI*60*t)+0.025*sin(2*PI*2000*t)|0.5*sin(2*PI*60*t)+0.025*sin(2*PI*2000*t)"
BUTTON = {"name": "button", "x": 100, "y": 60, "w": 80, "h": 40}
MARKERS = [
    {"name": "open", "t": 0.5},
    {"name": "typed", "t": 2.5, "elements": [BUTTON]},
    {"name": "done", "t": 4.5},
]


@pytest.fixture(autouse=True)
def no_disk_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTION_STUDIO_MIN_FREE_GB", "0")


@pytest.fixture
def asr_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A transcriber that only leaves a file behind, so a test can tell it never ran."""
    log = tmp_path / "asr-ran"
    worker = tmp_path / "asr-worker"
    worker.write_text(f"#!/bin/sh\ntouch {log}\nexit 1\n", encoding="utf-8")
    worker.chmod(0o755)
    monkeypatch.setenv("MOTION_STUDIO_ASR_WORKER", str(worker))
    return log


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    ws = tmp_path / "videos"
    run_json("init", ws)
    monkeypatch.chdir(ws)
    return ws


def launch(workspace: Path, tmp_path: Path, cursor: list[dict[str, Any]] | None = None) -> Path:
    sidecar: dict[str, Any] = {"markers": MARKERS, "cursor": cursor or []}
    project = product_project(workspace, tmp_path, sidecar=sidecar)
    write_edl(project)
    return project


def with_events(*events: dict[str, Any], **footage: Any) -> dict[str, Any]:
    """The fixture EDL with `events` (and any other `footage` fields) on its footage scene."""
    scenes = [*EDL["scenes"][:2], {**EDL["scenes"][2], "events": list(events), **footage}]
    return {**EDL, "scenes": scenes}


def check(*args: str) -> tuple[int, dict[str, Any]]:
    result = runner.invoke(app, ["check", "launch", *args, "--json"])
    assert result.exit_code in (0, 1), result.output
    return result.exit_code, json.loads(result.stdout)


def codes(body: dict[str, Any], severity: str) -> list[str]:
    return [i["code"] for i in body["issues"] if i["severity"] == severity]


def test_check_on_a_product_render_measures_without_asr_and_writes_the_contact_sheet(
    workspace: Path, tmp_path: Path, fake_renderer: Path, asr_log: Path
) -> None:
    project = launch(workspace, tmp_path)
    run_json("render", "launch")

    code, body = check()

    assert code == 0, body
    assert not asr_log.exists()
    assert "clipped_cut" not in codes(body, "blocking")
    metrics = body["metrics"]
    assert metrics["duration_s"] == pytest.approx(8.0, abs=0.05)
    assert set(metrics["loudness"]) == set(metrics["bands"]) == {"16x9"}
    assert "words" not in metrics
    assert body["cuts_s"] == [2.0, 4.0]
    contact = project / "check" / "contact.png"
    assert Path(body["contact_sheet"]) == contact
    with Image.open(contact) as sheet:
        assert sheet.width > 480
    report = (project / "check" / "report.md").read_text(encoding="utf-8")
    assert report.startswith("PASS")
    assert "look launch --at" in report


def test_a_bass_heavy_music_only_render_is_blocked(
    workspace: Path, tmp_path: Path, fake_renderer: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # tests/unit/test_check_cli.py shows the same imbalance on a talk render only warns.
    launch(workspace, tmp_path)
    monkeypatch.setenv("FAKE_REMOTION_AUDIO", BASS_HEAVY)
    run_json("render", "launch")

    code, body = check()

    assert code == 1
    [small] = [i for i in body["issues"] if i["code"] == "small_speaker"]
    assert small["severity"] == "blocking"
    assert "1 kHz" in small["message"] and "150 Hz" in small["message"]
    assert "brighter music bed" in small["fix"]
    bands = body["metrics"]["bands"]["16x9"]
    assert bands["below_150_hz"] - bands["1_to_5_khz"] > 20


def test_every_masked_region_is_listed_with_the_frames_it_covers(
    workspace: Path, tmp_path: Path, fake_renderer: Path
) -> None:
    project = launch(workspace, tmp_path)
    mask = {"type": "mask", "target": {"x": 0, "y": 0, "w": 320, "h": 20}, "end": "c1.m.typed"}
    write_edl(project, with_events(mask, {"type": "mask", "target": "c1.e.button"}))
    run_json("render", "launch")

    _, body = check()

    # The footage scene runs from frame 120 at 1x from c1.m.open (0.5 s); typed is 2.5 s.
    masks = [(m["start"], m["end"], m["element"]) for m in body["metrics"]["masks"]]
    assert masks == [(120, 180, None), (120, 240, "c1.e.button")]
    report = (project / "check" / "report.md").read_text(encoding="utf-8")
    section = report.split("## Masked regions")[1].split("## Metrics")[0]
    assert "box 0,0 320x20 of c1, frames 120-179 (4.00-6.00 s)" in section
    assert "c1.e.button of c1, frames 120-239" in section
    assert "look launch --at 5" in section


def test_a_cursor_sitting_on_a_highlight_target_warns(
    workspace: Path, tmp_path: Path, fake_renderer: Path
) -> None:
    # The cursor stops on the button at 2.0 s and stays there while the highlight shows.
    cursor = [{"t": 0.5, "x": 20, "y": 20}, {"t": 2.0, "x": 140, "y": 80}]
    project = launch(workspace, tmp_path, cursor)
    highlight = {"type": "highlight", "target": "c1.e.button", "start": "c1.m.typed"}
    write_edl(project, with_events(highlight))
    run_json("render", "launch")

    code, body = check()

    assert code == 0, body
    [warning] = [i for i in body["issues"] if i["code"] == "cursor_over_target"]
    assert warning["severity"] == "warning"
    # typed (2.5 s) is 2 s into the footage scene, which starts at 4 s.
    assert "c1.e.button in scene pick at 6.00 s" in warning["message"]
    assert "r.park" in warning["fix"]
    assert "look launch --at 6" in warning["fix"]


def test_a_cursor_parked_off_the_target_does_not_warn(
    workspace: Path, tmp_path: Path, fake_renderer: Path
) -> None:
    # On the button before the highlight, then parked off it as the highlight draws in.
    cursor = [{"t": 1.0, "x": 140, "y": 80}, {"t": 2.4, "x": 300, "y": 160}]
    project = launch(workspace, tmp_path, cursor)
    highlight = {"type": "highlight", "target": "c1.e.button", "start": "c1.m.typed"}
    write_edl(project, with_events(highlight))
    run_json("render", "launch")

    _, body = check()

    assert "cursor_over_target" not in codes(body, "warning")


def test_the_cursor_check_skips_terminal_footage(
    workspace: Path, tmp_path: Path, fake_renderer: Path
) -> None:
    cursor = [{"t": 2.0, "x": 140, "y": 80}]
    project = launch(workspace, tmp_path, cursor)
    highlight = {"type": "highlight", "target": "c1.e.button", "start": "c1.m.typed"}
    write_edl(project, with_events(highlight, device_frame="terminal"))
    run_json("render", "launch")

    _, body = check()

    assert "cursor_over_target" not in codes(body, "warning")


def test_the_summary_points_at_the_contact_sheet_and_look_at(
    workspace: Path, tmp_path: Path, fake_renderer: Path
) -> None:
    project = launch(workspace, tmp_path)
    run_json("render", "launch")

    result = runner.invoke(app, ["check", "launch"])

    assert result.exit_code == 0, result.output
    assert f"wrote {project / 'check' / 'contact.png'}" in result.output
    assert "look launch --at" in result.output
