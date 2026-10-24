"""`reelcut check` on a rendered demo project, with stand-ins for Remotion and the ASR worker.

The ASR stand-in returns the words a test scripts, so these tests drive the diff, the report
and the exit code; tests/integration/test_check_fixtures.py re-transcribes with the real model.
"""

import json
import os
import shutil
import stat
import sys
import textwrap
from pathlib import Path
from typing import Any

import pytest
from PIL import Image
from test_render_cli import demo, fake_renderer, invoke, render, timeline, write_edl

from reelcut.media.ffmpeg import run_ffmpeg, run_ffprobe

__all__ = ["demo", "fake_renderer"]

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")

FAKE_WORKER = """
import json, os, sys

request = json.load(sys.stdin)
words = json.loads(open(os.environ["FAKE_ASR_SCRIPT"]).read())
with open(os.environ["FAKE_ASR_LOG"], "a") as log:
    log.write(json.dumps(request["jobs"]) + "\\n")
results = [
    {
        "id": job["id"],
        "vad": [{"start": 0.0, "end": 60.0}],
        "language": {"code": job["language"] or "en", "confidence": 0.99},
        "words": [{"text": t, "start": s, "end": e, "conf": 0.9} for t, s, e in words],
    }
    for job in request["jobs"]
]
print(json.dumps({"pid": os.getpid(), "peak_rss_mb": 1.0, "results": results}))
"""


@pytest.fixture(autouse=True)
def no_disk_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    # CI runners have less free disk than the 20 GB render guard.
    monkeypatch.setenv("REELCUT_MIN_FREE_GB", "0")


@pytest.fixture
def asr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Where to write the words the stand-in worker hears; its requests go to `<this>.log`."""
    worker = tmp_path / "fake-check-worker"
    worker.write_text(f"#!{sys.executable}\n{textwrap.dedent(FAKE_WORKER)}", encoding="utf-8")
    worker.chmod(worker.stat().st_mode | stat.S_IEXEC)
    script = tmp_path / "heard.json"
    monkeypatch.setenv("REELCUT_ASR_WORKER", str(worker))
    monkeypatch.setenv("FAKE_ASR_SCRIPT", str(script))
    monkeypatch.setenv("FAKE_ASR_LOG", str(script.with_suffix(".log")))
    return script


def hear(script: Path, words: list[dict[str, Any]]) -> None:
    script.write_text(
        json.dumps([[w["text"], w["start_ms"] / 1000, w["end_ms"] / 1000] for w in words]),
        encoding="utf-8",
    )


def check(*args: str) -> tuple[int, dict[str, Any]]:
    result = invoke("check", "demo", *args, "--json")
    assert result.exit_code in (0, 1), result.output
    return result.exit_code, json.loads(result.stdout)


def codes(body: dict[str, Any], severity: str) -> list[str]:
    return [i["code"] for i in body["issues"] if i["severity"] == severity]


def test_a_good_render_passes_with_exit_0_and_writes_the_report_and_stills(
    demo: Path, asr: Path
) -> None:
    render("--preview")
    hear(asr, timeline(demo)["words"])

    code, body = check("--preview")

    assert code == 0, body
    assert body["ok"] is True
    assert body["verdict"] == "pass"
    assert codes(body, "blocking") == []
    report = demo / "check" / "report.md"
    assert Path(body["report"]) == report
    assert report.read_text(encoding="utf-8").splitlines()[0].startswith("PASS")
    assert Path(body["cuts_sheet"]) == demo / "check" / "cuts.png"


def test_a_word_lost_at_a_cut_blocks_with_an_edl_fix_and_exit_1(demo: Path, asr: Path) -> None:
    render("--preview")
    words = timeline(demo)["words"]
    # c1.w6 ("today.") ends the intro segment, right before cut 1.
    hear(asr, [w for w in words if w["id"] != "c1.w6"])

    code, body = check("--preview")

    assert code == 1
    assert body["ok"] is False
    assert body["verdict"] == "blocked"
    [clipped] = [i for i in body["issues"] if i["code"] == "clipped_cut"]
    assert clipped["severity"] == "blocking"
    assert "'today.'" in clipped["message"] and "cut 1" in clipped["message"]
    assert "policy.pad_out_ms (now 120)" in clipped["fix"]
    assert "segment intro's `to` to c1.w7" in clipped["fix"]
    report = (demo / "check" / "report.md").read_text(encoding="utf-8")
    assert report.startswith("BLOCKED")
    assert "c1.w7" in report


def test_a_word_lost_after_a_cut_points_at_pad_in_and_the_earlier_word(
    demo: Path, asr: Path
) -> None:
    render("--preview")
    words = timeline(demo)["words"]
    # c1.w17 ("See") starts the body segment, right after cut 1.
    hear(asr, [w for w in words if w["id"] != "c1.w17"])

    code, body = check("--preview")

    assert code == 1
    [clipped] = [i for i in body["issues"] if i["code"] == "clipped_cut"]
    assert "policy.pad_in_ms (now 80)" in clipped["fix"]
    assert "segment body's `from` to c1.w16" in clipped["fix"]


def test_a_word_misheard_far_from_any_cut_is_only_a_note(demo: Path, asr: Path) -> None:
    render("--preview")
    words = timeline(demo)["words"]
    # "reason" sits in the middle of the last segment, over a second from the last cut.
    heard = [{**w, "text": "raisin"} if w["text"] == "reason" else w for w in words]
    hear(asr, heard)

    code, body = check("--preview")

    assert code == 0, body
    [note] = [i for i in body["issues"] if i["code"] == "asr_noise"]
    assert note["severity"] == "info"
    assert "'raisin'" in note["message"]


def test_an_edl_longer_than_max_duration_blocks(demo: Path, asr: Path) -> None:
    write_edl(demo, max_duration_s=4)
    render("--preview")
    hear(asr, timeline(demo)["words"])

    code, body = check("--preview")

    assert code == 1
    [over] = [i for i in body["issues"] if i["code"] == "over_duration"]
    assert over["severity"] == "blocking"
    assert "max_duration_s 4" in over["message"]
    assert "body" in over["fix"]
    assert body["metrics"]["max_duration_s"] == 4


def test_the_voice_is_resampled_to_16k_and_transcribed_in_the_timeline_language(
    demo: Path, asr: Path
) -> None:
    render("--preview")
    hear(asr, timeline(demo)["words"])

    check("--preview")

    [jobs] = [json.loads(line) for line in asr.with_suffix(".log").read_text().splitlines()]
    [job] = jobs
    assert job["language"] == timeline(demo)["language"] == "en"
    info = json.loads(run_ffprobe(["-v", "error", "-show_streams", "-of", "json", job["wav"]]))
    stream = info["streams"][0]
    assert (stream["sample_rate"], stream["channels"]) == ("16000", 1)


def test_cuts_png_has_a_cell_per_cut_from_the_first_format(demo: Path, asr: Path) -> None:
    render("--preview")
    tl = timeline(demo)
    hear(asr, tl["words"])

    _, body = check("--preview")

    assert body["cuts_s"] == [round(r["out_in"] / tl["fps"], 3) for r in tl["runs"][1:]]
    assert len(body["cuts_s"]) >= 2
    with Image.open(body["cuts_sheet"]) as sheet:
        # Two 9x16 frames 240 px tall per cut, side by side, every cut in one row.
        assert sheet.height > 240
        assert sheet.width >= len(body["cuts_s"]) * 2 * 134


def test_loudness_is_measured_per_rendered_format(demo: Path, asr: Path) -> None:
    render("--preview")
    hear(asr, timeline(demo)["words"])

    _, body = check("--preview")

    loudness = body["metrics"]["loudness"]
    assert set(loudness) == {"9x16", "16x9"}
    for m in loudness.values():
        assert abs(m["integrated_lufs"] + 14) <= 1
        assert m["true_peak_db"] <= -1


def replace_picture(project: Path, colour: str) -> None:
    """Swap the demo mezzanine for a flat colour, keeping its length."""
    mezzanine = project / "media" / "c1.mp4"
    duration = run_ffprobe(
        ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", mezzanine]
    ).strip()
    run_ffmpeg(
        [
            "-y", "-f", "lavfi", "-i", f"color=c={colour}:size=360x640:rate=30", "-t", duration,
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", mezzanine,
        ]
    )  # fmt: skip


def test_black_frames_block_and_a_frozen_picture_warns(demo: Path, asr: Path) -> None:
    replace_picture(demo, "black")
    render("--preview", "--format", "9x16")
    hear(asr, timeline(demo)["words"])

    code, body = check("--preview")

    assert code == 1
    assert "black_frames" in codes(body, "blocking")
    assert body["formats"] == ["9x16"]

    replace_picture(demo, "gray")
    render("--preview", "--format", "9x16")

    code, body = check("--preview")

    assert code == 0, body
    assert "frozen_frames" in codes(body, "warning")


def test_check_before_a_render_is_a_user_error_pointing_at_render(demo: Path, asr: Path) -> None:
    result = invoke("check", "demo", "--final", "--json")

    assert result.exit_code == 1
    body = json.loads(result.stdout)
    assert "render demo --final" in body["hint"]


def test_a_passing_preview_check_marks_the_check_stage_done(demo: Path, asr: Path) -> None:
    render("--preview")
    hear(asr, timeline(demo)["words"])

    check("--preview")

    state = json.loads((demo / "state.json").read_text(encoding="utf-8"))
    assert state["stages"]["check"]["status"] == "done"
    assert os.path.exists(demo / "check" / "report.json")


def test_loudness_off_target_blocks_a_final_but_only_warns_on_a_preview(
    demo: Path, asr: Path
) -> None:
    render("--preview", "--format", "9x16")
    render("--final", "--format", "9x16")
    hear(asr, timeline(demo)["words"])
    # Mastered to -14 LUFS and -1.5 dBTP; check now judges against stricter targets.
    toml = demo / "project.toml"
    toml.write_text(
        toml.read_text(encoding="utf-8")
        + "\n[master]\nintegrated_lufs = -20\ntrue_peak_db = -20\n",
        encoding="utf-8",
    )

    code, body = check("--preview")
    assert code == 0, body
    assert {"loudness", "true_peak"} <= set(codes(body, "warning"))

    code, body = check("--final")
    assert code == 1, body
    blocking = {i["code"]: i for i in body["issues"] if i["severity"] == "blocking"}
    assert {"loudness", "true_peak"} <= set(blocking)
    assert "render demo --final" in blocking["loudness"]["fix"]
