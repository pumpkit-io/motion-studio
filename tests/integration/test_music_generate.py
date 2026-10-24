"""`reelcut music` with the real ACE-Step environment: a 60 s instrumental bed on this machine.

Uses the real cache and its heavy-model lock; run `reelcut setup --music` first.
"""

import json
import time
from pathlib import Path

import pytest
import soundfile as sf
from typer.testing import CliRunner

from reelcut.analysis import Span, TranscribedWord, analyse_transcript
from reelcut.analysis.models import ClipInfo
from reelcut.cli import app
from reelcut.lang import load_language
from reelcut.music import acestep

pytestmark = [pytest.mark.slow, pytest.mark.mac, pytest.mark.music]

runner = CliRunner()


def invoke(*args: str | Path):
    return runner.invoke(app, [str(a) for a in args])


def talking_clip(seconds: float):
    """One unbroken utterance of 0.3 s words with 0.1 s gaps, so the draft keeps all of it."""
    words: list[TranscribedWord] = []
    t = 0.5
    while t + 0.3 < seconds - 0.5:
        words.append(TranscribedWord(text="word", start=round(t, 3), end=round(t + 0.3, 3)))
        t += 0.4
    info = ClipInfo(id="c1", role="aroll", source="raw/c1.mov", duration_s=seconds)
    return analyse_transcript(info, words, [Span(start=0.0, end=seconds)], load_language("en"))


def test_music_generates_a_60_second_instrumental(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if acestep.installed() is None:
        pytest.skip("run `reelcut setup --music` first")
    ws = tmp_path / "reels"
    assert invoke("init", ws).exit_code == 0
    take = tmp_path / "take.mov"
    take.write_bytes(b"not really a movie")
    monkeypatch.chdir(ws)
    assert invoke("new", "demo", "--from", take).exit_code == 0
    project = ws / "projects" / "demo"
    (project / "analysis" / "c1.json").write_text(talking_clip(57.5).model_dump_json())
    assert invoke("plan", "draft", "demo").exit_code == 0
    edl = json.loads((project / "edl.json").read_text())
    edl["music"] = {
        "mode": "generate",
        "prompt": "minimal electronic, warm analog synths, soft punchy drums, confident, "
        "optimistic, instrumental",
        "bpm": 100,
        "seed": 1,
    }
    (project / "edl.json").write_text(json.dumps(edl))

    started = time.monotonic()
    result = invoke("music", "demo", "--json")
    elapsed = time.monotonic() - started

    assert result.exit_code == 0, result.output
    info = json.loads(result.stdout)
    print(f"music: {info['duration_s']} s bed in {elapsed:.1f} s; attempts {info['attempts']}")
    assert info["duration_s"] == pytest.approx(60, abs=1)
    assert sf.info(str(project / "build" / "music.wav")).duration == pytest.approx(60, abs=1.5)
    assert info["licence"] == acestep.installed().licence  # pyright: ignore[reportOptionalMemberAccess]
    assert info["attempts"][-1]["accepted"] is True
    assert len(info["beats"]) > 30
    validate = invoke("plan", "validate", "demo")
    assert validate.exit_code == 0, validate.output
