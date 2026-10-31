"""Retake clusters: utterances, within and across A-roll clips, that say the same thing."""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from rapidfuzz import fuzz

from motion_studio.analysis.models import ClipAnalysis, RetakeCluster, Retakes, Utterance
from motion_studio.text import normalise_token

DEFAULT_THRESHOLD = 0.75

# token_set_ratio scores any subset as identical, so "Yes." would match every line holding "yes".
MIN_WORDS = 3


@dataclass(frozen=True)
class _Candidate:
    utterance: Utterance
    clip_index: int
    tokens: str
    fillers: int

    def preference(self) -> tuple[bool, int, float, int]:
        """Larger is better: complete, then newest (later clip, then later in it), then cleaner."""
        return (self.utterance.complete, self.clip_index, self.utterance.start, -self.fillers)

    def position(self) -> tuple[int, float]:
        return (self.clip_index, self.utterance.start)


def find_retakes(clips: Sequence[ClipAnalysis], threshold: float = DEFAULT_THRESHOLD) -> Retakes:
    """Cluster similar A-roll utterances (union-find) and pick each cluster's winner."""
    candidates = _candidates(clips)
    parent = list(range(len(candidates)))

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, a in enumerate(candidates):
        for j in range(i + 1, len(candidates)):
            if _similarity(a, candidates[j]) >= threshold:
                parent[root(j)] = root(i)

    groups: dict[int, list[_Candidate]] = {}
    for i, candidate in enumerate(candidates):
        groups.setdefault(root(i), []).append(candidate)

    ranked = [
        sorted(group, key=_Candidate.preference, reverse=True)
        for group in groups.values()
        if len(group) > 1
    ]
    ranked.sort(key=lambda group: group[0].position())
    return Retakes(
        threshold=threshold,
        clusters=[
            RetakeCluster(
                id=f"R{n}",
                winner=group[0].utterance.id,
                members=[c.utterance.id for c in group],
                similarity={c.utterance.id: _similarity(group[0], c) for c in group[1:]},
            )
            for n, group in enumerate(ranked, start=1)
        ],
    )


def _candidates(clips: Sequence[ClipAnalysis]) -> list[_Candidate]:
    candidates: list[_Candidate] = []
    for position, analysis in enumerate(clips):
        if analysis.clip.role != "aroll":
            continue
        clip_index = _clip_index(analysis.clip.id, position)
        by_utt: dict[str, list[str]] = {}
        fillers: dict[str, int] = {}
        for word in analysis.words:
            if word.filler is None:
                by_utt.setdefault(word.utt, []).append(normalise_token(word.text))
            else:
                fillers[word.utt] = fillers.get(word.utt, 0) + 1
        for utterance in analysis.utterances:
            tokens = by_utt.get(utterance.id, [])
            if len(tokens) >= MIN_WORDS:
                candidates.append(
                    _Candidate(
                        utterance, clip_index, " ".join(tokens), fillers.get(utterance.id, 0)
                    )
                )
    return candidates


def _clip_index(clip_id: str, fallback: int) -> int:
    digits = re.search(r"\d+", clip_id)
    return int(digits.group()) if digits else fallback


def _similarity(a: _Candidate, b: _Candidate) -> float:
    return round(fuzz.token_set_ratio(a.tokens, b.tokens) / 100, 2)
