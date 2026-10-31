"""Measure a rendered file in one ffmpeg pass: loudness, black stretches and frozen stretches."""

import re
from dataclasses import dataclass, field
from pathlib import Path

from motion_studio.errors import InternalError
from motion_studio.media.ffmpeg import run_ffmpeg, run_ffprobe

# blackdetect and freezedetect thresholds: shorter blips are encoder noise, not a defect.
BLACK_MIN_S = 0.5
BLACK_PIXEL_THRESHOLD = 0.10
FREEZE_MIN_S = 2.0
FREEZE_NOISE = "-60dB"


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
    )


def _freezes(text: str, duration: float) -> list[Stretch]:
    starts = [float(s) for s in re.findall(r"freeze_start:\s*([\d.]+)", text)]
    ends = [float(e) for e in re.findall(r"freeze_end:\s*([\d.]+)", text)]
    # A freeze that lasts to the end of the file never logs its end.
    ends += [duration] * (len(starts) - len(ends))
    return [Stretch(s, e) for s, e in zip(starts, ends, strict=True)]
