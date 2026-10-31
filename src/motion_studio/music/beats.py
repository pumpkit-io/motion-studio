"""Tempo, beat and bar grid, sections and named hits of the music bed, in seconds from its start.

The bed starts at output time zero, so these times are output seconds.
"""

from dataclasses import dataclass, field
from itertools import pairwise
from pathlib import Path
from typing import Literal

import librosa
import numpy as np

SR = 22050
ONSET_HOP = 256
BAND_HOP = 512
BEATS_PER_BAR = 4
# librosa's tempo comes from coarse bins (119.8 bpm reads as 117.5); refine within this ratio.
SEARCH = 0.04
SEARCH_STEP_BPM = 0.02
BAND_EDGES_HZ = (0.0, 150.0, 1000.0, 5000.0)
CHANGE_DB = 3.0
# Frames this far below the loudest frame are silence.
SILENCE_DB = -60.0
QUIETER_DB = 3.0
TAIL_MIN_S = 0.5
# Section changes override the onset tempo only past this disagreement, above their own jitter.
SECTION_TOLERANCE = 0.015
MIN_SECTION_SPAN_BARS = 8
MAX_OFF_GRID_BARS = 0.25

HitName = Literal["intro_end", "build", "drop", "ending"]
TempoSource = Literal["onsets", "sections"]


@dataclass(frozen=True)
class Section:
    start_s: float
    end_s: float
    energy_db: float


@dataclass(frozen=True)
class Hit:
    name: HitName
    time_s: float


@dataclass
class BedAnalysis:
    tracker_bpm: float | None = None
    bpm: float | None = None
    tempo_from: TempoSource | None = None
    beats: list[float] = field(default_factory=lambda: list[float]())
    bars: list[float] = field(default_factory=lambda: list[float]())
    sections: list[Section] = field(default_factory=lambda: list[Section]())
    hits: list[Hit] = field(default_factory=lambda: list[Hit]())


def analyze_bed(wav: Path, until_s: float | None = None) -> BedAnalysis:
    """The bed's grid and structure; beats and bars stop at `until_s`, sections and hits do not."""
    y, _ = librosa.load(wav, sr=SR, mono=True)
    tempo, tracked = librosa.beat.beat_track(y=y, sr=SR, units="time", trim=False)
    tracker = float(np.asarray(tempo).reshape(-1)[0]) if np.size(tempo) else 0.0
    if tracker <= 0 or np.size(tracked) == 0:
        return BedAnalysis()
    duration = len(y) / SR
    onsets = librosa.onset.onset_strength(y=y, sr=SR, hop_length=ONSET_HOP)
    bpm, phase = _comb(onsets, SR / ONSET_HOP, tracker * (1 - SEARCH), tracker * (1 + SEARCH))
    bands = _band_power(y)
    music_end = _music_end(bands, SR / BAND_HOP)
    bar_s = BEATS_PER_BAR * 60 / bpm
    # The fade into trailing silence lands off the grid, so it is the ending, not a section change.
    changes = [c for c in _changes(bands, SR / BAND_HOP, bar_s) if c < music_end - bar_s / 2]
    tempo_from: TempoSource = "onsets"
    by_sections = _section_bpm(changes, bpm)
    if by_sections is not None and abs(by_sections - bpm) > SECTION_TOLERANCE * bpm:
        bpm, phase = _comb(onsets, SR / ONSET_HOP, by_sections, by_sections)
        tempo_from = "sections"
    beat = 60 / bpm
    first = phase % beat
    downbeat = first + _bar_offset(changes, first, beat) * beat
    starts = [_snap(c, downbeat, beat) for c in changes]
    sections = _sections(bands, SR / BAND_HOP, music_end, starts)
    end = duration if until_s is None else min(until_s, duration)
    return BedAnalysis(
        tracker_bpm=round(tracker, 1),
        bpm=round(bpm, 2),
        tempo_from=tempo_from,
        beats=_grid(first, beat, end),
        bars=_grid(downbeat, BEATS_PER_BAR * beat, end),
        sections=sections,
        hits=_hits(sections, duration),
    )


def _comb(onsets: np.ndarray, fps: float, lo_bpm: float, hi_bpm: float) -> tuple[float, float]:
    """The tempo in [lo, hi] and the phase (s) whose beat grid collects the most onset strength."""
    frames = np.arange(len(onsets))
    best = (-1.0, lo_bpm, 0.0)
    for bpm in np.arange(lo_bpm, hi_bpm + SEARCH_STEP_BPM / 2, SEARCH_STEP_BPM):
        period = 60 / bpm * fps
        count = int((len(onsets) - 1) // period)
        if count < 1:
            continue
        phases = np.arange(0, period, 0.5)
        idx = phases[:, None] + np.arange(count)[None, :] * period
        scores = np.interp(idx, frames, onsets).mean(axis=1)
        i = int(np.argmax(scores))
        if scores[i] > best[0]:
            best = (float(scores[i]), float(bpm), float(phases[i] / fps))
    return best[1], best[2]


def _band_power(y: np.ndarray) -> np.ndarray:
    """Power per frame in the bands below 150 Hz, 150 Hz to 1 kHz, 1 to 5 kHz and above."""
    power = np.abs(librosa.stft(y, n_fft=2048, hop_length=BAND_HOP)) ** 2
    freqs = librosa.fft_frequencies(sr=SR, n_fft=2048)
    edges = (*BAND_EDGES_HZ, SR)
    return np.stack([power[(freqs >= a) & (freqs < b)].sum(axis=0) for a, b in pairwise(edges)])


def _music_end(bands: np.ndarray, fps: float) -> float:
    total = bands.sum(axis=0)
    audible = np.flatnonzero(total >= total.max() * 10 ** (SILENCE_DB / 10))
    return round(float((audible[-1] + 1) / fps), 3) if audible.size else 0.0


def _changes(bands: np.ndarray, fps: float, bar_s: float) -> list[float]:
    """Times where the band levels over the next bar differ from the last bar by CHANGE_DB."""
    window = max(1, round(bar_s * fps))
    frames = bands.shape[1]
    if frames <= 2 * window:
        return []
    floor = float(bands.mean(axis=1).max()) * 1e-6 + 1e-20
    sums = np.cumsum(np.pad(bands, ((0, 0), (1, 0))), axis=1)
    t = np.arange(window, frames - window)
    before = 10 * np.log10((sums[:, t] - sums[:, t - window]) / window + floor)
    after = 10 * np.log10((sums[:, t + window] - sums[:, t]) / window + floor)
    novelty = np.sqrt(((after - before) ** 2).mean(axis=0))
    return [float(t[p] / fps) for p in _peaks(novelty, CHANGE_DB, window)]


def _peaks(x: np.ndarray, height: float, distance: int) -> list[int]:
    """Local maxima of at least `height`, the higher kept when two are within `distance`."""
    inner = np.flatnonzero((x[1:-1] >= height) & (x[1:-1] > x[:-2]) & (x[1:-1] >= x[2:])) + 1
    kept: list[int] = []
    for i in sorted(inner.tolist(), key=lambda i: -x[i]):
        if all(abs(i - k) >= distance for k in kept):
            kept.append(i)
    return sorted(kept)


def _section_bpm(changes: list[float], bpm: float) -> float | None:
    """The tempo that puts every section change on a bar line, when the changes span enough bars."""
    if len(changes) < 2:
        return None
    bar = BEATS_PER_BAR * 60 / bpm
    times = np.asarray(changes)
    counts = np.round((times - times[0]) / bar)
    if counts[-1] < MIN_SECTION_SPAN_BARS:
        return None
    slope, offset = np.polyfit(counts, times, 1)
    if np.max(np.abs(times - (offset + slope * counts))) > MAX_OFF_GRID_BARS * slope:
        return None
    return float(BEATS_PER_BAR * 60 / slope)


def _bar_offset(changes: list[float], first: float, beat: float) -> int:
    """Beats from the first beat to the first downbeat: where most section changes fall."""
    if not changes:
        return 0
    slots = [round((c - first) / beat) % BEATS_PER_BAR for c in changes]
    return max(range(BEATS_PER_BAR), key=lambda s: (slots.count(s), -s))


def _snap(t: float, downbeat: float, beat: float) -> float:
    """To the nearest bar line when one is within a beat, else to the nearest beat."""
    bar = BEATS_PER_BAR * beat
    on_bar = downbeat + round((t - downbeat) / bar) * bar
    if abs(on_bar - t) <= beat:
        return on_bar
    return downbeat + round((t - downbeat) / beat) * beat


def _grid(start: float, step: float, end: float) -> list[float]:
    count = int(np.floor((end - start) / step - 1e-9)) + 1 if end > start else 0
    return [round(start + i * step, 3) for i in range(max(0, count))]


def _sections(
    bands: np.ndarray, fps: float, music_end: float, starts: list[float]
) -> list[Section]:
    """The music up to its end cut at each change, energy relative to the loudest section."""
    cuts = sorted({round(s, 3) for s in starts if 0 < s < music_end})
    edges = [0.0, *cuts, music_end]
    total = bands.sum(axis=0)
    levels: list[float] = []
    for a, b in pairwise(edges):
        chunk = total[int(a * fps) : max(int(a * fps) + 1, int(b * fps))]
        levels.append(10 * float(np.log10(chunk.mean() + 1e-20)))
    peak = max(levels)
    return [
        Section(start_s=a, end_s=b, energy_db=round(level - peak, 1))
        for (a, b), level in zip(pairwise(edges), levels, strict=True)
    ]


def _hits(sections: list[Section], duration: float) -> list[Hit]:
    """intro_end, build, drop and ending, each only when the bed has it."""
    if len(sections) < 2:
        return []
    hits = [Hit("intro_end", sections[1].start_s)]
    loudest = max(range(len(sections)), key=lambda i: sections[i].energy_db)
    if loudest == 0:
        return hits
    if loudest >= 2:
        hits.append(Hit("build", sections[loudest - 1].start_s))
    hits.append(Hit("drop", sections[loudest].start_s))
    last = sections[-1]
    if len(sections) - 1 > loudest and last.energy_db <= -QUIETER_DB:
        hits.append(Hit("ending", last.start_s))
    elif last.end_s < duration - TAIL_MIN_S:
        hits.append(Hit("ending", last.end_s))
    return hits
