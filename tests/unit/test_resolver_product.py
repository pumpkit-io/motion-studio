"""The resolver on product EDLs (ADR 0004, 0005): scenes on the beat grid, footage by marker."""

from typing import Any

import pytest
from edl_fixtures import product, screen

from motion_studio.config import Config
from motion_studio.edl import EdlError, Issue, resolve
from motion_studio.edl.models import TimelineFootage, TimelineTitleCard

C1 = screen("c1", 20.0, {"start": 1.0, "typed": 4.0, "done": 9.0})


def title(scene_id: str, **extra: Any) -> dict[str, Any]:
    return {"id": scene_id, "type": "title_card", "headline": "Drop your idea.", **extra}


def footage(scene_id: str, start: Any = "c1.m.start", end: Any = "c1.m.done", **extra: Any):
    return {"id": scene_id, "type": "footage", "clip": "c1", "from": start, "to": end, **extra}


def errors(*scenes: dict[str, Any], clips: Any = (C1,), **extra: Any) -> list[Issue]:
    with pytest.raises(EdlError) as caught:
        resolve(list(clips), product(*scenes, **extra), Config())
    return caught.value.problems


def codes(issues: list[Issue]) -> list[str]:
    return [i.code for i in issues]


def test_title_cards_and_footage_sit_back_to_back_on_the_120_bpm_grid() -> None:
    edl = product(
        title("intro", beats=4, step="01", accent=["idea"], subline="Any length."),
        footage("demo", beats=8),
        title("next", bars=1),
    )

    timeline = resolve([C1], edl, Config()).timeline

    # 120 bpm at 30 fps: a beat is 15 frames, a bar of four beats 60.
    assert timeline.kind == "product"
    assert [(s.id, s.start, s.end) for s in timeline.scenes] == [
        ("intro", 0, 60),
        ("demo", 60, 180),
        ("next", 180, 240),
    ]
    assert timeline.duration_frames == 240
    assert timeline.runs == []
    assert [f.name for f in timeline.formats] == ["16x9"]


def test_a_title_card_carries_its_step_subline_and_accent_words() -> None:
    edl = product(title("intro", beats=4, step="01", accent=["idea"], subline="Any length."))

    [card] = resolve([C1], edl, Config()).timeline.scenes

    assert isinstance(card, TimelineTitleCard)
    assert (card.step, card.subline) == ("01", "Any length.")
    assert [(w.text, w.accent) for w in card.headline] == [
        ("Drop", False),
        ("your", False),
        ("idea.", True),
    ]


def test_footage_with_a_length_plays_marker_to_marker_at_the_rate_that_fills_it() -> None:
    [scene] = resolve([C1], product(footage("demo", beats=8)), Config()).timeline.scenes

    # start 1.0 s to done 9.0 s is 8 s of footage in 8 beats (4 s): twice as fast.
    assert isinstance(scene, TimelineFootage)
    assert (scene.clip, scene.src, scene.width, scene.height) == ("c1", "media/c1.mp4", 1600, 900)
    assert (scene.src_in_s, scene.src_out_s, scene.rate) == (1.0, 9.0, 2.0)
    assert scene.device_frame == "browser"


def test_footage_without_a_length_plays_at_its_rate_rounded_to_whole_beats() -> None:
    edl = product(footage("demo", "c1.m.start", "c1.m.typed", rate=2.5))

    [scene] = resolve([C1], edl, Config()).timeline.scenes

    # 3 s at 2.5x is 1.2 s, which rounds to 2 beats (1 s, 30 frames): 3x to fit.
    assert (scene.start, scene.end) == (0, 30)
    assert isinstance(scene, TimelineFootage)
    assert scene.rate == pytest.approx(3.0)


def test_marker_offsets_move_the_in_and_out_points_in_seconds_or_beats() -> None:
    edl = product(
        footage(
            "demo",
            {"marker": "c1.m.start", "offset_s": 0.5},
            {"marker": "c1.m.done", "offset_beats": -2},
            seconds=3,
        )
    )

    [scene] = resolve([C1], edl, Config()).timeline.scenes

    # Two beats at 120 bpm are 1 s.
    assert isinstance(scene, TimelineFootage)
    assert (scene.src_in_s, scene.src_out_s) == (1.5, 8.0)


def test_scene_lengths_follow_the_music_grid_when_there_is_one() -> None:
    beats = [0.0, 0.4, 0.8, 1.2, 1.6, 2.0, 2.4, 2.8, 3.2]  # 150 bpm

    timeline = resolve([C1], product(title("a", beats=2), title("b", bars=1)), Config(), beats)
    timeline = timeline.timeline

    # 0.4 s beats at 30 fps are 12 frames.
    assert [(s.start, s.end) for s in timeline.scenes] == [(0, 24), (24, 72)]


def test_the_grid_continues_past_the_last_beat_of_the_music() -> None:
    timeline = resolve([C1], product(title("a", beats=6)), Config(), [0.0, 0.4, 0.8]).timeline

    assert timeline.duration_frames == 72


def test_a_scene_in_beats_after_one_in_seconds_ends_on_the_nearest_beat() -> None:
    edl = product(title("a", seconds=0.6), title("b", beats=2))

    timeline = resolve([C1], edl, Config()).timeline

    # 0.6 s is beat 1.2; two beats later is 3.2, which ends on beat 3 (1.5 s).
    assert [(s.start, s.end) for s in timeline.scenes] == [(0, 18), (18, 45)]


def test_an_unknown_marker_is_an_error_that_lists_the_clips_markers() -> None:
    [issue] = errors(footage("demo", "c1.m.strat", beats=4))

    assert issue.code == "unknown_marker"
    assert "c1.m.strat" in issue.message
    assert issue.hint is not None and "c1.m.start" in issue.hint


def test_an_unknown_clip_is_an_error_that_lists_the_screen_recordings() -> None:
    [issue] = errors({**footage("demo", "c9.m.start", "c9.m.done", beats=4), "clip": "c9"})

    assert issue.code == "unknown_clip"
    assert "c9" in issue.message
    assert issue.hint is not None and "c1" in issue.hint


def test_a_marker_of_another_clip_is_an_error() -> None:
    c2 = screen("c2", 5.0, {"start": 0.0})

    issues = errors(footage("demo", "c2.m.start", beats=4), clips=(C1, c2))

    assert codes(issues) == ["cross_clip"]


def test_something_that_is_not_a_marker_id_is_an_error() -> None:
    assert codes(errors(footage("demo", "c1.w4", beats=4))) == ["bad_marker"]


def test_source_seconds_on_a_clip_without_markers_resolve_with_a_warning() -> None:
    brought = screen("c1", 10.0)

    result = resolve([brought], product(footage("demo", 2.0, 6.0, beats=4)), Config())

    [scene] = result.timeline.scenes
    assert isinstance(scene, TimelineFootage)
    assert (scene.src_in_s, scene.src_out_s) == (2.0, 6.0)
    [warning] = result.warnings
    assert warning.code == "seconds_addressed"
    assert warning.hint is not None


def test_source_seconds_on_a_clip_with_markers_are_an_error() -> None:
    assert codes(errors(footage("demo", 2.0, "c1.m.done", beats=4))) == ["seconds_on_marked_clip"]


def test_any_format_other_than_16x9_is_an_error() -> None:
    [issue] = errors(title("a", beats=2), formats=["9x16", "16x9"])

    assert issue.code == "product_format"
    assert "9x16" in issue.message
    assert issue.hint is not None


def test_every_problem_is_listed_at_once() -> None:
    issues = errors(
        title("a"),
        title("a", beats=2, seconds=1),
        footage("demo", "c1.m.nope", "c1.m.done", beats=2, rate=2),
        formats=["4x5"],
    )

    assert sorted(codes(issues)) == [
        "duplicate_scene",
        "length_and_rate",
        "product_format",
        "scene_length",
        "scene_length",
        "unknown_marker",
    ]


def test_a_range_that_runs_backwards_or_past_the_clip_is_an_error() -> None:
    backwards = errors(footage("demo", "c1.m.done", "c1.m.start", beats=4))
    past = errors(footage("demo", "c1.m.done", {"marker": "c1.m.done", "offset_s": 30}, beats=4))

    assert codes(backwards) == ["reversed_range"]
    assert codes(past) == ["outside_clip"]


def test_an_accent_word_missing_from_the_headline_is_an_error() -> None:
    assert codes(errors(title("a", beats=2, accent=["ideas"]))) == ["unknown_accent"]


def test_footage_of_a_clip_that_is_not_a_screen_recording_is_an_error() -> None:
    image = screen("i1", 0.0)
    image.clip.role = "image"

    issues = errors({**footage("demo", 0.0, 1.0, beats=2), "clip": "i1"}, clips=(C1, image))

    assert codes(issues) == ["unknown_clip"]


def test_a_video_over_the_duration_limit_is_a_warning() -> None:
    result = resolve([C1], product(title("a", seconds=50), max_duration_s=30), Config())

    assert [w.code for w in result.warnings] == ["too_long"]
