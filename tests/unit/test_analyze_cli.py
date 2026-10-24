"""`reelcut analyze` on ingested tiny clips, with a stand-in for the speech-to-text worker.

The stand-in replaces only the model subprocess: it returns scripted VAD regions and words,
reports whether it saw the heavy-model lock held, and logs each request it receives.
"""

import json
import os
import shutil
import stat
import sys
import textwrap
import tomllib
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from reelcut.cli import app

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")

TINY = Path(__file__).resolve().parents[1] / "fixtures" / "tiny.mp4"

ABANDONED = ["The", "most", "important", "thing", "to", "remember", "is"]
WINNER = [*ABANDONED, "to", "keep", "it", "short."]

FAKE_WORKER = """
import fcntl, json, os, sys
from reelcut.paths import locks_dir
from reelcut.state import HEAVY_MODEL_LOCK

request = json.load(sys.stdin)
with open(locks_dir() / HEAVY_MODEL_LOCK, "a+") as handle:
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        held = False
        fcntl.flock(handle, fcntl.LOCK_UN)
    except BlockingIOError:
        held = True
script = json.loads(open(os.environ["FAKE_ASR_SCRIPT"]).read())
results = []
for job in request["jobs"]:
    clip = script[job["id"]]
    language = job["language"] or clip["language"]
    words = [
        {"text": t, "start": s, "end": e, "conf": 0.9}
        for t, s, e in clip["words"]
    ]
    results.append({
        "id": job["id"],
        "vad": [{"start": s, "end": e} for s, e in clip["vad"]],
        "language": {"code": language, "confidence": 0.97},
        "words": words,
    })
with open(os.environ["FAKE_ASR_LOG"], "a") as log:
    log.write(json.dumps({"held": held, "jobs": request["jobs"], "pid": os.getpid()}) + "\\n")
print(json.dumps({"pid": os.getpid(), "peak_rss_mb": 1.0, "results": results}))
"""

runner = CliRunner()


def invoke(*args: str | Path):
    return runner.invoke(app, [str(a) for a in args])


def spoken(words: list[str], start: float = 0.1, step: float = 0.12) -> list[list[Any]]:
    return [
        [w, round(start + i * step, 3), round(start + i * step + 0.1, 3)]
        for i, w in enumerate(words)
    ]


@pytest.fixture(autouse=True)
def no_disk_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REELCUT_MIN_FREE_GB", "0")


@pytest.fixture
def worker_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    worker = tmp_path / "fake-asr-worker"
    worker.write_text(f"#!{sys.executable}\n{textwrap.dedent(FAKE_WORKER)}", encoding="utf-8")
    worker.chmod(worker.stat().st_mode | stat.S_IEXEC)
    script = tmp_path / "script.json"
    script.write_text(
        json.dumps(
            {
                "c1": {"language": "en", "vad": [[0.05, 1.0]], "words": spoken(ABANDONED)},
                "c2": {"language": "en", "vad": [[0.05, 1.6]], "words": spoken(WINNER)},
            }
        ),
        encoding="utf-8",
    )
    log = tmp_path / "worker.log"
    monkeypatch.setenv("REELCUT_ASR_WORKER", str(worker))
    monkeypatch.setenv("FAKE_ASR_SCRIPT", str(script))
    monkeypatch.setenv("FAKE_ASR_LOG", str(log))
    return log


def requests(log: Path) -> list[dict[str, Any]]:
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    ws = tmp_path / "reels"
    assert invoke("init", ws).exit_code == 0
    monkeypatch.chdir(ws)
    first, second = tmp_path / "take 1.mp4", tmp_path / "take 2.mp4"
    shutil.copy(TINY, first)
    shutil.copy(TINY, second)
    result = invoke("new", "demo", "--from", first, second)
    assert result.exit_code == 0, result.output
    result = invoke("ingest", "demo", "--json")
    assert result.exit_code == 0, result.output
    return ws / "projects" / "demo"


def analyze(*extra: str) -> dict[str, Any]:
    result = invoke("analyze", "demo", "--json", *extra)
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


def test_analyze_writes_each_clip_the_retakes_and_the_packed_index(
    project: Path, worker_log: Path
) -> None:
    out = analyze()

    assert out["ok"] is True
    assert out["language"] == "en"
    assert {c["id"]: (c["language"], c["words"]) for c in out["clips"]} == {
        "c1": ("en", 7),
        "c2": ("en", 11),
    }
    c2 = json.loads((project / "analysis" / "c2.json").read_text(encoding="utf-8"))
    assert c2["language"] == {"code": "en", "confidence": 0.97}
    assert [w["id"] for w in c2["words"]][:2] == ["c2.w0", "c2.w1"]
    assert c2["vad"] == [{"start": 0.05, "end": 1.6}]
    retakes = json.loads((project / "analysis" / "retakes.json").read_text(encoding="utf-8"))
    assert [(c["winner"], c["members"]) for c in retakes["clusters"]] == [
        ("c2.s0", ["c2.s0", "c1.s0"])
    ]
    packed = (project / "analysis" / "packed.md").read_text(encoding="utf-8")
    assert packed.startswith("# Project: demo · language: en (c1, c2)")
    assert "c2.s0" in packed and "keep it short." in packed
    assert out["packed"] == str(project / "analysis" / "packed.md")


def test_the_worker_runs_once_for_all_clips_holding_the_heavy_model_lock_and_exits(
    project: Path, worker_log: Path
) -> None:
    out = analyze()

    [request] = requests(worker_log)
    assert request["held"] is True
    assert [job["id"] for job in request["jobs"]] == ["c1", "c2"]
    assert all(job["language"] is None for job in request["jobs"])
    assert out["asr"]["worker_pid"] == request["pid"]
    with pytest.raises(ProcessLookupError):
        os.kill(request["pid"], 0)


def test_a_second_run_with_nothing_changed_does_not_start_the_worker(
    project: Path, worker_log: Path
) -> None:
    analyze()
    packed = project / "analysis" / "packed.md"
    before = packed.stat().st_mtime_ns

    out = analyze()

    assert out["noop"] is True
    assert len(requests(worker_log)) == 1
    assert packed.stat().st_mtime_ns == before


def test_clip_option_re_transcribes_only_that_clip(project: Path, worker_log: Path) -> None:
    analyze()

    out = analyze("--clip", "c2")

    assert [job["id"] for job in requests(worker_log)[1]["jobs"]] == ["c2"]
    assert {c["id"]: c["status"] for c in out["clips"]} == {"c1": "unchanged", "c2": "analysed"}


def test_a_configured_language_is_forced_on_every_clip(project: Path, worker_log: Path) -> None:
    toml = project / "project.toml"
    toml.write_text(
        toml.read_text(encoding="utf-8") + '\n[defaults]\nlanguage = "it"\n', encoding="utf-8"
    )

    out = analyze()

    assert {job["language"] for job in requests(worker_log)[0]["jobs"]} == {"it"}
    assert out["language"] == "it"
    assert out["language_source"] == "config"


def test_the_crisper_fillers_backend_fails_with_exit_2(project: Path, worker_log: Path) -> None:
    toml = project / "project.toml"
    toml.write_text(
        toml.read_text(encoding="utf-8") + '\n[asr]\nfillers_backend = "crisper"\n',
        encoding="utf-8",
    )

    result = invoke("analyze", "demo", "--json")

    assert result.exit_code == 2
    assert "not implemented in v0.1.0" in json.loads(result.stdout)["error"]
    assert requests(worker_log) == []


def test_missing_models_fail_with_exit_2_and_point_at_setup(project: Path) -> None:
    result = invoke("analyze", "demo", "--json")

    assert result.exit_code == 2, result.output
    body = json.loads(result.stdout)
    assert "setup" in (body["hint"] or "") or "extra" in (body["hint"] or "")


def test_analyze_before_ingest_is_a_user_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = tmp_path / "reels"
    assert invoke("init", ws).exit_code == 0
    monkeypatch.chdir(ws)
    assert invoke("new", "demo").exit_code == 0

    result = invoke("analyze", "demo")

    assert result.exit_code == 1
    assert "not ingested" in result.stderr


def test_setup_with_crisper_fails_with_exit_2() -> None:
    result = invoke("setup", "--crisper", "--json")

    assert result.exit_code == 2
    assert json.loads(result.stdout)["ok"] is False


PHOTO = Path(__file__).resolve().parents[1] / "fixtures" / "faces" / "neil_armstrong_960.jpg"


def still_video(path: Path, seconds: float = 3.0) -> Path:
    """A silent clip of one unchanging colour: no speech and no motion."""
    from reelcut.media.ffmpeg import run_ffmpeg

    source = f"color=c=0x336699:s=320x180:r=30:d={seconds}"
    run_ffmpeg(["-f", "lavfi", "-i", source, "-c:v", "libx264", "-pix_fmt", "yuv420p", path])
    return path


@pytest.fixture
def mixed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A project with a talking clip (c1), a still B-roll clip (b1) and a photo (i1)."""
    ws = tmp_path / "reels"
    assert invoke("init", ws).exit_code == 0
    monkeypatch.chdir(ws)
    take = tmp_path / "take.mp4"
    shutil.copy(TINY, take)
    result = invoke("new", "demo", "--from", take, still_video(tmp_path / "still.mp4"), PHOTO)
    assert result.exit_code == 0, result.output
    result = invoke("ingest", "demo", "--json")
    assert result.exit_code == 0, result.output
    return ws / "projects" / "demo"


def clip_json(project: Path, clip_id: str) -> dict[str, Any]:
    return json.loads((project / "analysis" / f"{clip_id}.json").read_text(encoding="utf-8"))


def clip_table(project: Path) -> dict[str, Any]:
    return tomllib.loads((project / "project.toml").read_text(encoding="utf-8"))["clips"]


def faces_script(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, script: dict[str, str]) -> None:
    path = tmp_path / "faces.json"
    path.write_text(json.dumps(script), encoding="utf-8")
    monkeypatch.setenv("FAKE_FACES_SCRIPT", str(path))


def test_each_clip_gets_shots_faces_and_its_static_stretches(mixed: Path, worker_log: Path) -> None:
    analyze()

    c1, b1, i1 = (clip_json(mixed, c) for c in ("c1", "b1", "i1"))
    assert c1["shots"] == [{"start": 0.0, "end": 2.0}]
    assert c1["static"] == []
    assert [s["t"] for s in c1["faces"]["samples"]] == [0.0, 0.5, 1.0, 1.5]
    assert c1["faces"]["sample_fps"] == 2
    assert b1["static"] == [{"start": 0.0, "end": 3.0}]
    assert b1["shots"] == [{"start": 0.0, "end": 3.0}]
    assert [s["t"] for s in i1["faces"]["samples"]] == [0.0]


def test_the_face_pass_runs_once_for_all_clips_under_the_heavy_model_lock(
    mixed: Path, worker_log: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "faces.log"
    monkeypatch.setenv("FAKE_FACES_LOG", str(log))

    analyze()

    [request] = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert request["held"] is True
    assert [(j["id"], j["kind"]) for j in request["jobs"]] == [
        ("c1", "video"),
        ("b1", "video"),
        ("i1", "image"),
    ]


def test_roles_are_finalised_from_speech_and_faces(
    mixed: Path, worker_log: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    faces_script(tmp_path, monkeypatch, {"c1": "none"})

    out = analyze()

    clips = clip_table(mixed)
    assert {c: (clips[c]["role"], clips[c]["auto_role"]) for c in clips} == {
        "c1": ("broll", "broll"),
        "b1": ("broll", "broll"),
        "i1": ("image", "image"),
    }
    assert {c["id"]: c["role"] for c in out["clips"]} == {
        "c1": "broll",
        "b1": "broll",
        "i1": "image",
    }
    assert clip_json(mixed, "c1")["clip"]["role"] == "broll"


def test_a_creator_override_wins_over_the_final_role(mixed: Path, worker_log: Path) -> None:
    toml = mixed / "project.toml"
    text = toml.read_text(encoding="utf-8")
    toml.write_text(text.replace('role = "aroll"', 'role = "broll"', 1), encoding="utf-8")

    analyze()

    c1 = clip_table(mixed)["c1"]
    assert (c1["role"], c1["auto_role"]) == ("broll", "aroll")
    assert "## c1 ·" in (mixed / "analysis" / "assets.md").read_text(encoding="utf-8")


def test_assets_md_lists_b_roll_and_images_and_keeps_written_descriptions(
    mixed: Path, worker_log: Path
) -> None:
    out = analyze()

    assets = mixed / "analysis" / "assets.md"
    text = assets.read_text(encoding="utf-8")
    assert out["assets"] == str(assets)
    assert "## c1 ·" not in text
    assert "## b1 · still.mp4\n- file: raw/still.mp4 · 3.0s · 320x180 · 1 shot\n" in text
    assert "- contact sheet: contact/b1.png\n- description:\n" in text
    assert "## i1 · neil_armstrong_960.jpg\n- file: raw/neil_armstrong_960.jpg · still" in text

    assets.write_text(
        text.replace("- description:\n", "- description: A blue screen.\n", 1), encoding="utf-8"
    )
    analyze("--clip", "b1")

    assert "- description: A blue screen.\n" in assets.read_text(encoding="utf-8")


def test_the_yunet_fallback_prints_a_warning_and_is_recorded_in_state(
    mixed: Path, worker_log: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_FACES_DETECTOR", "yunet")

    result = invoke("analyze", "demo")

    assert result.exit_code == 0, result.output
    [line] = [x for x in result.stderr.splitlines() if "YuNet" in x]
    assert line.startswith("warning: ")
    assert "MediaPipe face model is not in the cache" in line
    state = json.loads((mixed / "state.json").read_text(encoding="utf-8"))
    assert any("YuNet" in w for w in state["stages"]["analyze"]["warnings"])
