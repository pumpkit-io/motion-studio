"""Fitting VAD probabilities and Whisper words to speech regions, without any model."""

from motion_studio.analysis.models import Span, TranscribedWord
from motion_studio.asr.speech import align_to_speech, uncovered, windows
from motion_studio.asr.vad import VadParams, speech_spans

WINDOW_S = 512 / 16_000  # one Silero window: 32 ms


def probs(*runs: tuple[float, float]) -> list[float]:
    """Per-window probabilities from (seconds, probability) runs."""
    out: list[float] = []
    for seconds, prob in runs:
        out += [prob] * round(seconds / WINDOW_S)
    return out


def samples(values: list[float]) -> int:
    return len(values) * 512


def word(text: str, start: float, end: float) -> TranscribedWord:
    return TranscribedWord(text=text, start=start, end=end)


def test_speech_between_silences_becomes_one_padded_region() -> None:
    p = probs((0.512, 0.0), (1.024, 0.9), (0.512, 0.0))
    assert speech_spans(p, samples(p)) == [Span(start=0.482, end=1.566)]


def test_a_silence_shorter_than_the_minimum_does_not_split_speech() -> None:
    p = probs((0.512, 0.0), (0.512, 0.9), (0.064, 0.0), (0.512, 0.9), (0.512, 0.0))
    assert len(speech_spans(p, samples(p))) == 1


def test_a_silence_of_the_minimum_length_splits_speech() -> None:
    p = probs((0.512, 0.0), (0.512, 0.9), (0.192, 0.0), (0.512, 0.9), (0.512, 0.0))
    spans = speech_spans(p, samples(p), VadParams(min_silence_ms=100, speech_pad_ms=0))
    assert spans == [Span(start=0.512, end=1.024), Span(start=1.216, end=1.728)]


def test_speech_shorter_than_the_minimum_is_dropped() -> None:
    p = probs((0.512, 0.0), (0.128, 0.9), (0.512, 0.0))
    assert speech_spans(p, samples(p)) == []


def test_probabilities_between_the_thresholds_keep_speech_going() -> None:
    p = probs((0.512, 0.0), (0.512, 0.9), (0.512, 0.4), (0.512, 0.9), (0.512, 0.0))
    spans = speech_spans(p, samples(p), VadParams(speech_pad_ms=0))
    assert spans == [Span(start=0.512, end=2.048)]


def test_speech_running_to_the_end_closes_at_the_last_sample() -> None:
    p = probs((0.512, 0.0), (0.512, 0.9))
    assert speech_spans(p, samples(p), VadParams(speech_pad_ms=0)) == [Span(start=0.512, end=1.024)]


def test_windows_group_regions_up_to_the_maximum_and_pad_into_the_gaps() -> None:
    regions = [Span(start=1, end=10), Span(start=12, end=20), Span(start=31, end=40)]
    assert windows(regions, 41, max_s=28, pad_s=0.2) == [
        Span(start=0.8, end=20.2),
        Span(start=30.8, end=40.2),
    ]


def test_windows_never_overlap_when_the_gap_is_shorter_than_two_pads() -> None:
    regions = [Span(start=0, end=27.9), Span(start=28.0, end=30)]
    assert windows(regions, 30, max_s=28, pad_s=0.2) == [
        Span(start=0, end=27.95),
        Span(start=27.95, end=30),
    ]


def test_words_in_silence_are_dropped_and_words_across_a_pause_are_clamped() -> None:
    regions = [Span(start=1.0, end=2.0), Span(start=3.0, end=4.0)]
    words = [
        word("Thank", 0.2, 0.5),
        word("is...", 1.6, 2.6),
        word("the", 2.7, 3.3),
    ]
    assert align_to_speech(words, regions) == [word("is...", 1.6, 2.0), word("the", 3.0, 3.3)]


def test_a_word_spanning_two_regions_keeps_the_side_it_overlaps_most() -> None:
    regions = [Span(start=1.0, end=2.0), Span(start=2.5, end=4.0)]
    assert align_to_speech([word("long", 1.8, 3.5)], regions) == [word("long", 2.5, 3.5)]


def test_uncovered_lists_long_regions_without_words() -> None:
    regions = [Span(start=0, end=1), Span(start=2, end=2.3), Span(start=3, end=5)]
    assert uncovered(regions, [word("hi", 0.2, 0.4)], min_s=0.5) == [Span(start=3, end=5)]
