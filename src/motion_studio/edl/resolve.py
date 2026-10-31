"""The resolver (guide §6.5): a pure function from analysis, EDL and config to a timeline."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from statistics import median
from typing import Any

from motion_studio import lang
from motion_studio.analysis import ClipAnalysis, project_language
from motion_studio.config import Config, Edit
from motion_studio.edl.events import OutputMap, resolve_events
from motion_studio.edl.grid import DEFAULT_BEATS_PER_BAR, BeatGrid
from motion_studio.edl.issues import Issue, Problems
from motion_studio.edl.models import (
    Crop,
    DropRange,
    Edl,
    FormatSpec,
    ProductEdl,
    Run,
    SafeZone,
    TalkEdl,
    Timeline,
    TimelineBrand,
    TimelineCaptions,
    TimelineWord,
)
from motion_studio.edl.product import PRODUCT_FORMATS, BrandAssets, resolve_scenes
from motion_studio.edl.refs import RefIndex, WordSpan
from motion_studio.edl.runs import SourceRun, cut_segment

# The music stage writes the bed here, relative to the project.
MUSIC_PATH = "build/music.wav"


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
    # The beat grid a product EDL's scenes sit on.
    grid: BeatGrid | None = None


def resolve(
    clips: Sequence[ClipAnalysis],
    edl: Edl,
    config: Config,
    beats: Sequence[float] | None = None,
    *,
    beats_per_bar: int = DEFAULT_BEATS_PER_BAR,
    brand: BrandAssets | None = None,
) -> Resolution:
    """Resolve `edl` against the analyses. Raises EdlError listing every error found.

    `config` is the effective config; a talk EDL's own policy is applied on top of its [edit].
    `beats` are music beat times in output seconds. B-roll and image starts snap to them in a
    talk EDL; a product EDL's scenes are laid on them, or on 120 bpm without music. `brand` holds
    the `[brand]` files a product EDL's scenes may need, loaded by the caller.
    """
    if isinstance(edl, ProductEdl):
        grid = BeatGrid.of(beats, beats_per_bar)
        return _resolve_product(clips, edl, config, grid, brand or BrandAssets())
    return _resolve_talk(clips, edl, config, beats)


def _resolve_product(
    clips: Sequence[ClipAnalysis],
    edl: ProductEdl,
    config: Config,
    grid: BeatGrid,
    brand: BrandAssets,
) -> Resolution:
    problems = Problems()
    language = _language(edl, clips, config, problems)
    resolved = resolve_scenes(clips, edl, config, grid, problems, brand)
    problems.raise_errors()
    fps = config.defaults.fps
    _check_length(resolved.duration_frames / fps, edl, config, problems)
    music_mode = edl.music.mode or config.music.mode
    timeline = Timeline(
        kind="product",
        title=edl.title,
        language=language,
        fps=fps,
        duration_frames=resolved.duration_frames,
        formats=[_format_spec(name) for name in PRODUCT_FORMATS],
        runs=[],
        words=[],
        events=[],
        scenes=resolved.scenes,
        captions=_captions(config, edl, language),
        brand=TimelineBrand(
            primary=config.brand.primary,
            accent=config.brand.accent,
            logo=config.brand.logo,
            wordmark=brand.wordmark,
            mascot=brand.mascot,
        ),
        music_path=None if music_mode == "none" else MUSIC_PATH,
    )
    return Resolution(
        timeline=timeline, warnings=problems.warnings, stats=ResolveStats(), grid=grid
    )


def _language(edl: Edl, clips: Sequence[ClipAnalysis], config: Config, problems: Problems) -> str:
    language = edl.language or project_language(clips, config.defaults.language)
    if language not in lang.available_languages():
        problems.error(
            "unknown_language",
            f"language {language} has no data file; available: "
            + ", ".join(lang.available_languages()),
        )
    return language


def _check_length(seconds: float, edl: Edl, config: Config, problems: Problems) -> None:
    limit = edl.max_duration_s or config.defaults.max_duration_s
    if seconds > limit:
        hint = (
            "shorten or drop a scene"
            if isinstance(edl, ProductEdl)
            else "drop or shorten a segment, or lower policy.max_pause_ms"
        )
        problems.warn("too_long", f"duration {seconds:.1f} s is over the {limit:.1f} s limit", hint)


def _resolve_talk(
    clips: Sequence[ClipAnalysis],
    edl: TalkEdl,
    config: Config,
    beats: Sequence[float] | None,
) -> Resolution:
    policy = _policy(config, edl)
    fps = config.defaults.fps
    problems = Problems()
    index = RefIndex(clips)
    stats = ResolveStats(words_total=sum(len(c.words) for c in index.aroll()))

    spans = index.segment_spans(edl.segments, problems)
    dropped = index.word_list(edl.drop_words, "drop_words", problems)
    keep = index.word_list(edl.keep_words, "keep_words", problems)
    index.check_ranges(edl.drop_ranges, problems)
    language = _language(edl, clips, config, problems)
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
    scales = _punch_scales(source_runs, policy)
    for source, scale in zip(source_runs, scales, strict=True):
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
                **_framing(index.clips[source.clip], src_in, source.end_f / fps),
                base_scale=scale,
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

    segment_spans: dict[str, tuple[int, int] | None] = {s.id: None for s in edl.segments}
    for run in runs:
        current = segment_spans[run.segment]
        segment_spans[run.segment] = (current[0] if current else run.out_in, run.out_out)
    kept: dict[str, list[int]] = {}
    for source in source_runs:
        kept.setdefault(source.clip, []).extend(_index_of(w.id) for w in source.words)
    output = OutputMap(
        fps=fps,
        words={w.id: w for w in timeline_words},
        kept={c: sorted(indices) for c, indices in kept.items()},
        segments=segment_spans,
    )
    resolved = resolve_events(edl.events, index, output, beats, problems)
    problems.raise_errors()
    for word in timeline_words:
        word.emphasis = word.id in resolved.emphasis

    _check_length(out / fps, edl, config, problems)

    music_mode = edl.music.mode or config.music.mode
    timeline = Timeline(
        title=edl.title,
        language=language,
        fps=fps,
        duration_frames=out,
        formats=[_format_spec(name) for name in edl.formats or config.defaults.formats],
        runs=runs,
        words=timeline_words,
        events=resolved.events,
        captions=_captions(config, edl, language),
        brand=TimelineBrand(
            primary=config.brand.primary, accent=config.brand.accent, logo=config.brand.logo
        ),
        music_path=None if music_mode == "none" else MUSIC_PATH,
    )
    return Resolution(timeline=timeline, warnings=problems.warnings, stats=stats)


def _index_of(word_id: str) -> int:
    return int(word_id.rsplit(".w", 1)[1])


def _punch_scales(runs: Sequence[SourceRun], policy: Edit) -> list[float]:
    """Alternate 1.0 and the punch scale at each jump cut; a cut to another clip resets it."""
    scales: list[float] = []
    for k, run in enumerate(runs):
        scale = 1.0
        if k > 0 and runs[k - 1].clip == run.clip:
            scale = scales[-1]
            if policy.jumpcut_punch and runs[k - 1].end_f != run.start_f:
                scale = policy.jumpcut_punch_scale if scale == 1.0 else 1.0
        scales.append(scale)
    return scales


def _framing(analysis: ClipAnalysis, start: float, end: float) -> dict[str, Any]:
    """A static crop per run: the median face centre, or the frame centre with no face."""
    inside = [s for s in analysis.faces.samples if start <= s.t <= end]
    if not inside:
        return {"crop": Crop(cx=0.5, cy=0.5), "face": False}
    crop = Crop(cx=median(s.cx for s in inside), cy=median(s.cy for s in inside))
    return {"crop": crop, "face": True}


def _captions(config: Config, edl: Edl, language: str) -> TimelineCaptions:
    settings: dict[str, Any] = {
        **config.captions.model_dump(),
        **edl.captions.model_dump(exclude_none=True),
    }
    rules = lang.load_language(language).captions
    settings["max_chars_per_page"] = rules.max_chars_per_page
    settings["keep_with_next"] = rules.keep_with_next
    return TimelineCaptions.model_validate(settings)


def _policy(config: Config, edl: TalkEdl) -> Edit:
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
