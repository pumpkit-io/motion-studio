"""From a clip's words and voice activity to fillers, utterances, pauses and unaligned voice."""

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise

from reelcut.analysis.models import (
    ClipAnalysis,
    ClipInfo,
    FillerKind,
    LanguageGuess,
    Pause,
    Span,
    TranscribedWord,
    Utterance,
    Word,
)
from reelcut.lang import Language
from reelcut.text import ends_sentence, normalise_token, normalise_words, trails_off


@dataclass(frozen=True)
class AnalysisParams:
    utterance_gap_ms: int = 500
    """A silence this long between words ends an utterance, and counts as a long pause."""
    min_pause_ms: int = 300
    """Shorter silences between words are not recorded as pauses."""
    filler_min_ms: int = 80
    """A lexicon match shorter than this is not tagged: the filler prompt over-produces them."""
    unaligned_min_ms: int = 150


def analyse_transcript(
    clip: ClipInfo,
    words: Sequence[TranscribedWord],
    vad: Sequence[Span],
    language: Language,
    *,
    confidence: float = 1.0,
    params: AnalysisParams | None = None,
) -> ClipAnalysis:
    """Analyse one clip's transcript. Shots, static stretches and faces are left empty."""
    p = params or AnalysisParams()
    spoken = sorted((w for w in words if normalise_token(w.text)), key=lambda w: w.start)
    groups = _split_utterances(spoken, p.utterance_gap_ms / 1000)

    out_words: list[Word] = []
    utterances: list[Utterance] = []
    for index, group in enumerate(groups):
        utt_id = f"{clip.id}.s{index}"
        tags = _tag_fillers(group, vad, language, p.filler_min_ms / 1000)
        first_index = len(out_words)
        for word, tag in zip(group, tags, strict=True):
            out_words.append(
                Word(
                    id=f"{clip.id}.w{len(out_words)}",
                    text=word.text.strip(),
                    start=_r(word.start),
                    end=_r(word.end),
                    conf=word.conf,
                    filler=tag,
                    utt=utt_id,
                )
            )
        next_start = groups[index + 1][0].start if index + 1 < len(groups) else None
        utterances.append(
            Utterance(
                id=utt_id,
                start=_r(group[0].start),
                end=_r(group[-1].end),
                first_word=out_words[first_index].id,
                last_word=out_words[-1].id,
                text=" ".join(w.text.strip() for w in group),
                complete=_is_complete(group[-1], next_start, language, p.utterance_gap_ms / 1000),
            )
        )

    return ClipAnalysis(
        clip=clip,
        language=LanguageGuess(code=language.code, confidence=confidence),
        words=out_words,
        utterances=utterances,
        pauses=_pauses(out_words, clip.duration_s, p.min_pause_ms / 1000),
        unaligned_voice=_unaligned(vad, out_words, p.unaligned_min_ms / 1000),
        vad=[Span(start=_r(v.start), end=_r(v.end)) for v in vad],
    )


def _r(seconds: float) -> float:
    return round(seconds, 3)


def _split_utterances(
    words: Sequence[TranscribedWord], gap_s: float
) -> list[list[TranscribedWord]]:
    groups: list[list[TranscribedWord]] = []
    current: list[TranscribedWord] = []
    for i, word in enumerate(words):
        current.append(word)
        last = i + 1 == len(words)
        if (
            last
            or words[i + 1].start - word.end >= gap_s
            or ends_sentence(word.text)
            or trails_off(word.text)
        ):
            groups.append(current)
            current = []
    return groups


def _is_complete(
    last: TranscribedWord, next_start: float | None, language: Language, gap_s: float
) -> bool:
    # Whisper often puts a full stop after an abandoned "is", so a dangling last word counts too.
    stops_short = (
        not ends_sentence(last.text)
        or normalise_token(last.text) in language.utterances.incomplete_endings
    )
    long_pause_follows = next_start is None or next_start - last.end >= gap_s
    return not (stops_short and long_pause_follows)


def _tag_fillers(
    utterance: Sequence[TranscribedWord],
    vad: Sequence[Span],
    language: Language,
    min_s: float,
) -> list[FillerKind | None]:
    lexicon = language.fillers
    anywhere = [(normalise_words(p), "hard") for p in lexicon.hard] + [
        (normalise_words(p), "soft") for p in lexicon.soft
    ]
    at_start = [(normalise_words(p), "soft") for p in lexicon.soft_at_start]
    tokens = [normalise_token(w.text) for w in utterance]
    tags: list[FillerKind | None] = [None] * len(utterance)

    # The start of an utterance stays open across leading fillers: "Ehm, allora, ..." tags both.
    at_utterance_start = True
    i = 0
    while i < len(tokens):
        candidates = anywhere + at_start if at_utterance_start else anywhere
        match = _longest_match(tokens, i, candidates)
        if match is not None:
            length, kind = match
            first, last = utterance[i], utterance[i + length - 1]
            if last.end - first.start >= min_s and _overlaps_any(first.start, last.end, vad):
                for j in range(i, i + length):
                    tags[j] = kind
                i += length
                continue
        at_utterance_start = False
        i += 1
    return tags


def _longest_match(
    tokens: Sequence[str], i: int, candidates: Sequence[tuple[list[str], str]]
) -> tuple[int, FillerKind] | None:
    best: tuple[int, FillerKind] | None = None
    for phrase, kind in candidates:
        n = len(phrase)
        if tokens[i : i + n] == phrase and (best is None or n > best[0]):
            best = (n, "hard" if kind == "hard" else "soft")
    return best


def _overlaps_any(start: float, end: float, spans: Sequence[Span]) -> bool:
    return any(s.start < end and start < s.end for s in spans)


def _pauses(words: Sequence[Word], duration_s: float, min_s: float) -> list[Pause]:
    edges: list[tuple[float, float, str | None]] = []
    if not words:
        edges.append((0.0, duration_s, None))
    else:
        edges.append((0.0, words[0].start, None))
        edges.extend((a.end, b.start, a.id) for a, b in pairwise(words))
        edges.append((words[-1].end, duration_s, words[-1].id))
    return [
        Pause(start=_r(start), end=_r(end), dur=_r(end - start), after_word=after)
        for start, end, after in edges
        if end - start >= min_s
    ]


def _unaligned(vad: Sequence[Span], words: Sequence[Word], min_s: float) -> list[Span]:
    return [
        Span(start=_r(v.start), end=_r(v.end))
        for v in vad
        if v.end - v.start >= min_s and not any(w.start < v.end and v.start < w.end for w in words)
    ]
