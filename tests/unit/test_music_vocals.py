"""The vocal check with the real Silero VAD: speech is rejected, an instrumental is not."""

import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from reelcut.asr.vad import vad_model_path
from reelcut.music.vocals import has_vocals, speech_ratio

pytestmark = [pytest.mark.mac, pytest.mark.models]


@pytest.fixture
def vad_model(monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.delenv("REELCUT_CACHE_DIR", raising=False)
    path = vad_model_path()
    if not path.is_file():
        pytest.skip("run `reelcut setup` for the Silero VAD model")
    return path


def test_the_vocal_check_rejects_a_speech_wav(tmp_path: Path, vad_model: Path) -> None:
    if shutil.which("say") is None:
        pytest.skip("needs macOS `say`")
    speech = tmp_path / "speech.wav"
    text = "This is a voice over a music bed. It should never be accepted as an instrumental."
    subprocess.run(
        ["say", "-v", "Samantha", "-o", str(speech), "--data-format=LEI16@48000", text],
        check=True,
    )

    assert speech_ratio(speech, vad_model) > 0.5
    assert has_vocals(speech, vad_model)


def test_the_vocal_check_accepts_a_synth_pad(tmp_path: Path, vad_model: Path) -> None:
    sr = 48000
    t = np.arange(10 * sr) / sr
    chord = sum(np.sin(2 * np.pi * f * t) for f in (220.0, 277.2, 329.6)) / 6
    pad = tmp_path / "pad.wav"
    sf.write(pad, np.stack([chord, chord], axis=1).astype(np.float32), sr)

    assert not has_vocals(pad, vad_model)
