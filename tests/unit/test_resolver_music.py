"""The resolver's checks on `music.align`: a scene to land on, a generated bed, a product EDL."""

import pytest
from edl_fixtures import clip, edl, product

from motion_studio.config import Config
from motion_studio.edl import EdlError, resolve

INTRO = {"id": "intro", "type": "title_card", "beats": 4, "headline": "Hello there."}
LOGO = {"id": "logo", "type": "title_card", "beats": 4, "headline": "Bye now."}


def codes(error: pytest.ExceptionInfo[EdlError]) -> list[str]:
    return [p.code for p in error.value.problems]


def test_an_align_on_a_scene_of_a_generated_bed_resolves() -> None:
    music = {"mode": "generate", "align": {"hit": "drop", "at": "logo"}}

    timeline = resolve([], product(INTRO, LOGO, music=music), Config()).timeline

    assert [s.id for s in timeline.scenes] == ["intro", "logo"]


def test_an_align_at_an_unknown_scene_lists_the_scene_ids() -> None:
    music = {"align": {"hit": "drop", "at": "outro"}}

    with pytest.raises(EdlError) as error:
        resolve([], product(INTRO, LOGO, music=music), Config())

    assert codes(error) == ["align_scene"]
    assert error.value.problems[0].hint == "use one of the scene IDs: intro, logo"


def test_an_align_needs_a_generated_bed() -> None:
    music = {"mode": "library", "align": {"hit": "drop", "at": "logo"}}

    with pytest.raises(EdlError) as error:
        resolve([], product(INTRO, LOGO, music=music), Config())

    assert codes(error) == ["align_mode"]


def test_an_align_in_a_talk_edl_is_an_error() -> None:
    talk = edl(("hook", "c1.s0", "c1.s0"), music={"align": {"hit": "drop", "at": "hook"}})

    with pytest.raises(EdlError) as error:
        resolve([clip("c1", "Hello there.")], talk, Config())

    assert codes(error) == ["align_kind"]
