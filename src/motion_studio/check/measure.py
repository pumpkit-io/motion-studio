"""Measure a rendered file: loudness, black and frozen stretches, and energy per band."""

import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import numpy.typing as npt
import soundfile as sf

from motion_studio.errors import InternalError
from motion_studio.media.ffmpeg import run_ffmpeg, run_ffprobe

# blackdetect and freezedetect thresholds: shorter blips are encoder noise, not a defect.
BLACK_MIN_S = 0.5
BLACK_PIXEL_THRESHOLD = 0.10
FREEZE_MIN_S = 2.0
FREEZE_NOISE = "-60dB"
# Band edges in Hz for the small-speaker check: sub and bass, low mids, presence, air.
BANDS: dict[str, tuple[float, float]] = {
    "below_150_hz": (0.0, 150.0),
    "150_hz_to_1_khz": (150.0, 1000.0),
    "1_to_5_khz": (1000.0, 5000.0),
    "above_5_khz": (5000.0, float("inf")),
}
BAND_SAMPLE_RATE = 48_000
BAND_WINDOW = 8192
SILENT_DB = -120.0


@dataclass(frozen=True)
class Stretch:
    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class Measurement:
    duration_s: float
    integrated_lufs: float
    true_peak_db: float
    lra: float
    black: list[Stretch] = field(default_factory=lambda: list[Stretch]())
    frozen: list[Stretch] = field(default_factory=lambda: list[Stretch]())
    bands: dict[str, float] = field(default_factory=lambda: dict[str, float]())

    @property
    def bass_over_top_db(self) -> float:
        """How far the energy under 150 Hz sits above the energy over 1 kHz, in dB."""
        top = _power(self.bands["1_to_5_khz"]) + _power(self.bands["above_5_khz"])
        return self.bands["below_150_hz"] - _db(top)


def measure(path: Path) -> Measurement:
    duration = float(
        run_ffprobe(["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path])
    )
    video = (
        f"blackdetect=d={BLACK_MIN_S}:pix_th={BLACK_PIXEL_THRESHOLD},"
        f"freezedetect=n={FREEZE_NOISE}:d={FREEZE_MIN_S}"
    )
    lines = run_ffmpeg(
        ["-i", path, "-vf", video, "-af", "ebur128=peak=true:framelog=verbose", "-f", "null", "-"]
    )
    text = "\n".join(lines)
    summary = text[text.rfind("Summary:") :] if "Summary:" in text else ""
    integrated = re.search(r"I:\s+(-?[\d.]+|-inf) LUFS", summary)
    lra = re.search(r"LRA:\s+(-?[\d.]+) LU", summary)
    peak = re.search(r"Peak:\s+(-?[\d.]+|-inf) dBFS", summary)
    if not (integrated and lra and peak):
        raise InternalError(f"could not read the ebur128 summary of {path}")
    return Measurement(
        duration_s=duration,
        integrated_lufs=float(integrated.group(1)),
        true_peak_db=float(peak.group(1)),
        lra=float(lra.group(1)),
        black=[
            Stretch(float(a), float(b))
            for a, b in re.findall(r"black_start:\s*([\d.]+)\s+black_end:\s*([\d.]+)", text)
        ],
        frozen=_freezes(text, duration),
        bands=band_energy(path),
    )


def band_energy(path: Path) -> dict[str, float]:
    """Mean-square energy of `path`'s mono downmix per band, in dB full scale."""
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "bands.wav"
        run_ffmpeg(
            ["-v", "error", "-i", path, "-map", "0:a:0", "-ac", "1",
             "-ar", str(BAND_SAMPLE_RATE), "-c:a", "pcm_f32le", "-y", wav]
        )  # fmt: skip
        samples, rate = sf.read(wav, dtype="float32")
    return band_levels(np.asarray(samples, dtype=np.float64), int(rate))


def band_levels(samples: npt.NDArray[np.float64], rate: int) -> dict[str, float]:
    """Welch-averaged spectrum summed per band; a full-scale sine reads about -3 dB."""
    n = BAND_WINDOW
    if len(samples) < n:
        samples = np.pad(samples, (0, n - len(samples)))
    window = np.hanning(n)
    starts = range(0, len(samples) - n + 1, n // 2)
    power = np.zeros(n // 2 + 1)
    for start in starts:
        power += np.abs(np.fft.rfft(samples[start : start + n] * window)) ** 2
    # Parseval: scale so the bins sum to the signal's mean square.
    power *= 2 / (len(starts) * n * float(np.sum(window**2)))
    freqs = np.fft.rfftfreq(n, 1 / rate)
    return {
        name: _db(float(power[(freqs >= lo) & (freqs < hi)].sum()))
        for name, (lo, hi) in BANDS.items()
    }


def _db(power: float) -> float:
    return round(max(SILENT_DB, 10 * float(np.log10(max(power, 1e-30)))), 1)


def _power(db: float) -> float:
    return float(10 ** (db / 10))


def _freezes(text: str, duration: float) -> list[Stretch]:
    starts = [float(s) for s in re.findall(r"freeze_start:\s*([\d.]+)", text)]
    ends = [float(e) for e in re.findall(r"freeze_end:\s*([\d.]+)", text)]
    # A freeze that lasts to the end of the file never logs its end.
    ends += [duration] * (len(starts) - len(ends))
    return [Stretch(s, e) for s, e in zip(starts, ends, strict=True)]
