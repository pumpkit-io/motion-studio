"""Events resolve to output frames (guide §6.5 steps 9-10), with overlap checks and beat snaps."""

from typing import Any

import pytest
from edl_fixtures import asset, clip, edl

from reelcut.config import Config
from reelcut.edl import EdlError, Resolution, resolve

# Output: s0 = frames 0-40, s1 = 40-83, s2 = 83-125. "Second" (c1.w3) starts at 1.5 s, frame 45;
# "here." (c1.w5) ends at 2.6 s, frame 78.
C1 = clip("c1", "Hello there world.", "Second line here.", "Third and last.")
CLIPS = [C1, asset("b1", "broll", 5.0), asset("b2", "broll", 1.0), asset("i1", "image", 0.0)]


def run(*events: dict[str, Any], beats: list[float] | None = None, **extra: Any) -> Resolution:
    return resolve(
        CLIPS, edl(("a", "c1.s0", "c1.s2"), events=list(events), **extra), Config(), beats=beats
    )


def frames(result: Resolution) -> list[tuple[str, int, int]]:
    return [(e.type, e.start, e.end) for e in result.timeline.events]


def errors(*events: dict[str, Any], **extra: Any) -> list[tuple[str, str]]:
    with pytest.raises(EdlError) as raised:
        run(*events, **extra)
    return [(p.code, p.message) for p in raised.value.problems]


def broll(start: str, end: str, **extra: Any) -> dict[str, Any]:
    return {"type": "broll", "asset": "b1", "start": start, "end": end, **extra}


def test_word_anchors_resolve_to_the_words_in_output_time() -> None:
    result = run(broll("c1.w3", "c1.w5", asset_in_s=1.5, mode="pip"))

    [event] = result.timeline.events
    assert event.model_dump() == {
        "type": "broll",
        "asset": "b1",
        "src": "media/b1.mp4",
        "start": 45,
        "end": 78,
        "asset_in_s": 1.5,
        "mode": "pip",
    }


def test_an_utterance_anchor_starts_at_its_first_and_ends_at_its_last_kept_word() -> None:
    assert frames(run(broll("c1.s1", "c1.s1"))) == [("broll", 45, 78)]


def test_a_segment_anchor_spans_the_segment_in_the_output() -> None:
    result = resolve(
        CLIPS,
        edl(
            ("hook", "c1.s2", "c1.s2"),
            ("body", "c1.s0", "c1.s1"),
            events=[{"type": "push", "from": "body", "scale": 1.1}, broll("hook", "hook")],
        ),
        Config(),
    )

    push = result.timeline.events[1]
    assert frames(result) == [("broll", 0, 39), ("push", 39, 121)]
    assert push.model_dump()["scale"] == 1.1


def test_a_zoom_holds_until_its_hold_anchor_or_else_the_end_of_its_own() -> None:
    result = run(
        {"type": "zoom", "at": "c1.w3", "hold_until": "c1.w5", "scale": 1.2, "ease": "smooth"},
        {"type": "zoom", "at": "c1.w6"},
    )

    assert frames(result) == [("zoom", 45, 78), ("zoom", 88, 97)]
    assert result.timeline.events[1].model_dump() == {
        "type": "zoom",
        "start": 88,
        "end": 97,
        "scale": 1.15,
        "ease": "snap",
    }


def test_titles_and_images_resolve_and_events_are_ordered_by_start() -> None:
    result = run(
        {"type": "title", "text": "Three lines", "start": "c1.s2", "end": "c1.s2"},
        {"type": "image", "asset": "i1", "start": "c1.w0", "end": "c1.w2", "motion": "none"},
    )

    assert frames(result) == [("image", 2, 35), ("title", 88, 121)]
    assert result.timeline.events[0].model_dump()["src"] == "media/i1.mp4"


def test_emphasis_marks_its_words() -> None:
    result = run({"type": "emphasis", "words": ["c1.w1", "c1.w4"]})

    assert [w.id for w in result.timeline.words if w.emphasis] == ["c1.w1", "c1.w4"]
    assert result.timeline.events == []


def test_an_anchor_on_a_dropped_word_suggests_the_nearest_kept_word() -> None:
    found = errors({"type": "zoom", "at": "c1.w4"}, drop_words=["c1.w4", "c1.w5"])

    assert found == [
        (
            "dropped_anchor",
            "event 1 (zoom): at c1.w4 is cut from the edit; nearest kept word: c1.w3",
        )
    ]


def test_an_utterance_with_no_kept_word_suggests_the_nearest_kept_word() -> None:
    found = errors(broll("c1.s1", "c1.w8"), drop_words=["c1.w3", "c1.w4", "c1.w5"])

    assert found == [
        (
            "dropped_anchor",
            "event 1 (broll): start c1.s1 has no word in the edit; nearest kept word: c1.w2",
        )
    ]


def test_an_anchor_outside_every_segment_is_cut_from_the_edit() -> None:
    with pytest.raises(EdlError) as raised:
        resolve(CLIPS, edl(("a", "c1.s1", "c1.s1"), events=[broll("c1.w0", "c1.w4")]), Config())

    [problem] = raised.value.problems
    assert problem.message.endswith("start c1.w0 is cut from the edit; nearest kept word: c1.w3")
    assert problem.hint == "anchor to c1.w3"


def test_broken_anchors_are_reported() -> None:
    found = errors(
        {"type": "zoom", "at": "intro"},
        {"type": "zoom", "at": "c1.s9"},
        {"type": "push", "from": "c1.w3"},
        {"type": "emphasis", "words": ["c1.s1"]},
    )

    assert found == [
        ("bad_ref", "event 1 (zoom): at 'intro' is not a segment, word or utterance ID"),
        ("unknown_ref", "event 2 (zoom): c1.s9 does not exist; c1 has s0-s2"),
        ("bad_ref", "event 3 (push): from must be a segment ID, not c1.w3"),
        ("bad_ref", "event 4 (emphasis): c1.s1 is an utterance; list its words"),
    ]


def test_an_empty_segment_cannot_anchor_an_event() -> None:
    with pytest.raises(EdlError) as raised:
        resolve(
            CLIPS,
            edl(
                ("a", "c1.s0", "c1.s1"),
                ("b", "c1.w6", "c1.w6"),
                drop_words=["c1.w6"],
                events=[{"type": "push", "from": "b"}],
            ),
            Config(),
        )

    assert [(p.code, p.message) for p in raised.value.problems] == [
        ("dropped_anchor", "event 1 (push): from b keeps no words")
    ]


def test_an_event_cannot_end_before_it_starts() -> None:
    assert errors(broll("c1.w5", "c1.w3")) == [
        ("event_range", "event 1 (broll): end c1.w3 comes before start c1.w5")
    ]


def test_assets_must_exist_with_the_right_role_and_cover_asset_in() -> None:
    found = errors(
        {"type": "broll", "asset": "i1", "start": "c1.w0", "end": "c1.w1"},
        {"type": "image", "asset": "b9", "start": "c1.w0", "end": "c1.w1"},
        broll("c1.w3", "c1.w4", asset_in_s=5.0),
    )

    assert found == [
        ("bad_asset", "event 1 (broll): i1 is not a B-roll clip; B-roll: b1, b2"),
        ("bad_asset", "event 2 (image): b9 is not an image; images: i1"),
        ("bad_asset", "event 3 (broll): asset_in_s 5.00 is past the end of b1 (5.00 s)"),
    ]


def test_b_roll_shorter_than_its_span_ends_early_with_a_warning() -> None:
    result = run({"type": "broll", "asset": "b2", "start": "c1.w3", "end": "c1.w5"})

    assert frames(result) == [("broll", 45, 75)]
    assert [(w.code, w.message) for w in result.warnings] == [
        (
            "asset_short",
            "event 1 (broll): b2 has 1.00 s from asset_in_s, shown for 1.10 s: cut short",
        )
    ]


def test_full_frame_overlays_cannot_overlap() -> None:
    found = errors(
        broll("c1.w3", "c1.w5"),
        {"type": "image", "asset": "i1", "start": "c1.w5", "end": "c1.w7"},
        broll("c1.w4", "c1.w6", mode="pip"),
    )

    assert found == [
        ("overlay_overlap", "events 1 (broll b1) and 2 (image i1) overlap by 0.30 s"),
    ]


def test_a_title_over_b_roll_is_a_warning() -> None:
    result = run(
        broll("c1.w3", "c1.w5"),
        {"type": "title", "text": "Hi", "start": "c1.w5", "end": "c1.w7"},
    )

    assert [(w.code, w.message) for w in result.warnings] == [
        ("title_over_broll", "event 2 (title) overlaps event 1 (broll b1) by 0.30 s")
    ]


def test_b_roll_and_image_starts_snap_to_a_beat_within_80_ms() -> None:
    result = run(
        broll("c1.w3", "c1.w5"),
        {"type": "image", "asset": "i1", "start": "c1.w6", "end": "c1.w7"},
        {"type": "title", "text": "Hi", "start": "c1.w3", "end": "c1.w4"},
        beats=[1.43, 3.02],
    )
    unsnapped = run(broll("c1.w3", "c1.w5"), beats=[1.6])

    # 1.43 s is 70 ms before "Second" (1.5 s); 3.02 s is 87 ms after "Third" (2.933 s).
    assert frames(result) == [("broll", 43, 78), ("title", 45, 66), ("image", 88, 109)]
    assert frames(unsnapped) == [("broll", 45, 78)]


def test_beats_never_move_speech_cuts() -> None:
    plain = run(broll("c1.w3", "c1.w5"))
    snapped = run(broll("c1.w3", "c1.w5"), beats=[0.03, 1.43, 1.4, 2.79])

    assert snapped.timeline.runs == plain.timeline.runs
    assert snapped.timeline.words == plain.timeline.words


def test_emphasis_words_must_exist_and_be_kept() -> None:
    found = errors({"type": "emphasis", "words": ["c1.w99", "c1.w4"]}, drop_words=["c1.w4"])

    assert found == [
        ("unknown_ref", "event 1 (emphasis): c1.w99 does not exist; c1 has w0-w8"),
        (
            "dropped_anchor",
            "event 1 (emphasis): c1.w4 is cut from the edit; nearest kept word: c1.w3",
        ),
    ]


def test_an_anchor_in_a_clip_with_nothing_kept_says_so() -> None:
    c2 = clip("c2", "Other words here.")

    with pytest.raises(EdlError) as raised:
        resolve(
            [*CLIPS, c2], edl(("a", "c1.s0", "c1.s0"), events=[broll("c2.w0", "c2.w1")]), Config()
        )

    assert raised.value.problems[0].message == (
        "event 1 (broll): start c2.w0 is cut from the edit; no word of c2 is kept"
    )
