"""Retake clusters, built from transcripts analysed through the analysis entry point."""

from reelcut.analysis import (
    ClipAnalysis,
    ClipInfo,
    Retakes,
    Span,
    TranscribedWord,
    analyse_transcript,
    find_retakes,
)
from reelcut.analysis.models import Role
from reelcut.lang import load_language


def clip(clip_id: str, *utterances: str, role: Role = "aroll", lang: str = "en") -> ClipAnalysis:
    """One utterance per argument, each followed by 1.5 s of silence."""
    words: list[TranscribedWord] = []
    t = 0.5
    for utterance in utterances:
        for token in utterance.split():
            words.append(TranscribedWord(text=token, start=round(t, 3), end=round(t + 0.25, 3)))
            t += 0.3
        t += 1.5
    info = ClipInfo(id=clip_id, role=role, source=f"raw/{clip_id}.mov", duration_s=t)
    return analyse_transcript(info, words, [Span(start=0.0, end=t)], load_language(lang))


def summary(retakes: Retakes) -> list[tuple[str, list[str]]]:
    return [(c.winner, c.members) for c in retakes.clusters]


def test_a_complete_take_beats_a_newer_incomplete_one() -> None:
    c1 = clip(
        "c1",
        "Hi, welcome back.",
        "The most important thing to remember is to keep every sentence short.",
        "The most important thing to remember is",
    )

    retakes = find_retakes([c1])

    assert summary(retakes) == [("c1.s1", ["c1.s1", "c1.s2"])]
    assert retakes.clusters[0].id == "R1"
    assert retakes.clusters[0].similarity == {"c1.s2": 1.0}
    assert retakes.threshold == 0.75


def test_among_complete_takes_the_newest_wins_even_with_more_fillers() -> None:
    c1 = clip(
        "c1",
        "Today I want to show you how I edit my videos.",
        "Today, um, I want to, uh, show you how I edit my videos.",
    )

    assert summary(find_retakes([c1])) == [("c1.s1", ["c1.s1", "c1.s0"])]


def test_a_later_clip_is_newer_than_a_later_position_in_an_earlier_clip() -> None:
    c1 = clip("c1", "Filler line here.", "Thanks for watching, see you next time.")
    c2 = clip("c2", "Thanks for watching and see you next time!", "Something else entirely now.")

    assert summary(find_retakes([c2, c1])) == [("c2.s0", ["c2.s0", "c1.s1"])]


def test_fillers_and_punctuation_do_not_count_towards_similarity() -> None:
    c1 = clip("c1", "Ehm, il motivo è semplice.", "Il motivo, ehm, è semplice!", lang="it")

    retakes = find_retakes([c1])

    assert summary(retakes) == [("c1.s1", ["c1.s1", "c1.s0"])]
    assert retakes.clusters[0].similarity == {"c1.s0": 1.0}


def test_clusters_join_transitively_and_unrelated_lines_stay_out() -> None:
    c1 = clip(
        "c1",
        "We built the whole app in two weeks.",
        "The weather is nice today in Rome.",
        "We built the whole app in two weeks flat.",
        "We built the app in two weeks flat, really.",
    )

    assert summary(find_retakes([c1])) == [("c1.s3", ["c1.s3", "c1.s2", "c1.s0"])]


def test_clusters_are_numbered_in_footage_order() -> None:
    c1 = clip(
        "c1",
        "First we record every take.",
        "Then we cut the long pauses out.",
        "First we record every take!",
        "Then we cut the long pauses out!",
    )

    retakes = find_retakes([c1])

    assert [(c.id, c.winner) for c in retakes.clusters] == [("R1", "c1.s2"), ("R2", "c1.s3")]


def test_short_lines_and_non_a_roll_clips_never_cluster() -> None:
    c1 = clip("c1", "Yes.", "Yes, we keep every sentence short.", "Okay then.", "Okay then.")
    b1 = clip("b1", "Yes, we keep every sentence short.", role="broll")

    assert find_retakes([c1, b1]).clusters == []
