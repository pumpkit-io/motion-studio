"""The resolver (guide §6.5): analysis + EDL + config in, frame-accurate timeline out."""

import pytest
from edl_fixtures import clip, edl, timed

from reelcut.config import Config
from reelcut.edl import EdlError, Timeline, resolve

FILLERS = clip("c1", "We um really like it.")  # um: hard filler; like: soft filler


def src_frames(timeline: Timeline) -> list[tuple[int, int]]:
    return [(round(r.src_in_s * 30), round(r.src_out_s * 30)) for r in timeline.runs]


def kept_ids(timeline: Timeline) -> list[str]:
    return [w.id for w in timeline.words]


def test_a_segment_becomes_one_padded_run_snapped_to_frames() -> None:
    c1 = clip("c1", "Hello there world.", "Second line here.")

    timeline = resolve([c1], edl(("hook", "c1.s0", "c1.s0")), Config()).timeline

    # Words span 0.5-1.6 s; pads 80/120 ms give 0.42-1.72 s, which snaps to frames 13-52.
    [run] = timeline.runs
    assert (run.segment, run.clip) == ("hook", "c1")
    assert (run.src_in_s, run.src_out_s) == (pytest.approx(13 / 30), pytest.approx(52 / 30))
    assert (run.out_in, run.out_out) == (0, 39)
    assert timeline.duration_frames == 39
    assert [(w.id, w.text, w.start_ms, w.end_ms) for w in timeline.words] == [
        ("c1.w0", "Hello", 67, 367),
        ("c1.w1", "there", 467, 767),
        ("c1.w2", "world.", 867, 1167),
    ]


def test_hard_fillers_are_cut_and_each_side_stops_at_the_midpoint_to_them() -> None:
    result = resolve([FILLERS], edl(("a", "c1.s0", "c1.s0")), Config())

    # "We" ends 0.80 and "um" starts 0.90: the run ends at the midpoint 0.85, so frame 25.
    assert src_frames(result.timeline) == [(13, 25), (38, 76)]
    assert kept_ids(result.timeline) == ["c1.w0", "c1.w2", "c1.w3", "c1.w4"]
    assert result.stats.hard_fillers_removed == 1


def test_the_policy_can_keep_fillers_or_also_drop_soft_ones() -> None:
    keep_all = edl(("a", "c1.s0", "c1.s0"), policy={"drop_fillers": "none"})
    drop_soft = edl(("a", "c1.s0", "c1.s0"), policy={"drop_fillers": "hard+soft"})

    assert len(kept_ids(resolve([FILLERS], keep_all, Config()).timeline)) == 5
    assert "c1.w3" not in kept_ids(resolve([FILLERS], drop_soft, Config()).timeline)


def test_keep_words_overrides_filler_dropping() -> None:
    keep = edl(("a", "c1.s0", "c1.s0"), keep_words=["c1.w1"])

    assert src_frames(resolve([FILLERS], keep, Config()).timeline) == [(13, 76)]


def test_drop_words_splits_a_segment_around_the_word() -> None:
    c1 = clip("c1", "Hello there big world.")

    timeline = resolve([c1], edl(("a", "c1.s0", "c1.s0"), drop_words=["c1.w2"]), Config()).timeline

    assert kept_ids(timeline) == ["c1.w0", "c1.w1", "c1.w3"]
    assert len(timeline.runs) == 2


def test_a_drop_range_between_words_is_cut_out_exactly() -> None:
    c1 = clip("c1", "Hello there world.")
    cut = edl(("a", "c1.s0", "c1.s0"), drop_ranges=[{"clip": "c1", "start": 1.22, "end": 1.28}])

    timeline = resolve([c1], cut, Config()).timeline

    # Words: 0.5-0.8, 0.9-1.2, 1.3-1.6. The runs stop at 1.2 and resume at 1.3 (frames 36, 39).
    assert src_frames(timeline) == [(13, 36), (39, 52)]
    assert kept_ids(timeline) == ["c1.w0", "c1.w1", "c1.w2"]


def test_a_word_whose_middle_is_inside_a_drop_range_is_removed() -> None:
    c1 = clip("c1", "Hello there world.")
    cut = edl(("a", "c1.s0", "c1.s0"), drop_ranges=[{"clip": "c1", "start": 0.85, "end": 1.25}])

    assert kept_ids(resolve([c1], cut, Config()).timeline) == ["c1.w0", "c1.w2"]


def test_a_long_pause_is_cut_down_to_max_pause_split_evenly_around_the_cut() -> None:
    c1 = clip("c1", "Hello there world.", "Second line here.")

    result = resolve([c1], edl(("a", "c1.s0", "c1.s1")), Config())

    # 1.1 s between "world." and "Second" becomes 175 ms each side, then snaps to frames.
    words = result.timeline.words
    assert words[3].start_ms - words[2].end_ms == 333
    assert src_frames(result.timeline)[0][1] == 53
    assert result.stats.pauses_tightened == 1


def test_runs_less_than_150_ms_apart_are_merged() -> None:
    c1 = timed("c1", ("One", 0.5, 0.8), ("two", 1.25, 1.55), ("three", 2.6, 2.9))

    timeline = resolve([c1], edl(("a", "c1.w0", "c1.w2")), Config()).timeline

    # The 450 ms pause leaves a 100 ms gap after tightening, so it stays; the 1.05 s one is cut.
    assert len(timeline.runs) == 2
    assert kept_ids(timeline) == ["c1.w0", "c1.w1", "c1.w2"]


def test_a_short_run_is_dropped_with_a_warning() -> None:
    c1 = clip("c1", "Hi.", "Second line here.")
    short = edl(("hook", "c1.s0", "c1.s0"), ("body", "c1.s1", "c1.s1"), policy={"pad_out_ms": 0})

    result = resolve([c1], short, Config())

    assert [r.segment for r in result.timeline.runs] == ["body"]
    assert [(w.code, w.message) for w in result.warnings] == [
        ("short_run", "segment hook: run c1.w0 to c1.w0 ('Hi.') is 0.37 s, under 0.40 s: dropped"),
        ("empty_segment", "segment hook keeps no words"),
    ]
    assert result.warnings[0].hint == "extend hook, or lower policy.min_segment_ms"


def test_drop_and_keep_words_take_word_ids() -> None:
    bad = edl(("a", "c1.s0", "c1.s0"), drop_words=["c1.s0"], keep_words=["c1.w40"])

    with pytest.raises(EdlError) as raised:
        resolve([FILLERS], bad, Config())

    assert [p.message for p in raised.value.problems] == [
        "drop_words: c1.s0 is an utterance; list its words, or leave it out of the segments",
        "keep_words: c1.w40 does not exist; c1 has w0-w4",
    ]


def test_a_drop_range_must_name_a_clip_and_end_after_it_starts() -> None:
    ranges = [{"clip": "c7", "start": 1.0, "end": 2.0}, {"clip": "c1", "start": 2.0, "end": 1.0}]

    with pytest.raises(EdlError) as raised:
        resolve([FILLERS], edl(("a", "c1.s0", "c1.s0"), drop_ranges=ranges), Config())

    assert [p.code for p in raised.value.problems] == ["unknown_ref", "bad_drop_range"]


def test_a_word_in_both_drop_and_keep_words_is_dropped_with_a_warning() -> None:
    both = edl(("a", "c1.s0", "c1.s0"), drop_words=["c1.w1"], keep_words=["c1.w1"])

    result = resolve([FILLERS], both, Config())

    assert "c1.w1" not in kept_ids(result.timeline)
    assert [w.code for w in result.warnings] == ["drop_and_keep"]
