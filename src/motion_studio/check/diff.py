"""Align the words the timeline promises with the words a re-transcription heard."""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher

from motion_studio.analysis.models import TranscribedWord
from motion_studio.edl.models import TimelineWord

# A missing word this close to a cut (ms, word edge to cut) is a clipped cut, not ASR noise.
CLIP_WINDOW_MS = 300


@dataclass(frozen=True)
class Miss:
    """An expected word the re-transcription lost (`heard` None) or heard as something else."""

    word: TimelineWord
    heard: str | None
    cut: int | None = None
    """1-based index of the cut within CLIP_WINDOW_MS, if any."""


@dataclass(frozen=True)
class WordDiff:
    expected: int
    heard: int
    matched: int
    misses: list[Miss]


def normalise(text: str) -> str:
    return re.sub(r"[\W_]+", "", text.casefold())


def diff_words(
    expected: Sequence[TimelineWord],
    heard: Sequence[TranscribedWord],
    cuts_ms: Sequence[int],
) -> WordDiff:
    want = [normalise(w.text) for w in expected]
    got = [normalise(w.text) for w in heard]
    matcher = SequenceMatcher(None, want, got, autojunk=False)
    misses: list[Miss] = []
    matched = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            matched += i2 - i1
            continue
        if tag == "insert":
            continue
        replacement = " ".join(w.text for w in heard[j1:j2]) if tag == "replace" else None
        for k in range(i1, i2):
            if want[k]:
                misses.append(Miss(expected[k], replacement, _near_cut(expected[k], cuts_ms)))
    return WordDiff(len(expected), len(heard), matched, misses)


def _near_cut(word: TimelineWord, cuts_ms: Sequence[int]) -> int | None:
    best: tuple[int, int] | None = None
    for index, cut in enumerate(cuts_ms, start=1):
        gap = (
            0
            if word.start_ms <= cut <= word.end_ms
            else min(abs(word.start_ms - cut), abs(word.end_ms - cut))
        )
        if gap <= CLIP_WINDOW_MS and (best is None or gap < best[0]):
            best = (gap, index)
    return best[1] if best else None
