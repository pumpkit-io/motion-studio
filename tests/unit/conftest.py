import stat
import sys
import textwrap
from collections.abc import Iterator
from pathlib import Path

import pytest

from reelcut.media.ffmpeg import ffmpeg_caps


class FakeTools:
    """A directory of stand-in executables that replaces PATH for one test."""

    def __init__(self, directory: Path) -> None:
        self.dir = directory

    def add(self, name: str, body: str) -> Path:
        script = self.dir / name
        script.write_text(f"#!{sys.executable}\n{textwrap.dedent(body)}", encoding="utf-8")
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        return script


@pytest.fixture
def fake_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeTools]:
    directory = tmp_path / "bin"
    directory.mkdir()
    monkeypatch.setenv("PATH", str(directory))
    ffmpeg_caps.cache_clear()
    yield FakeTools(directory)
    ffmpeg_caps.cache_clear()


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Keep tests out of the real machine-wide cache, including its heavy-model lock."""
    cache = tmp_path / "cache"
    monkeypatch.setenv("REELCUT_CACHE_DIR", str(cache))
    return cache


FAKE_FACE_WORKER = """
import fcntl, json, math, os, sys
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
script_path = os.environ.get("FAKE_FACES_SCRIPT")
script = json.loads(open(script_path).read()) if script_path else {}
detector = os.environ.get("FAKE_FACES_DETECTOR", "mediapipe")
fps = request["sample_fps"]
results = []
for job in request["jobs"]:
    frames = 1 if job["kind"] == "image" else max(1, math.ceil(job["duration_s"] * fps - 1e-6))
    face = {"cx": 0.5, "cy": 0.4, "w": 0.3, "h": 0.2, "score": 0.9}
    samples = [] if script.get(job["id"]) == "none" else [
        {"t": round(i / fps, 3), **face} for i in range(frames)
    ]
    results.append({"id": job["id"], "samples": samples})
log_path = os.environ.get("FAKE_FACES_LOG")
if log_path:
    with open(log_path, "a") as log:
        log.write(json.dumps({"held": held, "jobs": request["jobs"]}) + "\\n")
reason = None if detector == "mediapipe" else "the MediaPipe face model is not in the cache"
print(json.dumps({
    "pid": os.getpid(), "peak_rss_mb": 1.0, "detector": detector,
    "fallback_reason": reason, "results": results,
}))
"""


@pytest.fixture(autouse=True)
def fake_face_worker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Stand in for the face model subprocess: a centred face in every sampled frame.

    Set FAKE_FACES_SCRIPT to a JSON file mapping a clip ID to "none" for a clip without faces,
    FAKE_FACES_DETECTOR=yunet to report the fallback, and FAKE_FACES_LOG to log requests.
    """
    worker = tmp_path / "fake-face-worker"
    worker.write_text(f"#!{sys.executable}\n{textwrap.dedent(FAKE_FACE_WORKER)}", encoding="utf-8")
    worker.chmod(worker.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("REELCUT_FACE_WORKER", str(worker))
    return worker
