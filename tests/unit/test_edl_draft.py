"""The deterministic draft EDL (guide §8 Phase 6): a baseline the host agent refines."""

import pytest
from edl_fixtures import asset, clip, timed

from reelcut.analysis import ClipAnalysis, Retakes, find_retakes
from reelcut.config import Config
from reelcut.edl import draft, resolve
from reelcut.errors import UserError


def segments(clips: list[ClipAnalysis], retakes: Retakes | None = None) -> list[tuple[str, str]]:
    result = draft(clips, retakes or find_retakes(clips))
    return [(s.from_, s.to) for s in result.segments]


def test_every_aroll_utterance_becomes_a_segment_in_source_order() -> None:
    c1 = clip("c1", "Hello there world.", "Second line here.")
    c2 = clip("c2", "Third clip speaks now.")

    assert segments([c2, c1]) == [
        ("c1.w0", "c1.w2"),
        ("c1.w3", "c1.w5"),
        ("c2.w0", "c2.w3"),
    ]


def test_segment_ids_name_their_utterance_and_are_not_references() -> None:
    c1 = clip("c1", "Hello there world.", "Second line here.")

    result = draft([c1], find_retakes([c1]))

    assert [s.id for s in result.segments] == ["c1-s0", "c1-s1"]
    assert [s.note for s in result.segments] == ["Hello there world.", "Second line here."]


def test_retake_losers_and_abandoned_takes_are_left_out() -> None:
    c1 = clip(
        "c1",
        "Welcome back everyone.",
        "The reason I built",
        "The reason I built this is simple.",
        "See you soon.",
    )
    c2 = clip("c2", "The reason I built this is simple.")

    # c1.s1 is abandoned (no closing punctuation, then a pause); c2.s0 is the newest complete take.
    assert segments([c1, c2]) == [
        ("c1.w0", "c1.w2"),
        ("c1.w14", "c1.w16"),
        ("c2.w0", "c2.w6"),
    ]


def test_an_incomplete_utterance_without_a_complete_retake_stays() -> None:
    c1 = clip("c1", "Welcome back everyone.", "And then we", "Bye now.")

    assert segments([c1]) == [("c1.w0", "c1.w2"), ("c1.w3", "c1.w5"), ("c1.w6", "c1.w7")]


def test_an_utterance_of_only_hard_fillers_is_left_out() -> None:
    c1 = clip("c1", "Hello there world.", "Um.", "Second line here.")

    assert segments([c1]) == [("c1.w0", "c1.w2"), ("c1.w4", "c1.w6")]


def test_assets_are_never_segments() -> None:
    c1 = clip("c1", "Hello there world.")

    assert segments([c1, asset("b1", "broll", 6.0), asset("i1", "image", 5.0)]) == [
        ("c1.w0", "c1.w2")
    ]


def test_the_draft_drops_hard_fillers_by_policy_and_adds_only_jumpcut_punch() -> None:
    c1 = clip("c1", "Hello there world.")

    result = draft([c1], find_retakes([c1]), title="Demo", language="en")

    assert result.policy.drop_fillers == "hard"
    assert result.policy.jumpcut_punch is True
    assert result.events == []
    assert result.rationale == "deterministic draft"
    assert (result.title, result.language) == ("Demo", "en")


@pytest.mark.parametrize(
    ("word_s", "bpm"),
    [
        (0.5, 90),  # 2.0 words/s
        (0.38, 103),  # 2.6 words/s
        (0.3, 118),  # 3.3 words/s
    ],
)
def test_music_is_generated_with_a_bpm_from_the_speech_pace(word_s: float, bpm: int) -> None:
    words = [
        (f"word{i}", round(1 + i * word_s, 3), round(1 + (i + 1) * word_s, 3)) for i in range(9)
    ]
    words[-1] = ("end.", words[-1][1], words[-1][2])
    c1 = timed("c1", *words)

    music = draft([c1], find_retakes([c1])).music

    assert music.mode == "generate"
    assert music.bpm == bpm
    assert music.prompt is not None and "instrumental" in music.prompt
    assert music.seed is not None


def test_fillers_do_not_count_towards_the_pace() -> None:
    # Nine 0.3 s words in 2.7 s would be 3.3 words/s; with three hard fillers it is 2.2.
    text = ["um", "one", "um", "two", "um", "three", "four", "five", "six."]
    words = [(t, round(1 + i * 0.3, 3), round(1.3 + i * 0.3, 3)) for i, t in enumerate(text)]
    c1 = timed("c1", *words)

    assert draft([c1], find_retakes([c1])).music.bpm == 90


def test_the_draft_is_deterministic_and_resolves_cleanly() -> None:
    c1 = clip("c1", "Welcome back um everyone.", "The reason I", "The reason I built it.")
    c2 = clip("c2", "And that is all.")

    first = draft([c1, c2], find_retakes([c1, c2]))
    again = draft([c1, c2], find_retakes([c1, c2]))

    assert first == again
    result = resolve([c1, c2], first, Config())
    assert result.stats.hard_fillers_removed == 1
    assert not [w for w in result.warnings if w.code != "short_run"]


def test_a_project_without_aroll_speech_cannot_be_drafted() -> None:
    with pytest.raises(UserError, match="no A-roll speech"):
        draft([asset("b1", "broll", 6.0)], Retakes(threshold=0.75, clusters=[]))
