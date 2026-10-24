"""The vocal check: how much of a music bed Silero VAD hears as a voice.

ACE-Step has no hard instrumental switch, so a generated bed that sings is caught here and
regenerated with another seed.
"""

from pathlib import Path

import librosa
import numpy as np

from reelcut.asr.vad import SAMPLE_RATE, SileroVad

# A bed with more of its length heard as voice than this is rejected.
MAX_SPEECH_RATIO = 0.2


def speech_ratio(wav: Path, vad_model: Path | None = None) -> float:
    """The fraction of the file's length that the VAD marks as speech, 0 to 1."""
    samples, _ = librosa.load(wav, sr=SAMPLE_RATE, mono=True)
    if len(samples) == 0:
        return 0.0
    spans = SileroVad(vad_model).speech(samples.astype(np.float32))
    speech = sum(s.end - s.start for s in spans)
    return min(1.0, speech / (len(samples) / SAMPLE_RATE))


def has_vocals(wav: Path, vad_model: Path | None = None) -> bool:
    return speech_ratio(wav, vad_model) > MAX_SPEECH_RATIO
