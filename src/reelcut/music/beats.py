"""Beat times of the music bed, in seconds from its start (which is output time zero)."""

from pathlib import Path

import librosa
import numpy as np


def detect_beats(wav: Path, until_s: float | None = None) -> tuple[float | None, list[float]]:
    """librosa's tempo estimate (None when it finds no beat) and the beats before `until_s`."""
    y, sr = librosa.load(wav, sr=22050, mono=True)
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units="time", trim=False)
    times = [round(float(t), 3) for t in np.asarray(beats).reshape(-1)]
    if until_s is not None:
        times = [t for t in times if t < until_s]
    bpm = float(np.asarray(tempo).reshape(-1)[0]) if np.size(tempo) else 0.0
    return (round(bpm, 1) if bpm > 0 and times else None), times
