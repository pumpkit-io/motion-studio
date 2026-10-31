"""Camera moves on footage scenes: targets resolved to keyframes in footage pixels."""

from typing import Any

import pytest
from edl_fixtures import product, screen

from motion_studio.analysis.models import Element
from motion_studio.config import Config
from motion_studio.edl import EdlError, Issue, resolve
from motion_studio.edl.models import TimelineCameraKey, TimelineFootage

POST = Element(name="post", x=200, y=100, w=600, h=300)
C1 = screen("c1", 20.0, {"start": 1.0, "typed": 4.0, "done": 9.0}, {"typed": [POST]})


def scene(*moves: dict[str, Any], **extra: Any) -> dict[str, Any]:
    """start 1.0 s to done 9.0 s in 8 beats: twice as fast, so source 4.0 s is output frame 45."""
    return {
        "id": "demo",
        "type": "footage",
        "clip": "c1",
        "from": "c1.m.start",
        "to": "c1.m.done",
        "beats": 8,
        "camera": list(moves),
        **extra,
    }


def keys(*moves: dict[str, Any], clip: Any = C1) -> list[TimelineCameraKey]:
    [resolved] = resolve([clip], product(scene(*moves)), Config()).timeline.scenes
    assert isinstance(resolved, TimelineFootage)
    return resolved.camera


def errors(*moves: dict[str, Any], clip: Any = C1) -> list[Issue]:
    with pytest.raises(EdlError) as caught:
        resolve([clip], product(scene(*moves)), Config())
    return caught.value.problems


def test_a_move_to_an_element_centres_it_at_its_marker_and_zooms_to_fill_70_percent() -> None:
    [key] = keys({"at": "c1.m.typed", "target": "c1.e.post"})

    # 600x300 in 1600x900 footage: width binds, 0.7 * 1600 / 600.
    assert (key.frame, key.cx, key.cy, key.ease) == (45, 500, 250, "smooth")
    assert key.zoom == pytest.approx(1.866667, abs=1e-6)


def test_an_explicit_zoom_is_used_as_given() -> None:
    [key] = keys({"at": "c1.m.typed", "target": "c1.e.post", "zoom": 1.25})

    assert key.zoom == 1.25


def test_the_70_percent_framing_never_zooms_out_or_past_the_limit() -> None:
    [wide, tiny] = keys(
        {"at": "c1.m.start", "target": {"x": 0, "y": 0, "w": 1500, "h": 800}},
        {"at": "c1.m.typed", "target": {"x": 700, "y": 400, "w": 80, "h": 40}},
    )

    assert (wide.zoom, tiny.zoom) == (1.0, 2.0)


def test_full_frames_the_whole_footage_and_a_box_frames_its_centre() -> None:
    [full, box] = keys(
        {"at": "c1.m.start", "target": "full"},
        {"at": "c1.m.typed", "target": {"x": 1000, "y": 500, "w": 400, "h": 200}, "zoom": 1.5},
    )

    assert (full.frame, full.cx, full.cy, full.zoom) == (0, 800, 450, 1.0)
    assert (box.cx, box.cy, box.zoom) == (1200, 600, 1.5)


def test_snap_is_passed_to_the_renderer_and_moves_come_out_in_frame_order() -> None:
    earlier, later = keys(
        {"at": "c1.m.typed", "target": "c1.e.post", "ease": "snap"},
        {"at": {"marker": "c1.m.start", "offset_s": 1.0}, "target": "full"},
    )

    # Source 2.0 s is 1 s into the scene at twice the speed: 0.5 s, frame 15.
    assert (earlier.frame, earlier.ease) == (15, "smooth")
    assert (later.frame, later.ease) == (45, "snap")


def test_an_element_is_boxed_where_it_was_captured_at_the_nearest_marker() -> None:
    moved = Element(name="post", x=0, y=0, w=600, h=300)
    clip = screen(
        "c1", 20.0, {"start": 1.0, "typed": 4.0, "done": 9.0}, {"start": [moved], "typed": [POST]}
    )

    first, second = keys(
        {"at": "c1.m.start", "target": "c1.e.post"},
        {"at": {"marker": "c1.m.typed", "offset_s": 3.0}, "target": "c1.e.post"},
        clip=clip,
    )

    assert (first.cx, second.cx) == (300, 500)


def test_a_zoom_past_2x_on_1_to_1_footage_is_an_error_with_the_limit() -> None:
    [issue] = errors({"at": "c1.m.typed", "target": "c1.e.post", "zoom": 2.5})

    assert issue.code == "zoom_too_far"
    assert "camera[0]" in issue.message
    assert issue.hint is not None and "2.00" in issue.hint


def test_larger_footage_can_zoom_further_and_smaller_footage_not_at_all() -> None:
    retina = screen("c1", 20.0, {"start": 1.0, "typed": 4.0, "done": 9.0}, size=(3200, 1800))
    small = screen("c1", 20.0, {"start": 1.0, "typed": 4.0, "done": 9.0}, size=(800, 450))
    move = {"at": "c1.m.typed", "target": "full", "zoom": 3.5}

    [key] = keys(move, clip=retina)

    assert key.zoom == 3.5
    assert [i.code for i in errors({**move, "zoom": 1.1}, clip=small)] == ["zoom_too_far"]


def test_a_target_outside_the_footage_is_an_error_with_a_fix() -> None:
    [issue] = errors({"at": "c1.m.typed", "target": {"x": 1400, "y": 0, "w": 400, "h": 100}})

    assert issue.code == "target_outside"
    assert "1600x900" in issue.message
    assert issue.hint is not None


def test_an_element_captured_partly_off_screen_is_outside_the_footage() -> None:
    clipped = Element(name="menu", x=-40, y=10, w=200, h=50)
    clip = screen("c1", 20.0, {"start": 1.0, "typed": 4.0, "done": 9.0}, {"typed": [clipped]})

    issues = errors({"at": "c1.m.typed", "target": "c1.e.menu"}, clip=clip)

    assert [i.code for i in issues] == ["target_outside"]


def test_an_unknown_element_is_an_error_that_lists_the_recordings_elements() -> None:
    [issue] = errors({"at": "c1.m.typed", "target": "c1.e.pots"})

    assert issue.code == "unknown_element"
    assert issue.hint is not None and "c1.e.post" in issue.hint


def test_a_target_that_is_no_element_id_or_an_element_of_another_clip_is_an_error() -> None:
    issues = errors(
        {"at": "c1.m.typed", "target": "post"},
        {"at": "c1.m.typed", "target": "c2.e.post"},
    )

    assert [i.code for i in issues] == ["bad_target", "cross_clip"]


def test_a_move_outside_the_scenes_footage_or_at_an_unknown_marker_is_an_error() -> None:
    issues = errors(
        {"at": {"marker": "c1.m.done", "offset_s": 0.5}, "target": "full"},
        {"at": "c1.m.nope", "target": "full"},
    )

    assert [i.code for i in issues] == ["move_outside_scene", "unknown_marker"]


def test_a_scene_without_camera_moves_rests() -> None:
    assert keys() == []
