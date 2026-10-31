"""Product projects: the kind in project.toml, screen recordings at ingest and in the index."""

import json
import re
import shutil
import tomllib
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from motion_studio.cli import app
from motion_studio.media.ffmpeg import run_ffmpeg

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")

runner = CliRunner()


def invoke(*args: str | Path):
    return runner.invoke(app, [str(a) for a in args])


def run_json(*args: str | Path) -> dict[str, Any]:
    result = invoke(*args, "--json")
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


def project_meta(project: Path) -> dict[str, Any]:
    return tomllib.loads((project / "project.toml").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def no_disk_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTION_STUDIO_MIN_FREE_GB", "0")


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    ws = tmp_path / "videos"
    assert invoke("init", ws).exit_code == 0
    monkeypatch.chdir(ws)
    return ws


def test_new_with_kind_product_stores_the_kind_and_status_shows_it(workspace: Path) -> None:
    run_json("new", "launch", "--kind", "product")

    assert project_meta(workspace / "projects" / "launch")["project"]["kind"] == "product"
    status = invoke("status", "launch")
    assert status.exit_code == 0, status.output
    assert status.output.splitlines()[0].startswith("launch (product):")
    assert run_json("status", "launch")["kind"] == "product"


def test_new_without_kind_makes_a_talk_project(workspace: Path) -> None:
    run_json("new", "talk")

    assert project_meta(workspace / "projects" / "talk")["project"]["kind"] == "talk"
    assert run_json("status", "talk")["kind"] == "talk"


def test_an_unknown_kind_is_refused(workspace: Path) -> None:
    result = invoke("new", "x", "--kind", "promo")

    assert result.exit_code != 0
    assert not (workspace / "projects" / "x").exists()


def test_a_project_toml_from_before_kinds_reads_as_talk(workspace: Path) -> None:
    run_json("new", "old")
    toml = workspace / "projects" / "old" / "project.toml"
    toml.write_text('[project]\ntitle = "old"\n\n[clips]\n', encoding="utf-8")

    assert run_json("status", "old")["kind"] == "talk"


def test_words_on_a_product_project_exits_1_with_a_hint(workspace: Path) -> None:
    run_json("new", "launch", "--kind", "product")

    result = invoke("words", "launch", "c1.s0")

    assert result.exit_code == 1
    assert "talk projects" in result.output
    assert "packed.md" in result.output


def screen_recording(path: Path) -> Path:
    """320x180 at 30 fps: 1.5 s of moving test pattern, then 3 s of a still grey screen."""
    run_ffmpeg(
        [
            "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30:duration=1.5",
            "-f", "lavfi", "-i", "color=c=gray:size=320x180:rate=30:duration=3",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=4.5",
            "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]",
            "-map", "[v]", "-map", "2:a", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest", "-y", path,
        ]
    )  # fmt: skip
    return path


@pytest.fixture
def product(workspace: Path, tmp_path: Path) -> Path:
    clip = screen_recording(tmp_path / "demo flow.mp4")
    run_json("new", "launch", "--kind", "product", "--from", clip)
    return workspace / "projects" / "launch"


@needs_ffmpeg
def test_a_plain_mp4_in_a_product_project_ingests_as_a_screen_recording(product: Path) -> None:
    out = run_json("ingest", "launch")

    [clip] = out["clips"]
    assert (clip["id"], clip["role"], clip["width"], clip["height"]) == ("c1", "screen", 320, 180)
    assert Path(clip["mezzanine"]).is_file()
    assert clip["audio"] is None
    assert project_meta(product)["clips"]["c1"]["role"] == "screen"


@needs_ffmpeg
def test_ingest_writes_a_1_fps_contact_sheet_outside_the_look_budget(product: Path) -> None:
    out = run_json("ingest", "launch")

    sheet = product / "contact" / "c1.png"
    assert out["sheets"] == [str(sheet)]
    assert sheet.is_file()
    state = json.loads((product / "state.json").read_text(encoding="utf-8"))
    assert state.get("look_count", 0) == 0


@needs_ffmpeg
def test_ingest_prints_the_contact_sheet_it_wrote(product: Path) -> None:
    result = invoke("ingest", "launch")

    assert result.exit_code == 0, result.output
    assert f"wrote {product / 'contact' / 'c1.png'}" in result.output


@pytest.fixture
def model_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Stand-ins for the speech and face workers that log any request they get."""
    log = tmp_path / "models.log"
    asr = tmp_path / "fake-asr-worker"
    asr.write_text(f"#!/bin/sh\necho asr >> '{log}'\nexit 1\n", encoding="utf-8")
    asr.chmod(0o755)
    monkeypatch.setenv("MOTION_STUDIO_ASR_WORKER", str(asr))
    monkeypatch.setenv("FAKE_FACES_LOG", str(log))
    return log


@needs_ffmpeg
def test_analyze_on_a_product_project_loads_no_speech_or_face_model(
    product: Path, model_log: Path
) -> None:
    run_json("ingest", "launch")

    out = run_json("analyze", "launch")

    assert not model_log.exists()
    assert [(c["id"], c["role"], c["words"]) for c in out["clips"]] == [("c1", "screen", 0)]
    assert not (product / "analysis" / "retakes.json").exists()


@needs_ffmpeg
def test_the_packed_index_lists_length_frame_size_and_static_stretches(
    product: Path, model_log: Path
) -> None:
    run_json("ingest", "launch")
    run_json("analyze", "launch")

    packed = (product / "analysis" / "packed.md").read_text(encoding="utf-8")
    assert packed.startswith("# Project: launch · product · 1 screen recording")
    assert "## c1 · demo flow.mp4 · 4.5 s · 320x180 · no markers" in packed
    assert re.search("^- static \\[00:01\\.\\d\N{EN DASH}00:04\\.5\\]", packed, flags=re.M), packed


def typing_recording(path: Path) -> Path:
    """1600x900: a light page idle for 3 s, then 10x18 px glyphs typed 4 a second for 4 s."""
    glyphs = ",".join(
        f"drawbox=x={200 + 12 * i}:y=400:w=10:h=18:color=0x202020:t=fill"
        f":enable='gte(t,{3 + i / 4:.2f})'"
        for i in range(16)
    )
    run_ffmpeg(
        [
            "-f", "lavfi", "-i", "color=c=0xF4F4F4:size=1600x900:rate=30:duration=7",
            "-vf", glyphs, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-y", path,
        ]
    )  # fmt: skip
    return path


@needs_ffmpeg
def test_typing_in_a_screen_recording_is_motion_and_the_idle_page_is_static(
    workspace: Path, tmp_path: Path, model_log: Path
) -> None:
    run_json("new", "typing", "--kind", "product", "--from", typing_recording(tmp_path / "t.mp4"))
    run_json("ingest", "typing")

    run_json("analyze", "typing")

    analysis = json.loads(
        (workspace / "projects" / "typing" / "analysis" / "c1.json").read_text(encoding="utf-8")
    )
    [static] = analysis["static"]
    assert static["start"] == 0.0
    assert static["end"] == pytest.approx(3.0, abs=0.5)


def write_sidecar(product: Path, data: dict[str, Any]) -> Path:
    path = product / "raw" / "demo flow.markers.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


SIDECAR: dict[str, Any] = {
    "schema_version": 1,
    "width": 320,
    "height": 180,
    "markers": [
        {
            "name": "v1_shown",
            "t": 1.2,
            "elements": [{"name": "hook", "x": 10, "y": 20, "w": 200, "h": 40}],
        },
        {"name": "start", "t": 0.0},
    ],
    "cursor": [{"t": 0.0, "x": 5, "y": 5}, {"t": 1.0, "x": 100, "y": 60, "down": True}],
}


@needs_ffmpeg
def test_a_markers_sidecar_puts_markers_and_elements_in_the_packed_index(
    product: Path, model_log: Path
) -> None:
    write_sidecar(product, SIDECAR)

    ingested = run_json("ingest", "launch")
    out = run_json("analyze", "launch")

    assert [c["id"] for c in ingested["clips"]] == ["c1"]
    assert ingested["warnings"] == []
    assert out["clips"][0]["markers"] == 2
    packed = (product / "analysis" / "packed.md").read_text(encoding="utf-8")
    assert "## c1 · demo flow.mp4 · 4.5 s · 320x180 · 2 markers" in packed
    assert "- c1.m.start 00:00.0\n- c1.m.v1_shown 00:01.2 · c1.e.hook 10,20 200x40\n" in packed
    analysis = json.loads((product / "analysis" / "c1.json").read_text(encoding="utf-8"))
    assert analysis["markers_source"] == "raw/demo flow.markers.json"
    assert analysis["cursor"][1] == {"t": 1.0, "x": 100, "y": 60, "down": True}


@needs_ffmpeg
def test_sidecar_boxes_are_scaled_to_the_mezzanine(product: Path, model_log: Path) -> None:
    write_sidecar(product, {**SIDECAR, "width": 640, "height": 360})
    run_json("ingest", "launch")

    run_json("analyze", "launch")

    packed = (product / "analysis" / "packed.md").read_text(encoding="utf-8")
    assert "c1.e.hook 5,10 100x20" in packed
    analysis = json.loads((product / "analysis" / "c1.json").read_text(encoding="utf-8"))
    assert analysis["cursor"][1] == {"t": 1.0, "x": 50, "y": 30, "down": True}


@needs_ffmpeg
def test_an_edited_sidecar_is_read_again(product: Path, model_log: Path) -> None:
    sidecar = write_sidecar(product, SIDECAR)
    run_json("ingest", "launch")
    run_json("analyze", "launch")

    sidecar.write_text(json.dumps({**SIDECAR, "markers": []}), encoding="utf-8")
    run_json("ingest", "launch")
    out = run_json("analyze", "launch")

    assert out["clips"][0]["markers"] == 0


@needs_ffmpeg
def test_an_invalid_sidecar_exits_1_naming_the_file_and_the_problem(
    product: Path, model_log: Path
) -> None:
    twice = [{"name": "start", "t": 0.0}, {"name": "start", "t": 1.0}]
    write_sidecar(product, {**SIDECAR, "markers": twice})
    run_json("ingest", "launch")

    result = invoke("analyze", "launch")

    assert result.exit_code == 1
    assert "demo flow.markers.json" in result.output
    assert "start" in result.output and "twice" in result.output


def test_a_new_product_project_points_at_recording(workspace: Path) -> None:
    result = invoke("new", "other", "--kind", "product")

    (hint,) = [line for line in result.output.splitlines() if line.startswith("next:")]
    assert "motion-studio record web other <script.mjs>" in hint
    assert "motion-studio record terminal other <tape>" in hint


def test_status_of_a_product_project_without_recordings_points_at_recording(
    workspace: Path,
) -> None:
    assert invoke("new", "launch", "--kind", "product").exit_code == 0

    out = run_json("status", "launch")

    assert out["clips"] == 0
    assert "motion-studio record web launch <script.mjs>" in out["hint"]


def test_status_does_not_count_markers_sidecars_as_clips(workspace: Path) -> None:
    assert invoke("new", "launch", "--kind", "product").exit_code == 0
    raw = workspace / "projects" / "launch" / "raw"
    (raw / "demo.mp4").write_bytes(b"")
    (raw / "demo.markers.json").write_text("{}", encoding="utf-8")

    assert run_json("status", "launch")["clips"] == 1
