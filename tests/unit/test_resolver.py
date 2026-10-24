"""The resolver (guide §6.5): analysis + EDL + config in, frame-accurate timeline out."""

import pytest
from edl_fixtures import clip, edl, timed

from reelcut.analysis import Faces, FaceSample, LanguageGuess
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

    # "We" ends 0.80 and "um" starts 0.90: the run ends at the midpoint 0.85, frame 25.5 -> 26.
    assert src_frames(result.timeline) == [(13, 26), (38, 76)]
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


def scales(timeline: Timeline) -> list[float]:
    return [r.base_scale for r in timeline.runs]


TWO_LINES = clip("c1", "Hello there world.", "Second line here.")
OTHER = clip("c2", "Another clip speaking.")


def test_segments_that_meet_in_a_gap_share_the_boundary_frame() -> None:
    timeline = resolve([TWO_LINES], edl(("a", "c1.w0", "c1.w1"), ("b", "c1.w2", "c1.w2")), Config())

    first, second = timeline.timeline.runs
    assert first.src_out_s == second.src_in_s


def test_jump_cuts_alternate_the_punch_in_scale() -> None:
    three = clip("c1", "Line one here.", "Line two here.", "Line three here.")

    timeline = resolve([three], edl(("a", "c1.s0", "c1.s2")), Config()).timeline

    assert scales(timeline) == [1.0, 1.08, 1.0]


def test_the_punch_scale_and_switch_come_from_the_policy() -> None:
    bigger = edl(("a", "c1.s0", "c1.s1"), policy={"jumpcut_punch_scale": 1.2})
    off = edl(("a", "c1.s0", "c1.s1"), policy={"jumpcut_punch": False})

    assert scales(resolve([TWO_LINES], bigger, Config()).timeline) == [1.0, 1.2]
    assert scales(resolve([TWO_LINES], off, Config()).timeline) == [1.0, 1.0]


def test_a_cut_to_another_clip_or_a_continuous_cut_is_not_a_jump_cut() -> None:
    switch = edl(("a", "c1.s1", "c1.s1"), ("b", "c2.s0", "c2.s0"), ("c", "c1.s0", "c1.s0"))
    continuous = edl(("a", "c1.w0", "c1.w1"), ("b", "c1.w2", "c1.w2"))
    reversed_ = edl(("b", "c1.w2", "c1.w2"), ("a", "c1.w0", "c1.w1"))

    assert scales(resolve([TWO_LINES, OTHER], switch, Config()).timeline) == [1.0, 1.0, 1.0]
    assert scales(resolve([TWO_LINES], continuous, Config()).timeline) == [1.0, 1.0]
    assert scales(resolve([TWO_LINES], reversed_, Config()).timeline) == [1.0, 1.08]


def test_each_run_is_framed_on_the_median_face_inside_it() -> None:
    samples = [(0.5, 0.3, 0.2), (1.0, 0.4, 0.5), (1.5, 0.9, 0.4), (3.0, 0.1, 0.1)]
    faces = Faces(
        samples=[FaceSample(t=t, cx=x, cy=y, w=0.2, h=0.3, score=0.9) for t, x, y in samples]
    )
    c1 = TWO_LINES.model_copy(update={"faces": faces})

    first, second = resolve([c1], edl(("a", "c1.s0", "c1.s1")), Config()).timeline.runs

    assert (first.crop.cx, first.crop.cy, first.face) == (0.4, 0.4, True)
    assert (second.crop.cx, second.crop.cy, second.face) == (0.1, 0.1, True)


def test_a_run_without_a_face_is_framed_on_the_centre() -> None:
    [run] = resolve([TWO_LINES], edl(("a", "c1.s0", "c1.s0")), Config()).timeline.runs

    assert (run.crop.cx, run.crop.cy, run.face) == (0.5, 0.5, False)


def test_language_captions_and_music_come_from_the_edl_over_the_config() -> None:
    plain = resolve([TWO_LINES], edl(("a", "c1.s0", "c1.s0")), Config()).timeline
    styled = resolve(
        [TWO_LINES],
        edl(
            ("a", "c1.s0", "c1.s0"),
            language="it",
            captions={"style": "karaoke"},
            music={"mode": "none"},
            formats=["16x9", "4x5"],
        ),
        Config(),
    ).timeline

    assert (plain.language, plain.captions.style, plain.music_path) == (
        "en",
        "clean",
        "build/music.wav",
    )
    assert plain.captions.max_chars_per_page == 22
    assert "the" in plain.captions.keep_with_next
    assert [(f.name, f.width, f.height) for f in plain.formats] == [("9x16", 1080, 1920)]
    assert (styled.language, styled.captions.style, styled.music_path) == ("it", "karaoke", None)
    assert styled.captions.max_chars_per_page == 20
    assert [(f.name, f.width, f.height) for f in styled.formats] == [
        ("16x9", 1920, 1080),
        ("4x5", 1080, 1350),
    ]


def test_hiding_captions_during_full_b_roll_is_off_unless_configured() -> None:
    one = edl(("a", "c1.s0", "c1.s0"))
    hidden = Config.model_validate({"captions": {"hide_during_broll": True}})
    overridden = edl(("a", "c1.s0", "c1.s0"), captions={"hide_during_broll": False})

    assert resolve([TWO_LINES], one, Config()).timeline.captions.hide_during_broll is False
    assert resolve([TWO_LINES], one, hidden).timeline.captions.hide_during_broll is True
    assert resolve([TWO_LINES], overridden, hidden).timeline.captions.hide_during_broll is False


def test_an_edl_longer_than_its_limit_gets_a_warning() -> None:
    result = resolve([TWO_LINES], edl(("a", "c1.s0", "c1.s1"), max_duration_s=1), Config())

    assert [(w.code, w.message) for w in result.warnings] == [
        ("too_long", "duration 2.7 s is over the 1.0 s limit")
    ]


def test_the_language_comes_from_the_config_unless_it_is_auto() -> None:
    config = Config.model_validate({"defaults": {"language": "it"}})
    silent = TWO_LINES.model_copy(update={"language": None})

    assert resolve([TWO_LINES], edl(("a", "c1.s0", "c1.s0")), config).timeline.language == "it"
    unknown = resolve([silent], edl(("a", "c1.s0", "c1.s0")), Config()).timeline
    assert unknown.language == "en"


def test_the_project_language_is_the_one_with_most_a_roll_speech_time() -> None:
    # c1 has more words in English; c2's two Italian words span far more speech time.
    english = timed("c1", *[(f"w{n}", 0.5 + n * 0.2, 0.6 + n * 0.2) for n in range(6)])
    italian = timed("c2", ("Ciao", 0.5, 4.0), ("tutti.", 4.2, 9.0))
    english = english.model_copy(update={"language": LanguageGuess(code="en", confidence=0.9)})
    italian = italian.model_copy(update={"language": LanguageGuess(code="it", confidence=0.9)})

    result = resolve([english, italian], edl(("a", "c1.s0", "c1.s0")), Config())

    assert result.timeline.language == "it"


def test_an_edl_language_needs_a_language_file() -> None:
    with pytest.raises(EdlError) as raised:
        resolve([TWO_LINES], edl(("a", "c1.s0", "c1.s0"), language="xx"), Config())

    assert raised.value.problems[0].message == "language xx has no data file; available: en, it"


def test_a_short_run_warning_shortens_long_text() -> None:
    c1 = timed("c1", *[(f"word{n}", 0.5 + n * 0.02, 0.51 + n * 0.02) for n in range(8)])

    [warning] = resolve([c1], edl(("a", "c1.w0", "c1.w7")), Config()).warnings[:1]

    assert "('word0 word1 word2 word3 word4 word5 w...')" in warning.message
