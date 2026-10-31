"""Properties of the resolver (guide §8 Phase 6) over generated transcripts and EDLs."""

import itertools
import random
from dataclasses import dataclass

from hypothesis import given, settings
from hypothesis import strategies as st

from motion_studio.analysis import ClipAnalysis, ClipInfo, Span, TranscribedWord, analyse_transcript
from motion_studio.config import Config, Defaults
from motion_studio.edl import Edl, Timeline, resolve
from motion_studio.edl.models import Run
from motion_studio.lang import load_language

ENGLISH = load_language("en")
TOKENS = ["hello", "world.", "um", "uh", "like", "so", "great", "really", "the"]


@dataclass
class Edit:
    clips: list[ClipAnalysis]
    edl: Edl
    config: Config


@st.composite
def transcripts(draw: st.DrawFn, clip_id: str, min_gap_ms: int) -> ClipAnalysis:
    count = draw(st.integers(3, 25))
    t = draw(st.integers(0, 1000))
    words: list[TranscribedWord] = []
    for _ in range(count):
        length = draw(st.integers(80, 600))
        text = draw(st.sampled_from(TOKENS))
        words.append(TranscribedWord(text=text, start=t / 1000, end=(t + length) / 1000))
        t += length + draw(st.one_of(st.integers(min_gap_ms, 300), st.integers(300, 1500)))
    duration = words[-1].end + 0.5
    info = ClipInfo(id=clip_id, role="aroll", source=f"raw/{clip_id}.mov", duration_s=duration)
    return analyse_transcript(info, words, [Span(start=0.0, end=duration)], ENGLISH)


@st.composite
def edits(draw: st.DrawFn, min_gap_ms: int = 70) -> Edit:
    """Disjoint segments over one or two clips, in a random order, with random drops."""
    clips = [draw(transcripts(f"c{n}", min_gap_ms)) for n in range(1, draw(st.integers(1, 2)) + 1)]
    segments: list[dict[str, str]] = []
    drop_words: list[str] = []
    for analysis in clips:
        count = len(analysis.words)
        cuts = sorted(draw(st.sets(st.integers(0, count), min_size=2, max_size=6)))
        for lo, hi in itertools.pairwise(cuts):
            if draw(st.booleans()) or not segments:
                cid = analysis.clip.id
                segments.append(
                    {"id": f"{cid}-{lo}", "from": f"{cid}.w{lo}", "to": f"{cid}.w{hi - 1}"}
                )
        drop_words += [w.id for w in analysis.words if draw(st.integers(0, 9)) == 0]
    order = draw(st.permutations(segments))
    policy = {
        "pad_in_ms": draw(st.integers(0, 200)),
        "pad_out_ms": draw(st.integers(0, 200)),
        "max_pause_ms": draw(st.integers(100, 800)),
        "min_segment_ms": draw(st.integers(0, 600)),
        "drop_fillers": draw(st.sampled_from(["none", "hard", "hard+soft"])),
        "jumpcut_punch": draw(st.booleans()),
    }
    edl = Edl.model_validate(
        {"segments": order, "drop_words": drop_words, "policy": policy, "music": {"mode": "none"}}
    )
    config = Config(defaults=Defaults(fps=draw(st.sampled_from([24, 25, 30, 60]))))
    return Edit(clips, edl, config)


def timeline_of(edit: Edit) -> Timeline:
    return resolve(edit.clips, edit.edl, edit.config).timeline


def run_of(timeline: Timeline, ms: float) -> Run:
    fps = timeline.fps
    return next(r for r in timeline.runs if r.out_in * 1000 / fps <= ms < r.out_out * 1000 / fps)


SETTINGS = settings(max_examples=300, deadline=None)


@SETTINGS
@given(edits())
def test_runs_never_overlap_and_add_up_to_the_duration(edit: Edit) -> None:
    timeline = timeline_of(edit)

    out = 0
    for run in timeline.runs:
        assert run.out_in == out
        assert run.out_out > run.out_in
        out = run.out_out
    assert timeline.duration_frames == sum(r.out_out - r.out_in for r in timeline.runs)
    for a in timeline.runs:
        for b in timeline.runs:
            if a is not b and a.clip == b.clip:
                assert a.src_out_s <= b.src_in_s + 1e-9 or b.src_out_s <= a.src_in_s + 1e-9


@SETTINGS
@given(edits())
def test_every_kept_word_lies_whole_inside_its_run(edit: Edit) -> None:
    timeline = timeline_of(edit)
    source = {w.id: w for c in edit.clips for w in c.words}

    for word in timeline.words:
        run = run_of(timeline, (word.start_ms + word.end_ms) / 2)
        assert word.id.split(".")[0] == run.clip
        assert word.start_ms >= round(run.out_in * 1000 / timeline.fps) - 1
        assert word.end_ms <= round(run.out_out * 1000 / timeline.fps) + 1
        original = source[word.id]
        assert abs((word.end_ms - word.start_ms) - (original.end - original.start) * 1000) <= 1
        offset = word.start_ms - run.out_in * 1000 / timeline.fps
        assert abs(run.src_in_s + offset / 1000 - original.start) <= 0.001


@SETTINGS
@given(edits(min_gap_ms=0))
def test_no_run_crosses_a_removed_word(edit: Edit) -> None:
    timeline = timeline_of(edit)
    kept = {w.id for w in timeline.words}

    for run in timeline.runs:
        [analysis] = [c for c in edit.clips if c.clip.id == run.clip]
        for word in analysis.words:
            if word.id not in kept:
                assert run.src_out_s <= word.start + 1e-9 or run.src_in_s >= word.end - 1e-9


@SETTINGS
@given(edits())
def test_times_are_frame_aligned(edit: Edit) -> None:
    timeline = timeline_of(edit)

    for run in timeline.runs:
        for t in (run.src_in_s, run.src_out_s):
            assert abs(t * timeline.fps - round(t * timeline.fps)) < 1e-6


@SETTINGS
@given(edits(), st.randoms(use_true_random=False))
def test_reordering_segments_reorders_the_output(edit: Edit, rng: random.Random) -> None:
    shuffled = list(edit.edl.segments)
    rng.shuffle(shuffled)
    reordered = edit.edl.model_copy(update={"segments": shuffled})

    before = timeline_of(edit)
    after = resolve(edit.clips, reordered, edit.config).timeline

    def by_segment(timeline: Timeline) -> dict[str, list[tuple[str, float, float]]]:
        found: dict[str, list[tuple[str, float, float]]] = {}
        for r in timeline.runs:
            found.setdefault(r.segment, []).append((r.clip, r.src_in_s, r.src_out_s))
        return found

    def order(timeline: Timeline) -> list[str]:
        return list(dict.fromkeys(r.segment for r in timeline.runs))

    assert by_segment(after) == by_segment(before)
    assert order(after) == [s.id for s in shuffled if s.id in by_segment(before)]
    assert before.duration_frames == after.duration_frames
