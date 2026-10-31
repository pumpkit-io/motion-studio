"""Highlight, mask, caption pill and flash events on product scenes, resolved to output frames."""

from typing import Any

import pytest
from edl_fixtures import product, screen

from motion_studio.analysis.models import Element
from motion_studio.config import Config
from motion_studio.edl import EdlError, Issue, resolve
from motion_studio.edl.models import TimelineEvent

POST = Element(name="post", x=200, y=100, w=600, h=300)
C1 = screen("c1", 20.0, {"start": 1.0, "typed": 4.0, "done": 9.0}, {"typed": [POST]})
CARD = {"id": "intro", "type": "title_card", "beats": 4, "headline": "Meet the app."}


def footage(*events: dict[str, Any], **extra: Any) -> dict[str, Any]:
    """start 1.0 s to done 9.0 s in 8 beats after a 4-beat card: frames 60 to 180, at 2x."""
    return {
        "id": "demo",
        "type": "footage",
        "clip": "c1",
        "from": "c1.m.start",
        "to": "c1.m.done",
        "beats": 8,
        "events": list(events),
        **extra,
    }


def events(*scenes: dict[str, Any], clip: Any = C1) -> list[TimelineEvent]:
    return resolve([clip], product(CARD, *scenes), Config()).timeline.events


def errors(*scenes: dict[str, Any], clip: Any = C1) -> list[Issue]:
    with pytest.raises(EdlError) as caught:
        resolve([clip], product(CARD, *scenes), Config())
    return caught.value.problems


def test_a_highlight_on_an_element_boxes_it_from_start_to_end_in_output_frames() -> None:
    [event] = events(
        footage(
            {
                "type": "highlight",
                "target": "c1.e.post",
                "start": "c1.m.typed",
                "end": {"marker": "c1.m.typed", "offset_s": 2.0},
                "label": "Your post",
            }
        )
    )

    # Source 4.0 s is 3 s into the footage at 2x: 1.5 s, frame 60 + 45.
    assert event.model_dump() == {
        "type": "highlight",
        "scene": "demo",
        "clip": "c1",
        "start": 105,
        "end": 135,
        "src_start_s": 4.0,
        "src_end_s": 6.0,
        "element": "c1.e.post",
        "x": 200,
        "y": 100,
        "w": 600,
        "h": 300,
        "label": "Your post",
    }


def test_a_mask_on_a_box_covers_the_whole_scene_by_default_in_the_frames_background() -> None:
    [event] = events(footage({"type": "mask", "target": {"x": 0, "y": 0, "w": 1600, "h": 118}}))

    assert (event.type, event.start, event.end) == ("mask", 60, 180)
    assert event.model_dump(include={"element", "x", "y", "w", "h", "color"}) == {
        "element": None,
        "x": 0,
        "y": 0,
        "w": 1600,
        "h": 118,
        "color": None,
    }


def test_a_mask_covers_exactly_its_range_in_its_own_colour() -> None:
    [event] = events(
        footage(
            {
                "type": "mask",
                "target": {"x": 10, "y": 20, "w": 30, "h": 40},
                "start": {"marker": "c1.m.start", "offset_s": 1.0},
                "end": "c1.m.typed",
                "color": "#1E1E2E",
            }
        )
    )

    # Source 2.0 s and 4.0 s, 1 s and 3 s into the footage at 2x: frames 75 and 105.
    assert event.model_dump(include={"start", "end", "src_start_s", "src_end_s", "color"}) == {
        "start": 75,
        "end": 105,
        "src_start_s": 2.0,
        "src_end_s": 4.0,
        "color": "#1E1E2E",
    }


def test_an_element_is_boxed_where_it_was_captured_at_the_marker_nearest_the_start() -> None:
    moved = Element(name="post", x=0, y=0, w=600, h=300)
    clip = screen(
        "c1", 20.0, {"start": 1.0, "typed": 4.0, "done": 9.0}, {"start": [moved], "typed": [POST]}
    )

    first, second = events(
        footage(
            {"type": "highlight", "target": "c1.e.post", "end": "c1.m.typed"},
            {"type": "highlight", "target": "c1.e.post", "start": "c1.m.typed"},
        ),
        clip=clip,
    )

    assert (first.model_dump()["x"], second.model_dump()["x"]) == (0, 200)


def test_a_caption_pill_lasts_its_scene_and_a_flash_its_first_five_frames() -> None:
    card = {**CARD, "events": [{"type": "flash"}, {"type": "caption_pill", "text": "Hello"}]}
    resolved = resolve([C1], product(card, footage({"type": "flash", "strength": 0.6})), Config())

    assert [e.model_dump() for e in resolved.timeline.events] == [
        {"type": "flash", "scene": "intro", "start": 0, "end": 5, "strength": 0.35},
        {"type": "caption_pill", "scene": "intro", "start": 0, "end": 60, "text": "Hello"},
        {"type": "flash", "scene": "demo", "start": 60, "end": 65, "strength": 0.6},
    ]


def test_bad_targets_are_the_camera_s_errors_named_after_the_event() -> None:
    issues = errors(
        footage(
            {"type": "highlight", "target": "post"},
            {"type": "highlight", "target": "c1.e.pots"},
            {"type": "mask", "target": {"x": 1500, "y": 0, "w": 200, "h": 50}},
        )
    )

    assert [i.code for i in issues] == ["bad_target", "unknown_element", "target_outside"]
    assert all("scene demo events[" in i.message for i in issues)


def test_a_range_outside_the_scene_or_reversed_is_an_error() -> None:
    issues = errors(
        footage(
            {"type": "highlight", "target": "full", "start": 0.0},
            {"type": "mask", "target": "full", "end": {"marker": "c1.m.done", "offset_s": 1.0}},
            {"type": "mask", "target": "full", "start": "c1.m.typed", "end": "c1.m.start"},
            {"type": "highlight", "target": "full", "start": "c1.m.nope"},
        )
    )

    assert [i.code for i in issues] == [
        "seconds_on_marked_clip",
        "event_outside_scene",
        "reversed_event",
        "unknown_marker",
    ]
    assert issues[1].hint is not None and "from and to" in issues[1].hint


def test_a_highlight_or_mask_off_footage_and_a_second_pill_or_flash_are_errors() -> None:
    card = {
        **CARD,
        "id": "step1",
        "events": [
            {"type": "highlight", "target": "full"},
            {"type": "caption_pill", "text": "One"},
            {"type": "caption_pill", "text": "Two"},
        ],
    }

    issues = errors(card, footage({"type": "flash"}, {"type": "flash"}))

    assert [i.code for i in issues] == ["event_needs_footage", "duplicate_event", "duplicate_event"]
    assert "title_card" in issues[0].message


def test_a_flash_on_terminal_footage_is_softer_by_default() -> None:
    [flash] = events(footage({"type": "flash"}, device_frame="terminal"))

    assert flash.model_dump()["strength"] == 0.12
