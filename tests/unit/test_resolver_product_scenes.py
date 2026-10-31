"""The resolver on kinetic text, proof and logo outro scenes, and footage in a terminal frame."""

from typing import Any

import pytest
from edl_fixtures import asset, product, screen

from motion_studio.config import Config
from motion_studio.edl import EdlError, Issue, resolve
from motion_studio.edl.models import (
    TimelineFootage,
    TimelineKineticText,
    TimelineLogoOutro,
    TimelineMascot,
    TimelineProof,
    TimelineSpriteFrame,
)
from motion_studio.edl.product import BrandAssets

C1 = screen("c1", 20.0, {"start": 1.0, "done": 9.0})
I1 = asset("i1", "image", 0.0)
I1.clip.width, I1.clip.height = 1644, 1245
MASCOT = TimelineMascot(
    sheet="library/brand/mascot.png",
    sheet_width=64,
    sheet_height=32,
    frame_width=32,
    frame_height=32,
    frames=[TimelineSpriteFrame(x=0, y=0, ms=600), TimelineSpriteFrame(x=32, y=0, ms=80)],
    loops=0,
)
BRAND = BrandAssets(wordmark="library/brand/wordmark.svg", mascot=MASCOT)
OUTRO: dict[str, Any] = {
    "id": "outro",
    "type": "logo_outro",
    "bars": 2,
    "tagline": "Write like the people you admire.",
    "accent": ["admire."],
    "url": "example.com",
}


def errors(*scenes: dict[str, Any], **kwargs: Any) -> list[Issue]:
    with pytest.raises(EdlError) as caught:
        resolve([C1, I1], product(*scenes), Config(), **kwargs)
    return caught.value.problems


def test_kinetic_text_shares_the_scene_between_its_lines_in_order() -> None:
    edl = product(
        {"id": "warm", "type": "title_card", "beats": 2, "headline": "Hi."},
        {
            "id": "intro",
            "type": "kinetic_text",
            "bars": 3,
            "lines": ["Got an idea?", "Turning it into a post…", "…is the hard part."],
            "accent": ["idea?", "hard"],
        },
    )

    [_, scene] = resolve([C1], edl, Config()).timeline.scenes

    # Three bars at 120 bpm are 180 frames after the 30-frame card: 60 frames a line.
    assert isinstance(scene, TimelineKineticText)
    assert (scene.start, scene.end) == (30, 210)
    assert [(line.start, line.end) for line in scene.lines] == [(30, 90), (90, 150), (150, 210)]
    assert [(w.text, w.accent) for w in scene.lines[0].words] == [
        ("Got", False),
        ("an", False),
        ("idea?", True),
    ]
    assert [w.text for w in scene.lines[2].words if w.accent] == ["hard"]


def test_an_accent_word_in_no_line_of_kinetic_text_is_an_error() -> None:
    scene = {"id": "intro", "type": "kinetic_text", "beats": 4, "lines": ["Hi."], "accent": ["yo"]}

    [issue] = errors(scene)

    assert issue.code == "unknown_accent"
    assert "yo" in issue.message


def test_footage_can_sit_in_a_terminal_frame_with_a_title() -> None:
    scene = {
        "id": "term",
        "type": "footage",
        "clip": "c1",
        "from": "c1.m.start",
        "to": "c1.m.done",
        "device_frame": "terminal",
        "address": "claude: ~/demo",
    }

    [resolved] = resolve([C1], product(scene), Config()).timeline.scenes

    assert isinstance(resolved, TimelineFootage)
    assert (resolved.device_frame, resolved.address) == ("terminal", "claude: ~/demo")


def test_a_proof_scene_shows_an_image_beside_its_headline_and_badge() -> None:
    scene = {
        "id": "tweet",
        "type": "proof",
        "beats": 8,
        "image": "i1",
        "headline": "Live on X.",
        "accent": ["X."],
        "subline": "One click.",
        "badge": "Posted",
    }

    [proof] = resolve([C1, I1], product(scene), Config()).timeline.scenes

    assert isinstance(proof, TimelineProof)
    assert (proof.start, proof.end, proof.src) == (0, 120, "media/i1.mp4")
    assert (proof.width, proof.height) == (1644, 1245)
    assert [(w.text, w.accent) for w in proof.headline] == [
        ("Live", False),
        ("on", False),
        ("X.", True),
    ]
    assert (proof.subline, proof.badge) == ("One click.", "Posted")


def test_a_proof_scene_needs_no_headline() -> None:
    scene = {"id": "tweet", "type": "proof", "beats": 8, "image": "i1"}

    [proof] = resolve([C1, I1], product(scene), Config()).timeline.scenes

    assert isinstance(proof, TimelineProof)
    assert (proof.headline, proof.subline, proof.badge) == ([], None, None)


def test_a_proof_of_something_that_is_not_an_image_is_an_error_listing_the_images() -> None:
    [issue] = errors({"id": "tweet", "type": "proof", "beats": 8, "image": "c1"})

    assert issue.code == "unknown_image"
    assert "images: i1" in (issue.hint or "")


def test_a_logo_outro_carries_its_tagline_and_url_and_the_brand_assets() -> None:
    timeline = resolve([C1], product(OUTRO), Config(), brand=BRAND).timeline

    [outro] = timeline.scenes
    assert isinstance(outro, TimelineLogoOutro)
    assert (outro.start, outro.end, outro.url, outro.mascot) == (0, 120, "example.com", True)
    assert [w.text for w in outro.tagline if w.accent] == ["admire."]
    assert timeline.brand.wordmark == "library/brand/wordmark.svg"
    assert timeline.brand.mascot == MASCOT


def test_a_logo_outro_without_the_brand_assets_is_an_error_naming_each_config_key() -> None:
    issues = errors(OUTRO)

    assert [i.code for i in issues] == ["missing_brand_asset", "missing_brand_asset"]
    assert "[brand] wordmark is not set" in issues[0].message
    assert "[brand] mascot is not set" in issues[1].message
    assert all("motion-studio.toml" in (i.hint or "") for i in issues)


def test_the_reason_a_configured_asset_failed_to_load_is_in_the_error() -> None:
    brand = BrandAssets(mascot=MASCOT, broken={"wordmark": "names logo.svg, which does not exist"})

    [issue] = errors(OUTRO, brand=brand)

    assert "[brand] wordmark names logo.svg, which does not exist" in issue.message


def test_a_logo_outro_can_leave_the_mascot_out() -> None:
    brand = BrandAssets(wordmark="library/brand/wordmark.svg")

    [outro] = resolve(
        [C1], product({**OUTRO, "mascot": False}), Config(), brand=brand
    ).timeline.scenes

    assert isinstance(outro, TimelineLogoOutro)
    assert outro.mascot is False
