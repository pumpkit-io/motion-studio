"""The resolver (guide §6.5): a pure function from analysis, EDL and config to a timeline."""

from collections.abc import Sequence
from dataclasses import dataclass, field

from reelcut.analysis import ClipAnalysis
from reelcut.config import Config, Edit
from reelcut.edl.issues import Issue, Problems
from reelcut.edl.models import (
    Crop,
    DropRange,
    Edl,
    FormatSpec,
    Run,
    SafeZone,
    Timeline,
    TimelineCaptions,
    TimelineWord,
)
from reelcut.edl.refs import RefIndex, WordSpan
from reelcut.edl.runs import SourceRun, cut_segment


@dataclass
class ResolveStats:
    """Counts the validate summary reports."""

    words_total: int = 0
    words_kept: int = 0
    hard_fillers_removed: int = 0
    pauses_tightened: int = 0
    runs_per_segment: dict[str, int] = field(default_factory=lambda: dict[str, int]())


@dataclass
class Resolution:
    timeline: Timeline
    warnings: list[Issue]
    stats: ResolveStats


def resolve(clips: Sequence[ClipAnalysis], edl: Edl, config: Config) -> Resolution:
    """Resolve `edl` against the analyses. Raises EdlError listing every error found.

    `config` is the effective config; the EDL's own policy is applied on top of its [edit].
    """
    policy = _policy(config, edl)
    fps = config.defaults.fps
    problems = Problems()
    index = RefIndex(clips)
    stats = ResolveStats(words_total=sum(len(c.words) for c in index.aroll()))

    spans = index.segment_spans(edl.segments, problems)
    dropped = index.word_list(edl.drop_words, "drop_words", problems)
    keep = index.word_list(edl.keep_words, "keep_words", problems)
    index.check_ranges(edl.drop_ranges, problems)
    problems.raise_errors()
    for clip_id, i in sorted(dropped & keep):
        problems.warn(
            "drop_and_keep",
            f"{clip_id}.w{i} is in both drop_words and keep_words; it is dropped",
            hint="remove it from one of the two lists",
        )

    source_runs: list[SourceRun] = []
    for segment, span in zip(edl.segments, spans, strict=True):
        assert span is not None
        analysis = index.clips[span.clip]
        ranges = [r for r in edl.drop_ranges if r.clip == span.clip]
        explicit = {i for c, i in dropped if c == span.clip} | _in_ranges(analysis, span, ranges)
        fillers = _fillers(analysis, span, policy, {i for c, i in keep if c == span.clip})
        removed = explicit | fillers
        stats.hard_fillers_removed += sum(
            1 for i in fillers - explicit if analysis.words[i].filler == "hard"
        )
        cut = cut_segment(segment.id, analysis, span, removed, ranges, policy, fps, problems)
        if not cut.runs:
            problems.warn(
                "empty_segment",
                f"segment {segment.id} keeps no words",
                hint="widen it, or remove it from segments",
            )
        stats.pauses_tightened += cut.pauses_tightened
        stats.runs_per_segment[segment.id] = len(cut.runs)
        source_runs.extend(cut.runs)

    runs: list[Run] = []
    timeline_words: list[TimelineWord] = []
    out = 0
    for source in source_runs:
        length = source.end_f - source.start_f
        src_in = source.start_f / fps
        runs.append(
            Run(
                segment=source.segment,
                clip=source.clip,
                src_in_s=src_in,
                src_out_s=source.end_f / fps,
                out_in=out,
                out_out=out + length,
                crop=Crop(cx=0.5, cy=0.5),
                face=False,
                base_scale=1.0,
            )
        )
        for word in source.words:
            timeline_words.append(
                TimelineWord(
                    id=word.id,
                    text=word.text,
                    start_ms=round((out / fps + word.start - src_in) * 1000),
                    end_ms=round((out / fps + word.end - src_in) * 1000),
                )
            )
        out += length
    stats.words_kept = len(timeline_words)

    timeline = Timeline(
        title=edl.title,
        language=edl.language,
        fps=fps,
        duration_frames=out,
        formats=[_format_spec(name) for name in edl.formats or config.defaults.formats],
        runs=runs,
        words=timeline_words,
        events=[],
        captions=TimelineCaptions(**config.captions.model_dump()),
        brand=config.brand,
        music_path=None,
    )
    return Resolution(timeline=timeline, warnings=problems.warnings, stats=stats)


def _policy(config: Config, edl: Edl) -> Edit:
    overrides = edl.policy.model_dump(exclude_none=True)
    return Edit.model_validate({**config.edit.model_dump(), **overrides})


def _in_ranges(analysis: ClipAnalysis, span: WordSpan, ranges: Sequence[DropRange]) -> set[int]:
    """Words whose middle lies inside a drop range."""
    found: set[int] = set()
    for i in range(span.first, span.last + 1):
        word = analysis.words[i]
        middle = (word.start + word.end) / 2
        if any(r.start <= middle <= r.end for r in ranges):
            found.add(i)
    return found


def _fillers(analysis: ClipAnalysis, span: WordSpan, policy: Edit, keep: set[int]) -> set[int]:
    kinds = {"none": (), "hard": ("hard",), "hard+soft": ("hard", "soft")}[policy.drop_fillers]
    return {
        i
        for i in range(span.first, span.last + 1)
        if analysis.words[i].filler in kinds and i not in keep
    }


FORMAT_SIZES = {"9x16": (1080, 1920), "16x9": (1920, 1080), "4x5": (1080, 1350)}

# Approximate platform UI areas: Reels covers the bottom ~20% and the right ~12% (guide §7b).
SAFE_ZONES = {
    "9x16": SafeZone(top=0.10, right=0.12, bottom=0.20, left=0.05),
    "16x9": SafeZone(top=0.05, right=0.05, bottom=0.12, left=0.05),
    "4x5": SafeZone(top=0.06, right=0.08, bottom=0.14, left=0.06),
}


def _format_spec(name: str) -> FormatSpec:
    width, height = FORMAT_SIZES[name]
    return FormatSpec.model_validate(
        {"name": name, "width": width, "height": height, "safe_zone": SAFE_ZONES[name]}
    )
