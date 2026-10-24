"""Steps 1-5 of guide §6.5: from a segment's words to frame-snapped runs of source time."""

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from typing import Literal

from reelcut.analysis import ClipAnalysis, Word
from reelcut.config import Edit
from reelcut.edl.issues import Problems
from reelcut.edl.models import DropRange
from reelcut.edl.refs import WordSpan

# Pauses that tightening leaves shorter than this are kept whole rather than cut.
MERGE_GAP_S = 0.150

_EPS = 1e-6

Break = Literal["cut", "pause"]


@dataclass
class SourceRun:
    """One run of a segment in source time. `start_f`/`end_f` are frames on the output grid."""

    segment: str
    clip: str
    words: list[Word]
    start_f: int
    end_f: int
    after: Break


@dataclass
class _Draft:
    indices: list[int]
    after: Break
    start: float = 0.0
    end: float = 0.0
    lo: float = 0.0
    hi: float = 0.0


@dataclass
class SegmentCut:
    runs: list[SourceRun]
    pauses_tightened: int


def cut_segment(
    segment: str,
    analysis: ClipAnalysis,
    span: WordSpan,
    removed: Collection[int],
    ranges: Sequence[DropRange],
    policy: Edit,
    fps: int,
    problems: Problems,
) -> SegmentCut:
    """Split the kept words of one segment into padded, merged, snapped runs.

    `removed` holds every word index cut from this segment (drops and fillers); words outside
    the segment are treated the same way at its edges, so a run never reaches into them.
    """
    words = analysis.words
    max_pause = policy.max_pause_ms / 1000
    drafts: list[_Draft] = []
    current: list[int] = []
    after: Break = "cut"
    for i in range(span.first, span.last + 1):
        if i in removed:
            if current:
                drafts.append(_Draft(current, after))
                current = []
            after = "cut"
            continue
        if current:
            prev, word = words[current[-1]], words[i]
            if any(r.start < word.start and r.end > prev.end for r in ranges):
                drafts.append(_Draft(current, after))
                current, after = [], "cut"
            elif word.start - prev.end > max_pause:
                drafts.append(_Draft(current, after))
                current, after = [], "pause"
        current.append(i)
    if current:
        drafts.append(_Draft(current, after))

    for k, draft in enumerate(drafts):
        next_pause = k + 1 < len(drafts) and drafts[k + 1].after == "pause"
        _bound(draft, words, ranges, analysis.clip.duration_s, policy, next_pause)
    drafts = _merge(drafts)

    runs: list[SourceRun] = []
    pauses = 0
    kept_previous = False
    for draft in drafts:
        start_f = round(draft.start * fps)
        if start_f < draft.lo * fps - _EPS:
            start_f += 1
        end_f = round(draft.end * fps)
        if end_f > draft.hi * fps + _EPS:
            end_f -= 1
        kept = [words[i] for i in draft.indices]
        if (end_f - start_f) * 1000 < policy.min_segment_ms * fps:
            _warn_short(problems, segment, kept, (end_f - start_f) / fps, policy)
            kept_previous = False
            continue
        if draft.after == "pause" and kept_previous:
            pauses += 1
        runs.append(SourceRun(segment, analysis.clip.id, kept, start_f, end_f, draft.after))
        kept_previous = True
    return SegmentCut(runs, pauses)


def _bound(
    draft: _Draft,
    words: Sequence[Word],
    ranges: Sequence[DropRange],
    duration: float,
    policy: Edit,
    next_pause: bool,
) -> None:
    """Pad a run, stopping at the midpoint to a neighbouring word and at any drop range."""
    first_i, last_i = draft.indices[0], draft.indices[-1]
    first, last = words[first_i], words[last_i]
    half_pause = policy.max_pause_ms / 2000

    lo = 0.0
    if first_i > 0:
        lo = min((words[first_i - 1].end + first.start) / 2, first.start)
    for r in ranges:
        if r.start < first.start and r.end > lo:
            lo = r.end
    lead = half_pause if draft.after == "pause" else policy.pad_in_ms / 1000
    draft.lo, draft.start = lo, max(first.start - lead, lo)

    hi = duration
    if last_i + 1 < len(words):
        hi = max((last.end + words[last_i + 1].start) / 2, last.end)
    for r in ranges:
        if r.end > last.end and r.start < hi:
            hi = r.start
    tail = half_pause if next_pause else policy.pad_out_ms / 1000
    draft.hi, draft.end = hi, min(last.end + tail, hi)


def _merge(drafts: list[_Draft]) -> list[_Draft]:
    """Merge runs split only by a pause that tightening left shorter than MERGE_GAP_S.

    Runs split by a removed word or a drop range never merge: that would bring the cut back.
    """
    merged: list[_Draft] = []
    for draft in drafts:
        if merged and draft.after == "pause" and draft.start - merged[-1].end < MERGE_GAP_S:
            last = merged[-1]
            last.indices = last.indices + draft.indices
            last.end, last.hi = draft.end, draft.hi
        else:
            merged.append(draft)
    return merged


def _warn_short(
    problems: Problems, segment: str, words: list[Word], length_s: float, policy: Edit
) -> None:
    text = " ".join(w.text for w in words)
    if len(text) > 40:
        text = text[:37] + "..."
    problems.warn(
        "short_run",
        f"segment {segment}: run {words[0].id} to {words[-1].id} ('{text}') is {length_s:.2f} s, "
        f"under {policy.min_segment_ms / 1000:.2f} s: dropped",
        hint=f"extend {segment}, or lower policy.min_segment_ms",
    )
