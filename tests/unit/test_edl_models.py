"""Reading edl.json into the EDL model (guide §6.4)."""

import pytest

from motion_studio.edl import EdlError, parse_edl

GUIDE_EXAMPLE = {
    "schema_version": 1,
    "title": "Come ho costruito Pumpkit in 2 settimane",
    "language": "it",
    "formats": ["9x16", "16x9"],
    "max_duration_s": 60,
    "policy": {
        "pad_in_ms": 80,
        "pad_out_ms": 120,
        "max_pause_ms": 350,
        "drop_fillers": "hard",
        "jumpcut_punch": True,
    },
    "segments": [
        {"id": "hook", "from": "c1.s2", "to": "c1.s2", "note": "pain-point hook"},
        {"id": "body1", "from": "c1.s0", "to": "c1.w9", "note": "skip 'Allora ehm'"},
        {"id": "body2", "from": "c1.s5", "to": "c1.s12"},
        {"id": "cta", "from": "c2.s3", "to": "c2.s3"},
    ],
    "drop_words": ["c1.w233"],
    "drop_ranges": [{"clip": "c1", "start": 22.3, "end": 22.7}],
    "keep_words": [],
    "events": [
        {"type": "zoom", "at": "c1.w52", "scale": 1.18, "hold_until": "c1.w58", "ease": "snap"},
        {"type": "push", "from": "body2", "scale": 1.06},
        {
            "type": "broll",
            "asset": "b1",
            "start": "c1.w70",
            "end": "c1.w84",
            "asset_in_s": 2.0,
            "mode": "full",
        },
        {
            "type": "image",
            "asset": "i1",
            "start": "c1.w90",
            "end": "c1.w97",
            "mode": "pip",
            "motion": "kenburns",
        },
        {"type": "title", "text": "3 ore → 10 minuti", "start": "c1.w101", "end": "c1.w110"},
        {"type": "emphasis", "words": ["c1.w103", "c1.w106"]},
    ],
    "captions": {"enabled": True, "style": "pop"},
    "music": {
        "mode": "generate",
        "prompt": "upbeat minimal electronic, warm synths, confident, instrumental",
        "bpm": 104,
        "seed": 7,
        "gain_db": -20,
    },
    "rationale": "Hook = strongest pain point.",
}


def test_the_guide_example_round_trips() -> None:
    edl = parse_edl(GUIDE_EXAMPLE)

    assert [s.from_ for s in edl.segments] == ["c1.s2", "c1.s0", "c1.s5", "c2.s3"]
    assert [e.type for e in edl.events] == ["zoom", "push", "broll", "image", "title", "emphasis"]
    assert edl.model_dump(by_alias=True, exclude_unset=True) == GUIDE_EXAMPLE


def test_schema_errors_name_the_field_and_exit_1() -> None:
    bad = {"segments": [], "events": [{"type": "spin", "at": "c1.w0"}], "colour": "red"}

    with pytest.raises(EdlError) as raised:
        parse_edl(bad)

    assert raised.value.exit_code == 1
    assert [(p.code, p.message.split(":")[0]) for p in raised.value.problems] == [
        ("invalid_edl", "segments"),
        ("invalid_edl", "events.0"),
        ("invalid_edl", "colour"),
    ]
