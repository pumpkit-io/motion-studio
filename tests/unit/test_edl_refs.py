"""Reference semantics in segments (guide §6.4), observed through the resolver."""

import pytest
from edl_fixtures import asset, clip, edl

from motion_studio.config import Config
from motion_studio.edl import EdlError, resolve

C1 = clip("c1", "Hello there world.", "Second line here.", "Third and last.")
C2 = clip("c2", "Another clip speaking.")
B1 = asset("b1", "broll", 5.0)


def kept(*segments: tuple[str, str, str]) -> list[str]:
    timeline = resolve([C1, C2, B1], edl(*segments), Config()).timeline
    return [w.id for w in timeline.words]


def errors(*segments: tuple[str, str, str]) -> list[tuple[str, str]]:
    with pytest.raises(EdlError) as raised:
        resolve([C1, C2, B1], edl(*segments), Config())
    assert raised.value.exit_code == 1
    return [(p.code, p.message) for p in raised.value.problems]


def test_an_utterance_as_from_means_its_first_word_and_as_to_its_last() -> None:
    assert kept(("a", "c1.s1", "c1.s2")) == ["c1.w3", "c1.w4", "c1.w5", "c1.w6", "c1.w7", "c1.w8"]


def test_word_ids_are_inclusive_at_both_ends() -> None:
    assert kept(("a", "c1.w1", "c1.w4")) == ["c1.w1", "c1.w2", "c1.w3", "c1.w4"]


def test_a_word_and_an_utterance_can_be_mixed() -> None:
    assert kept(("a", "c1.w4", "c1.s2")) == ["c1.w4", "c1.w5", "c1.w6", "c1.w7", "c1.w8"]


def test_segment_order_is_output_order() -> None:
    assert kept(("cta", "c2.s0", "c2.s0"), ("body", "c1.s0", "c1.s0")) == [
        "c2.w0",
        "c2.w1",
        "c2.w2",
        "c1.w0",
        "c1.w1",
        "c1.w2",
    ]


def test_a_missing_utterance_names_the_range_that_exists() -> None:
    assert errors(("a", "c1.s0", "c1.s40")) == [
        ("unknown_ref", "segment a: c1.s40 does not exist; c1 has s0-s2")
    ]


def test_a_missing_word_names_the_range_that_exists() -> None:
    assert errors(("a", "c1.w99", "c1.s2")) == [
        ("unknown_ref", "segment a: c1.w99 does not exist; c1 has w0-w8")
    ]


def test_a_missing_clip_lists_the_a_roll_clips() -> None:
    assert errors(("a", "c9.s0", "c9.s0")) == [
        ("unknown_ref", "segment a: clip c9 does not exist; A-roll clips: c1, c2")
    ]


def test_a_clip_without_words_cannot_be_cut() -> None:
    assert errors(("a", "b1.w0", "c1.w0"))[0] == (
        "unknown_ref",
        "segment a: b1 is broll and has no words; A-roll clips: c1, c2",
    )


def test_a_malformed_reference_says_what_ids_look_like() -> None:
    code, message = errors(("a", "c1.x3", "c1.s0"))[0]
    assert code == "bad_ref"
    assert message == "segment a: 'c1.x3' is not a word ID (c1.w52) or an utterance ID (c1.s4)"


def test_from_and_to_must_be_in_the_same_clip() -> None:
    assert errors(("a", "c1.s0", "c2.s0")) == [
        ("cross_clip", "segment a goes from c1 to c2; from and to must be in the same clip")
    ]


def test_from_must_not_come_after_to() -> None:
    assert errors(("a", "c1.s2", "c1.w1")) == [
        ("reversed_range", "segment a: from c1.s2 (c1.w6) comes after to c1.w1")
    ]


def test_segment_ids_are_unique_and_not_shaped_like_references() -> None:
    found = errors(("a", "c1.s0", "c1.s0"), ("a", "c1.s2", "c1.s2"), ("c1.s1", "c1.s1", "c1.s1"))
    assert found == [
        ("duplicate_segment", "segment id 'a' is used twice"),
        ("bad_segment_id", "segment id 'c1.s1' looks like a word or utterance ID"),
    ]


def test_two_segments_cannot_keep_the_same_word() -> None:
    assert errors(("a", "c1.w0", "c1.w4"), ("b", "c1.w3", "c1.s2")) == [
        ("overlapping_segments", "segments a and b both keep c1.w3 to c1.w4")
    ]


def test_every_broken_reference_is_reported_at_once() -> None:
    found = errors(("a", "c1.s40", "c1.s0"), ("b", "c1.s0", "c2.s0"))
    assert [code for code, _ in found] == ["unknown_ref", "cross_clip"]


def test_an_edl_error_reads_as_its_first_problem() -> None:
    with pytest.raises(EdlError) as raised:
        resolve([C1], edl(("a", "c1.s40", "c1.s0"), ("b", "c1.s50", "c1.s0")), Config())
    assert str(raised.value) == "segment a: c1.s40 does not exist; c1 has s0-s2 (and 1 more)"
