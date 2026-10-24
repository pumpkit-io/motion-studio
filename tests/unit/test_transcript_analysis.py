"""Transcript analysers, driven through `analyse_transcript` with constructed transcripts."""

from reelcut.analysis import ClipAnalysis, ClipInfo, Span, TranscribedWord, analyse_transcript
from reelcut.lang import load_language

WORD_S = 0.25
GAP_S = 0.05


def transcript(script: str, start: float = 0.5) -> list[TranscribedWord]:
    """Words of 250 ms with 50 ms gaps; a token like `|1.2|` inserts that much silence."""
    words: list[TranscribedWord] = []
    t = start
    for token in script.split():
        if token.startswith("|") and token.endswith("|"):
            t += float(token.strip("|")) - GAP_S
            continue
        words.append(TranscribedWord(text=token, start=round(t, 3), end=round(t + WORD_S, 3)))
        t += WORD_S + GAP_S
    return words


def analyse(
    script: str,
    lang: str = "en",
    vad: list[Span] | None = None,
    duration_s: float | None = None,
    words: list[TranscribedWord] | None = None,
) -> ClipAnalysis:
    words = words if words is not None else transcript(script)
    end = words[-1].end if words else 0.0
    clip = ClipInfo(
        id="c1",
        role="aroll",
        source="raw/take.mov",
        duration_s=duration_s if duration_s is not None else end + 0.5,
    )
    if vad is None:
        vad = [Span(start=0.0, end=end + 0.1)]
    return analyse_transcript(clip, words, vad, load_language(lang))


def fillers(analysis: ClipAnalysis) -> list[tuple[str, str | None]]:
    return [(w.text, w.filler) for w in analysis.words if w.filler]


def test_english_hard_fillers_are_tagged_case_insensitively_without_punctuation() -> None:
    result = analyse("Today, Um, I want to show you, uh, how I edit.")

    assert fillers(result) == [("Um,", "hard"), ("uh,", "hard")]


def test_english_multi_word_soft_fillers_are_tagged_on_every_word() -> None:
    result = analyse("It was, you know, basically done. I mean it.")

    assert fillers(result) == [
        ("you", "soft"),
        ("know,", "soft"),
        ("basically", "soft"),
        ("I", "soft"),
        ("mean", "soft"),
    ]


def test_english_start_only_soft_fillers_count_only_at_utterance_start() -> None:
    result = analyse("So, um, okay we start. We do it so well, okay?")

    assert fillers(result) == [("So,", "soft"), ("um,", "hard"), ("okay", "soft")]


def test_italian_hard_and_soft_fillers_are_tagged() -> None:
    result = analyse("Allora, ehm, oggi vi faccio vedere, tipo, il mio lavoro. Ehm comunque!", "it")

    assert fillers(result) == [
        ("Allora,", "soft"),
        ("ehm,", "hard"),
        ("tipo,", "soft"),
        ("Ehm", "hard"),
        ("comunque!", "soft"),
    ]


def test_italian_start_only_soft_fillers_are_left_alone_mid_utterance() -> None:
    result = analyse("Ci vediamo allora, comunque è ok.", "it")

    assert fillers(result) == []


def test_a_filler_must_overlap_voice_activity_and_last_80_ms() -> None:
    words = [
        TranscribedWord(text="Today", start=0.5, end=0.8),
        TranscribedWord(text="um", start=0.85, end=1.2),  # outside every VAD region
        TranscribedWord(text="uh", start=1.25, end=1.3),  # only 50 ms long
        TranscribedWord(text="um", start=1.35, end=1.5),
        TranscribedWord(text="done.", start=1.55, end=1.9),
    ]
    vad = [Span(start=0.4, end=0.82), Span(start=1.22, end=2.0)]

    result = analyse("", words=words, vad=vad)

    assert [(w.text, w.filler) for w in result.words] == [
        ("Today", None),
        ("um", None),
        ("uh", None),
        ("um", "hard"),
        ("done.", None),
    ]


def test_utterances_split_at_long_pauses_and_sentence_ends() -> None:
    result = analyse("Hi there. Welcome back |0.6| to the show |0.4| today. Bye!")

    assert [u.text for u in result.utterances] == [
        "Hi there.",
        "Welcome back",
        "to the show today.",
        "Bye!",
    ]
    second = result.utterances[1]
    assert (second.id, second.first_word, second.last_word) == ("c1.s1", "c1.w2", "c1.w3")
    assert [w.utt for w in result.words] == ["c1.s0"] * 2 + ["c1.s1"] * 2 + ["c1.s2"] * 4 + [
        "c1.s3"
    ]
    assert [w.id for w in result.words][:3] == ["c1.w0", "c1.w1", "c1.w2"]
    assert (second.start, second.end) == (result.words[2].start, result.words[3].end)


def test_an_utterance_that_stops_mid_sentence_before_a_long_pause_is_incomplete() -> None:
    result = analyse(
        "The most important thing is |1.2| The most important thing is short. "
        "Then a pause, |1.0| and the end."
    )

    assert [(u.text, u.complete) for u in result.utterances] == [
        ("The most important thing is", False),
        ("The most important thing is short.", True),
        ("Then a pause,", False),
        ("and the end.", True),
    ]


def test_a_dangling_word_is_incomplete_even_with_a_full_stop() -> None:
    result = analyse("Il motivo per cui è. |1.0| Il motivo per cui l'ho fatto è semplice.", "it")

    assert [u.complete for u in result.utterances] == [False, True]


def test_trailing_off_and_the_clip_end_mark_incomplete_utterances() -> None:
    result = analyse("Il motivo per cui… |1.0| E poi")

    assert [(u.text, u.complete) for u in result.utterances] == [
        ("Il motivo per cui…", False),
        ("E poi", False),
    ]


def test_a_dangling_word_quickly_continued_stays_complete() -> None:
    result = analyse("This is. |0.3| Fine.")

    assert [u.complete for u in result.utterances] == [True, True]


def test_pauses_cover_the_head_long_gaps_and_the_tail() -> None:
    words = transcript("One two |0.8| three |0.2| four", start=1.0)
    result = analyse("", words=words, duration_s=words[-1].end + 0.6)

    assert [(p.start, p.end, p.dur, p.after_word) for p in result.pauses] == [
        (0.0, 1.0, 1.0, None),
        (1.55, 2.35, 0.8, "c1.w1"),
        (3.05, 3.65, 0.6, "c1.w3"),
    ]


def test_unaligned_voice_is_activity_of_150_ms_or_more_with_no_word() -> None:
    words = transcript("Hello there |2.0| again.", start=1.0)
    vad = [
        Span(start=0.9, end=1.6),
        Span(start=2.0, end=2.4),  # a mumble between the words
        Span(start=2.6, end=2.7),  # too short to report
        Span(start=3.5, end=3.9),
    ]

    result = analyse("", words=words, vad=vad)

    assert [(s.start, s.end) for s in result.unaligned_voice] == [(2.0, 2.4)]
