"""The validate summary (guide §6.6): what the host agent reads after every EDL change."""

from edl_fixtures import asset, clip, edl

from motion_studio.config import Config
from motion_studio.edl import EdlError, Issue, resolve, summarize
from motion_studio.edl.summary import error_report

C1 = clip(
    "c1",
    "We um really need this.",
    "Second line here today.",
    "A third line to close.",
    "And one more after that.",
)
EVENTS = [
    {"type": "zoom", "at": "c1.w2"},
    {"type": "zoom", "at": "c1.w6"},
    {"type": "push", "from": "body"},
    {"type": "broll", "asset": "b1", "start": "c1.w6", "end": "c1.w8"},
    {"type": "title", "text": "Need this", "start": "c1.w6", "end": "c1.w7"},
    {"type": "emphasis", "words": ["c1.w3", "c1.w4"]},
]


def summary_for(**extra: object):
    the_edl = edl(("hook", "c1.s1", "c1.s1"), ("body", "c1.s0", "c1.s0"), **extra)
    clips = [C1, asset("b1", "broll", 6.0)]
    return summarize(the_edl, resolve(clips, the_edl, Config()), Config(), "build/timeline.json")


def test_the_summary_has_the_guide_shape() -> None:
    lines = summary_for(events=EVENTS, max_duration_s=45).lines()

    assert lines[0] == "✓ edl.json valid · language en · 2 segments → 3 runs"
    assert lines[1].startswith("Duration 3.4s (limit 45s) · words kept 8/19 · ")
    assert lines[1].endswith(" · hard fillers removed 1 · pauses tightened 0")
    assert lines[2] == 'Hook (first 3s): "Second line here today. We really need this."'
    assert lines[3] == "Events: 2 zoom · 1 push · 1 broll · 1 title · emphasis 2"
    assert lines[-1] == "→ build/timeline.json"


def test_the_pace_is_reported_for_choosing_the_music_bpm() -> None:
    assert "· 2.4 words/s ·" in summary_for().lines()[1]


def test_warnings_carry_their_fix() -> None:
    lines = summary_for(events=EVENTS).lines()

    [warning] = [line for line in lines if line.startswith("⚠")]
    assert warning == (
        "⚠ event 5 (title) overlaps event 4 (broll b1) by 0.70 s"
        " → move the title, or accept it drawn over the overlay"
    )


def test_without_events_the_summary_says_so() -> None:
    assert summary_for().lines()[3] == "Events: none"


def test_many_warnings_are_capped_to_keep_the_summary_short() -> None:
    summary = summary_for()
    summary.warnings = [Issue(code="short_run", message=f"run {n}") for n in range(40)]

    lines = summary.lines()

    assert len(lines) < 30
    assert lines[-2] == "⚠ … and 20 more warnings (--json lists them all)"


def test_the_json_carries_the_same_facts() -> None:
    data = summary_for(events=EVENTS, max_duration_s=45).to_json()

    assert data["valid"] is True
    assert data["language"] == "en"
    assert (data["segments"], data["runs"]) == (2, 3)
    assert data["duration_s"] == 3.4
    assert data["limit_s"] == 45
    assert (data["words_kept"], data["words_total"]) == (8, 19)
    assert data["hard_fillers_removed"] == 1
    assert data["hook"] == "Second line here today. We really need this."
    assert data["events"] == {"zoom": 2, "push": 1, "broll": 1, "title": 1, "emphasis": 2}
    assert data["warnings"][0]["code"] == "title_over_broll"
    assert data["timeline"] == "build/timeline.json"


def test_an_error_report_lists_every_problem_with_its_fix() -> None:
    error = EdlError(
        [
            Issue(code="unknown_ref", message="segment a: c1.s9 does not exist", hint="see ids"),
            Issue(code="bad_ref", message="drop_words: c1.s0 is an utterance"),
        ]
    )

    lines, data = error_report(error)

    assert lines == [
        "✗ edl.json has 2 errors",
        "✗ segment a: c1.s9 does not exist → see ids",
        "✗ drop_words: c1.s0 is an utterance",
    ]
    assert data == {
        "valid": False,
        "errors": [
            {
                "code": "unknown_ref",
                "message": "segment a: c1.s9 does not exist",
                "hint": "see ids",
            },
            {"code": "bad_ref", "message": "drop_words: c1.s0 is an utterance", "hint": None},
        ],
    }


def test_an_error_report_is_capped_too() -> None:
    lines, data = error_report(EdlError(Issue(code="x", message=f"e{n}") for n in range(50)))

    assert len(lines) < 30
    assert lines[-1] == "✗ … and 30 more errors (--json lists them all)"
    assert len(data["errors"]) == 50


def test_a_hook_cut_off_at_three_seconds_ends_with_an_ellipsis() -> None:
    long = clip("c1", "One two three four five six seven eight nine ten.")
    the_edl = edl(("hook", "c1.s0", "c1.s0"))

    summary = summarize(the_edl, resolve([long], the_edl, Config()), Config(), "t.json")

    # Words start every 0.4 s from 0.08 s in output time, so eight start before 3 s.
    assert summary.hook == "One two three four five six seven eight"
    assert summary.lines()[2] == 'Hook (first 3s): "One two three four five six seven eight…"'
