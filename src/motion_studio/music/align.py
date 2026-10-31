"""Fit a bed to a product video: a section hit on a scene start, the length on the scene total.

The bed is cut into pieces of itself played back to back. Before the hit, the head is trimmed,
and whole bars are repeated at a phrase boundary when the hit comes too early. After it, whole
bars are repeated or cut at the phrase boundary before the ending so the natural ending lands
on the end of the video, or, when there is too little room for that, the bed stops on a bar and
its last beat echoes out. Every join sits on a bar line under a 30 ms crossfade, so the beat
grid runs on unbroken and the hit is a downbeat of it.
"""

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import numpy as np
import soundfile as sf

from motion_studio.errors import UserError
from motion_studio.music.beats import BedAnalysis, Hit, HitName, Section

CROSSFADE_S = 0.03
PHRASE_BARS = 4
ECHO_BEATS = 4
ECHO_DECAY = 0.5
HEAD_FADE_S = 0.02
SAMPLE_RATE = 48000

Ending = Literal["natural", "echo"]


@dataclass(frozen=True)
class Piece:
    """Bed seconds [src_start, src_end) played from output second `out_start`."""

    src_start: float
    src_end: float
    out_start: float

    @property
    def out_end(self) -> float:
        return self.out_start + self.src_end - self.src_start


@dataclass(frozen=True)
class Edit:
    """Whole bars repeated (positive) or cut (negative) at output second `at_s`."""

    at_s: float
    bars: int


@dataclass
class Alignment:
    hit: HitName
    hit_src_s: float
    at_s: float
    duration_s: float
    pieces: list[Piece]
    edits: list[Edit]
    ending: Ending
    # Where the echo starts, in output seconds, when the ending is an echo.
    echo_at_s: float | None
    beat_s: float
    beats: list[float] = field(default_factory=lambda: list[float]())
    bars: list[float] = field(default_factory=lambda: list[float]())
    sections: list[Section] = field(default_factory=lambda: list[Section]())
    hits: list[Hit] = field(default_factory=lambda: list[Hit]())


def grid_period(bed: BedAnalysis) -> float:
    """The bed's beat length from its whole grid, more precise than its rounded bpm."""
    if len(bed.beats) < 2:
        raise UserError("the bed has no beat grid to align on", hint="try another seed")
    return (bed.beats[-1] - bed.beats[0]) / (len(bed.beats) - 1)


def plan_alignment(
    bed: BedAnalysis,
    bed_s: float,
    hit: HitName,
    at_s: float,
    duration_s: float,
    beats_per_bar: int,
) -> Alignment:
    """Where each piece of `bed` (analysed whole, `bed_s` long) plays so `hit` lands on `at_s`.

    Raises UserError when the bed has no such hit or it falls before the first full bar.
    """
    found = [h.time_s for h in bed.hits if h.name == hit]
    if not found or not bed.sections or not bed.bars:
        names = ", ".join(h.name for h in bed.hits) or "none"
        raise UserError(
            f"music.align: the bed has no {hit} hit (it has: {names})",
            hint='align another hit, try another "seed", or remove music.align',
        )
    beat = grid_period(bed)
    bar = beat * beats_per_bar
    h = found[0]
    pieces, edits = _before_hit(bed, h, at_s, bar)
    after, after_edits, ending, echo_src = _after_hit(bed, bed_s, h, at_s, duration_s, bar)
    pieces += after
    edits += after_edits
    echo_at = pieces[-1].out_end if echo_src is not None else None
    alignment = Alignment(
        hit=hit,
        hit_src_s=h,
        at_s=at_s,
        duration_s=duration_s,
        pieces=pieces,
        edits=edits,
        ending=ending,
        echo_at_s=echo_at,
        beat_s=beat,
    )
    _map_analysis(alignment, bed, bar)
    return alignment


def _before_hit(
    bed: BedAnalysis, h: float, at_s: float, bar: float
) -> tuple[list[Piece], list[Edit]]:
    if h >= at_s:
        return [Piece(h - at_s, h, 0.0)], []
    missing = at_s - h
    count = math.ceil(missing / bar - 1e-6)
    downbeat = bed.bars[0]
    boundaries = [s.start_s for s in bed.sections[1:] if s.start_s <= h] + [h]
    usable = [q for q in boundaries if q - downbeat >= bar - 1e-6]
    if not usable:
        raise UserError(
            f"music.align: the bed's hit at {h:.2f} s comes before its first full bar, so "
            "there is nothing to repeat before it",
            hint='align a later hit, or try another "seed"',
        )
    q = usable[0]
    span = min(PHRASE_BARS, math.floor((q - downbeat) / bar + 1e-6))
    head = count * bar - missing
    pieces = [Piece(head, q, 0.0)]
    edits: list[Edit] = []
    left = count
    while left > 0:
        n = min(span, left)
        start = pieces[-1].out_end
        pieces.append(Piece(q - n * bar, q, start))
        edits.append(Edit(start, n))
        left -= n
    if q < h:
        pieces.append(Piece(q, h, pieces[-1].out_end))
    return pieces, edits


def _after_hit(
    bed: BedAnalysis, bed_s: float, h: float, at_s: float, duration_s: float, bar: float
) -> tuple[list[Piece], list[Edit], Ending, float | None]:
    need = duration_s - at_s
    beat = grid_period(bed)
    music_end = bed.sections[-1].end_s
    # Past the music's end the bed holds its own ring-out, which plays on.
    bed_end = max(music_end, bed_s)
    have = music_end - h
    later = [s.start_s for s in bed.sections if s.start_s > h + 1e-6]
    if have <= need + beat:
        # Too short: repeat whole bars before the last section, so the ending lands by the end.
        count = math.floor((need - have) / bar + 1e-6)
        ends = [z for z in later if z - h >= bar - 1e-6]
        if count <= 0 or not ends:
            return [Piece(h, bed_end, at_s)], [], "natural", None
        z = ends[-1]
        span = min(PHRASE_BARS, math.floor((z - h) / bar + 1e-6))
        pieces = [Piece(h, z, at_s)]
        edits: list[Edit] = []
        left = count
        while left > 0:
            n = min(span, left)
            start = pieces[-1].out_end
            pieces.append(Piece(z - n * bar, z, start))
            edits.append(Edit(start, n))
            left -= n
        pieces.append(Piece(z, bed_end, pieces[-1].out_end))
        return pieces, edits, "natural", None
    # Too long: cut whole bars just before the ending section, if there is room to.
    count = math.ceil((have - need - beat) / bar - 1e-6)
    if later and later[-1] - count * bar >= h + bar - 1e-6:
        z = later[-1]
        first = Piece(h, z - count * bar, at_s)
        return (
            [first, Piece(z, bed_end, first.out_end)],
            [Edit(first.out_end, -count)],
            ("natural"),
            None,
        )
    echo = ECHO_BEATS * beat
    bars_kept = math.floor((need - echo) / bar + 1e-6)
    kept = bars_kept * bar if bars_kept >= 1 else max(1, math.floor((need - echo) / beat)) * beat
    stop = h + min(kept, need)
    return [Piece(h, stop, at_s)], [], "echo", stop


def _map_analysis(alignment: Alignment, bed: BedAnalysis, bar: float) -> None:
    """The bed's grid, sections and hits in output seconds, up to the end of the video."""
    shift = alignment.at_s - alignment.hit_src_s
    end = alignment.duration_s
    beat = alignment.beat_s
    alignment.beats = _grid((bed.beats[0] + shift) % beat, beat, end)
    alignment.bars = _grid((bed.bars[0] + shift) % bar, bar, end)
    sections: list[tuple[int, float, float]] = []
    for piece in alignment.pieces:
        for i, s in enumerate(bed.sections):
            a, b = max(piece.src_start, s.start_s), min(piece.src_end, s.end_s)
            if b - a <= 1e-6:
                continue
            out_a = piece.out_start + a - piece.src_start
            out_b = min(end, piece.out_start + b - piece.src_start)
            if out_a >= end:
                continue
            if sections and sections[-1][0] == i and abs(sections[-1][2] - out_a) < 1e-6:
                sections[-1] = (i, sections[-1][1], out_b)
            else:
                sections.append((i, out_a, out_b))
    if alignment.echo_at_s is not None and sections:
        last = sections[-1]
        sections[-1] = (last[0], last[1], end)
    alignment.sections = [
        Section(round(a, 3), round(b, 3), bed.sections[i].energy_db) for i, a, b in sections
    ]
    hits: list[Hit] = []
    for hit in bed.hits:
        if hit.name == "ending" and alignment.echo_at_s is not None:
            hits.append(Hit("ending", round(alignment.echo_at_s, 3)))
            continue
        out = _out_time(alignment.pieces, hit.time_s)
        if out is not None and out <= end:
            hits.append(Hit(hit.name, round(out, 3)))
    alignment.hits = hits


def _out_time(pieces: list[Piece], src: float) -> float | None:
    for piece in pieces:
        if piece.src_start - 1e-6 <= src < piece.src_end - 1e-6:
            return piece.out_start + src - piece.src_start
    last = pieces[-1]
    if abs(src - last.src_end) < 1e-6:
        return last.out_end
    return None


def _grid(start: float, step: float, end: float) -> list[float]:
    count = int(np.floor((end - start) / step - 1e-9)) + 1 if end > start else 0
    return [round(start + i * step, 3) for i in range(max(0, count))]


def render_alignment(source: Path, alignment: Alignment, out: Path) -> Path:
    """Write the aligned bed to `out`: 48 kHz stereo 16-bit, exactly the video's length."""
    y, rate = sf.read(str(source), always_2d=True, dtype="float64")
    if rate != SAMPLE_RATE or y.shape[1] != 2:
        raise UserError(f"{source} is not a 48 kHz stereo bed", hint="run music again")
    total = round(alignment.duration_s * rate)
    bed = np.zeros((total, 2))
    half = round(CROSSFADE_S * rate / 2)
    pieces = alignment.pieces
    for i, piece in enumerate(pieces):
        pre = half if i > 0 else 0
        post = half if i < len(pieces) - 1 or alignment.echo_at_s is not None else 0
        a = round(piece.src_start * rate) - pre
        b = round(piece.src_end * rate) + post
        chunk = _slice(y, a, b)
        if pre:
            chunk[: 2 * pre] *= np.sin(np.linspace(0, np.pi / 2, 2 * pre))[:, None]
        elif piece.src_start > 0:
            fade = min(len(chunk), round(HEAD_FADE_S * rate))
            chunk[:fade] *= np.linspace(0, 1, fade)[:, None]
        if post:
            chunk[-2 * post :] *= np.cos(np.linspace(0, np.pi / 2, 2 * post))[:, None]
        _add(bed, chunk, round(piece.out_start * rate) - pre)
    if alignment.echo_at_s is not None:
        _echo(bed, y, pieces[-1].src_end, alignment.echo_at_s, alignment.beat_s, rate)
    tail = min(total, round(CROSSFADE_S * rate))
    bed[total - tail :] *= np.linspace(1, 0, tail)[:, None]
    out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out), np.clip(bed, -1, 1).astype(np.float32), rate, subtype="PCM_16")
    return out


def _echo(bed: np.ndarray, y: np.ndarray, src: float, at: float, beat: float, rate: int) -> None:
    """The bed's last beat repeating every beat, halving each time, faded out over the last."""
    last = _slice(y, round((src - beat) * rate), round(src * rate))
    start = round(at * rate)
    gain = ECHO_DECAY
    t = start
    while t < len(bed) and gain > 1e-3:
        _add(bed, gain * last, t)
        gain *= ECHO_DECAY
        t += len(last)
    fade = min(len(bed) - start, len(last))
    if fade > 0:
        bed[len(bed) - fade :] *= np.linspace(1, 0, fade)[:, None]


def _slice(y: np.ndarray, a: int, b: int) -> np.ndarray:
    """Samples [a, b) of `y`, zero outside it."""
    chunk = np.zeros((b - a, y.shape[1]))
    lo, hi = max(a, 0), min(b, len(y))
    if hi > lo:
        chunk[lo - a : hi - a] = y[lo:hi]
    return chunk


def _add(bed: np.ndarray, chunk: np.ndarray, at: int) -> None:
    lo, hi = max(at, 0), min(at + len(chunk), len(bed))
    if hi > lo:
        bed[lo:hi] += chunk[lo - at : hi - at]
