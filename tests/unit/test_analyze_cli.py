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
