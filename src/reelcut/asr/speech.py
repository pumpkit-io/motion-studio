"""Pure helpers that fit Whisper's output to the VAD regions. No model is loaded here."""

from collections.abc import Sequence

from reelcut.analysis.models import Span, TranscribedWord

WINDOW_MAX_S = 28.0
WINDOW_PAD_S = 0.2
RESCUE_MIN_S = 0.5


def windows(
    regions: Sequence[Span],
    duration_s: float,
    *,
    max_s: float = WINDOW_MAX_S,
    pad_s: float = WINDOW_PAD_S,
) -> list[Span]:
    """Group speech regions into windows that each fit one 30 s Whisper pass.

    Whisper can skip the end of a window it decodes in several seeks, so each window is
    transcribed on its own. A region longer than `max_s` becomes a window by itself.
    """
    groups: list[list[Span]] = []
    for region in regions:
        if groups and region.end - groups[-1][0].start <= max_s:
            groups[-1].append(region)
        else:
            groups.append([region])
    out: list[Span] = []
    for index, group in enumerate(groups):
        start = group[0].start - pad_s
        end = group[-1].end + pad_s
        if index > 0:
            start = max(start, (groups[index - 1][-1].end + group[0].start) / 2)
        if index + 1 < len(groups):
            end = min(end, (group[-1].end + groups[index + 1][0].start) / 2)
        out.append(Span(start=round(max(0.0, start), 3), end=round(min(duration_s, end), 3)))
    return out


def align_to_speech(
    words: Sequence[TranscribedWord], regions: Sequence[Span]
) -> list[TranscribedWord]:
    """Drop words outside every speech region and clamp the rest to the region they sit in.

    Whisper hallucinates in silence and stretches words across pauses; the VAD edges are more
    accurate, so a word spanning a gap keeps only its part in the region it overlaps most.
    """
    out: list[TranscribedWord] = []
    for word in sorted(words, key=lambda w: w.start):
        best: Span | None = None
        best_overlap = 0.0
        for region in regions:
            overlap = min(word.end, region.end) - max(word.start, region.start)
            if overlap > best_overlap:
                best, best_overlap = region, overlap
        if best is None:
            continue
        start = max(word.start, best.start)
        end = min(word.end, best.end)
        out.append(word.model_copy(update={"start": round(start, 3), "end": round(end, 3)}))
    return out


def uncovered(
    regions: Sequence[Span], words: Sequence[TranscribedWord], *, min_s: float = RESCUE_MIN_S
) -> list[Span]:
    """Speech regions of at least `min_s` that no word overlaps: candidates for a second pass."""
    return [
        r
        for r in regions
        if r.end - r.start >= min_s and not any(w.start < r.end and r.start < w.end for w in words)
    ]
