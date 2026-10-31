"""Product EDLs resolved to a timeline of scenes (ADR 0004), footage addressed by marker (ADR 0005).

Scenes follow each other on the beat grid with no gap. Each scene type has one resolver in
`_SCENES`, which returns the timeline scene for the frames it was given, or None after recording
its problems.
"""

import re
import string
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

from motion_studio.analysis import ClipAnalysis
from motion_studio.config import Config
from motion_studio.edl.grid import BeatGrid
from motion_studio.edl.issues import Problems
from motion_studio.edl.models import (
    FootagePoint,
    FootageScene,
    KineticTextScene,
    LogoOutroScene,
    MarkerPoint,
    ProductEdl,
    ProofScene,
    Scene,
    TimelineFootage,
    TimelineHeadlineWord,
    TimelineKineticLine,
    TimelineKineticText,
    TimelineLogoOutro,
    TimelineMascot,
    TimelineProof,
    TimelineScene,
    TimelineTitleCard,
    TitleCardScene,
)
from motion_studio.paths import WORKSPACE_FILE

PRODUCT_FORMATS = ("16x9",)
# Clip roles a footage scene can play.
FOOTAGE_ROLES = ("screen", "broll")
_MARKER = re.compile(r"^(?P<clip>[a-z]+\d+)\.m\.(?P<name>[A-Za-z0-9_][A-Za-z0-9_-]*)$")
_MARKERS_SHOWN = 8
_MARKERS_HINT = "markers are listed under each screen recording in analysis/packed.md"


@dataclass(frozen=True)
class Slot:
    """Where a scene sits: output seconds on the grid, and its frames."""

    start_s: float
    start: int
    end: int


@dataclass(frozen=True)
class BrandAssets:
    """The `[brand]` files that loaded: the wordmark's path and the mascot's sprite sheet."""

    wordmark: str | None = None
    mascot: TimelineMascot | None = None
    # Why a configured asset did not load, by its key: "names x.svg, which does not exist".
    broken: Mapping[str, str] = field(default_factory=lambda: dict[str, str]())


@dataclass(frozen=True)
class SceneContext:
    clips: dict[str, ClipAnalysis]
    grid: BeatGrid
    fps: int
    problems: Problems
    brand: BrandAssets


@dataclass(frozen=True)
class ProductScenes:
    scenes: list[TimelineScene]
    duration_frames: int


def resolve_scenes(
    clips: Sequence[ClipAnalysis],
    edl: ProductEdl,
    config: Config,
    grid: BeatGrid,
    problems: Problems,
    brand: BrandAssets,
) -> ProductScenes:
    """Every scene on the grid. Errors go to `problems`; the caller raises them."""
    fps = config.defaults.fps
    context = SceneContext({c.clip.id: c for c in clips}, grid, fps, problems, brand)
    _check_formats(edl, problems)
    seen: set[str] = set()
    scenes: list[TimelineScene] = []
    t = 0.0
    frame = 0
    for scene in edl.scenes:
        if scene.id in seen:
            problems.error("duplicate_scene", f"scene id '{scene.id}' is used twice")
        seen.add(scene.id)
        span = None
        if isinstance(scene, FootageScene):
            span = _footage_span(scene, t, context, problems)
        end_s = _scene_end(scene, t, span, context)
        if end_s is None or (isinstance(scene, FootageScene) and span is None):
            continue
        end = max(round(end_s * fps), frame + 1)
        resolved = _SCENES[scene.type](scene, Slot(t, frame, end), context)
        if resolved is not None:
            scenes.append(resolved)
        t, frame = end_s, end
    return ProductScenes(scenes, frame)


def _check_formats(edl: ProductEdl, problems: Problems) -> None:
    other = [f for f in edl.formats or () if f not in PRODUCT_FORMATS]
    if other:
        problems.error(
            "product_format",
            f"formats: product videos render in {', '.join(PRODUCT_FORMATS)} only, not "
            + ", ".join(other),
            hint='set "formats": ["16x9"], or leave formats out',
        )


def _scene_end(
    scene: Scene, t: float, span: tuple[float, float] | None, context: SceneContext
) -> float | None:
    """Output seconds where the scene ends, or None when its length is unknown.

    `span` is a footage scene's source range, when it resolved.
    """
    lengths = [n for n in ("beats", "bars", "seconds") if getattr(scene, n) is not None]
    where = f"scene {scene.id}"
    if isinstance(scene, FootageScene) and not lengths:
        if span is None:
            return None
        seconds = (span[1] - span[0]) / (scene.rate or 1.0)
        beats = max(1, round(seconds / context.grid.beat_s_at(t)))
        return context.grid.after_beats(t, beats)
    if isinstance(scene, FootageScene) and scene.rate is not None:
        context.problems.error(
            "length_and_rate",
            f"{where} sets both {lengths[0]} and rate",
            hint="keep rate to play from..to at that speed (rounded to whole beats), or keep the "
            "length to fit from..to into it",
        )
        return None
    if len(lengths) != 1:
        given = " and ".join(lengths) if lengths else "no length"
        context.problems.error(
            "scene_length",
            f"{where} has {given}",
            hint="give exactly one of beats, bars or seconds",
        )
        return None
    if scene.seconds is not None:
        return t + scene.seconds
    grid = context.grid
    beats = scene.beats if scene.beats is not None else (scene.bars or 0) * grid.beats_per_bar
    return grid.after_beats(t, beats)


def _title_card(scene: Scene, slot: Slot, context: SceneContext) -> TimelineScene | None:
    assert isinstance(scene, TitleCardScene)
    lines = _accented(scene, [scene.headline], "the headline", context)
    if lines is None:
        return None
    return TimelineTitleCard(
        type="title_card",
        id=scene.id,
        start=slot.start,
        end=slot.end,
        step=scene.step,
        headline=lines[0],
        subline=scene.subline,
    )


def _kinetic_text(scene: Scene, slot: Slot, context: SceneContext) -> TimelineScene | None:
    assert isinstance(scene, KineticTextScene)
    lines = _accented(scene, scene.lines, "any line", context)
    if lines is None:
        return None
    frames = slot.end - slot.start
    cuts = [slot.start + frames * i // len(lines) for i in range(len(lines) + 1)]
    return TimelineKineticText(
        type="kinetic_text",
        id=scene.id,
        start=slot.start,
        end=slot.end,
        lines=[
            TimelineKineticLine(start=a, end=b, words=words)
            for a, b, words in zip(cuts, cuts[1:], lines, strict=False)
        ],
    )


def _proof(scene: Scene, slot: Slot, context: SceneContext) -> TimelineScene | None:
    assert isinstance(scene, ProofScene)
    image = context.clips.get(scene.image)
    if image is None or image.clip.role != "image":
        images = [c for c, a in context.clips.items() if a.clip.role == "image"]
        context.problems.error(
            "unknown_image",
            f"scene {scene.id}: {scene.image} is not an image",
            hint=f"images: {', '.join(images) or 'none; add one to raw/ and run ingest'}",
        )
        return None
    lines = _accented(scene, [scene.headline or ""], "the headline", context)
    if lines is None:
        return None
    return TimelineProof(
        type="proof",
        id=scene.id,
        start=slot.start,
        end=slot.end,
        src=image.clip.mezzanine or image.clip.source,
        width=image.clip.width,
        height=image.clip.height,
        headline=lines[0],
        subline=scene.subline,
        badge=scene.badge,
    )


def _logo_outro(scene: Scene, slot: Slot, context: SceneContext) -> TimelineScene | None:
    assert isinstance(scene, LogoOutroScene)
    brand = context.brand
    needed = {"wordmark": brand.wordmark is not None}
    if scene.mascot:
        needed["mascot"] = brand.mascot is not None
    for key in (k for k, loaded in needed.items() if not loaded):
        context.problems.error(
            "missing_brand_asset",
            f"scene {scene.id}: [brand] {key} {brand.broken.get(key, 'is not set')}",
            hint=_BRAND_HINTS[key],
        )
    lines = _accented(scene, [scene.tagline or ""], "the tagline", context)
    if lines is None or not all(needed.values()):
        return None
    return TimelineLogoOutro(
        type="logo_outro",
        id=scene.id,
        start=slot.start,
        end=slot.end,
        tagline=lines[0],
        url=scene.url,
        mascot=scene.mascot,
    )


_BRAND_HINTS = {
    "wordmark": f'set wordmark = "library/brand/wordmark.svg" under [brand] in {WORKSPACE_FILE} '
    "or project.toml, an image path relative to the workspace",
    "mascot": f"set mascot = {{ sheet = ..., timings = ... }} under [brand] in {WORKSPACE_FILE} "
    'or project.toml (a sprite sheet and its frame-timing JSON), or "mascot": false on the scene',
}


def _accented(
    scene: KineticTextScene | LogoOutroScene | ProofScene | TitleCardScene,
    texts: Sequence[str],
    where: str,
    context: SceneContext,
) -> list[list[TimelineHeadlineWord]] | None:
    """Each text split into words, marked where the scene's `accent` names them."""
    split = [text.split() for text in texts]
    accents = {_bare(a) for a in scene.accent}
    missing = sorted(accents - {_bare(w) for words in split for w in words})
    if missing:
        context.problems.error(
            "unknown_accent",
            f"scene {scene.id}: accent {', '.join(missing)} is not a word of {where}",
            hint=f"list words exactly as {where} spells them",
        )
        return None
    return [
        [TimelineHeadlineWord(text=w, accent=_bare(w) in accents) for w in words] for words in split
    ]


def _bare(word: str) -> str:
    return word.strip(string.punctuation + "\u201c\u201d\u2018\u2019«»…").casefold()


def _footage(scene: Scene, slot: Slot, context: SceneContext) -> TimelineScene | None:
    assert isinstance(scene, FootageScene)
    # Resolved without errors already; a second pass would repeat its warnings.
    span = _footage_span(scene, slot.start_s, context, Problems())
    assert span is not None
    analysis = context.clips[scene.clip]
    info = analysis.clip
    assert info.mezzanine is not None and info.width is not None and info.height is not None
    src_in, src_out = span
    seconds = (slot.end - slot.start) / context.fps
    return TimelineFootage(
        type="footage",
        id=scene.id,
        start=slot.start,
        end=slot.end,
        clip=scene.clip,
        src=info.mezzanine,
        width=info.width,
        height=info.height,
        src_in_s=round(src_in, 6),
        src_out_s=round(src_out, 6),
        rate=round((src_out - src_in) / seconds, 6),
        device_frame=scene.device_frame,
        address=scene.address,
    )


def _footage_span(
    scene: FootageScene, t: float, context: SceneContext, problems: Problems
) -> tuple[float, float] | None:
    """Source seconds from `from` to `to`, or None after recording why not."""
    where = f"scene {scene.id}"
    analysis = context.clips.get(scene.clip)
    if (
        analysis is None
        or analysis.clip.role not in FOOTAGE_ROLES
        or analysis.clip.mezzanine is None
    ):
        recordings = [c for c, a in context.clips.items() if a.clip.role in FOOTAGE_ROLES]
        problems.error(
            "unknown_clip",
            f"{where}: {scene.clip} is not a screen recording",
            hint=f"screen recordings: {', '.join(recordings) or 'none; run ingest'}",
        )
        return None
    start = _point(scene.from_, "from", scene, analysis, t, context, problems)
    end = _point(scene.to, "to", scene, analysis, t, context, problems)
    if start is None or end is None:
        return None
    if not analysis.markers:
        problems.warn(
            "seconds_addressed",
            f"{where}: {scene.clip} has no markers, so from and to are source seconds",
            hint="record with `record web`, or add a markers sidecar, to address it by marker",
        )
    if end <= start:
        problems.error(
            "reversed_range",
            f"{where}: to ({end:.3f} s) is not after from ({start:.3f} s)",
            hint="swap from and to, or pick a later marker for to",
        )
        return None
    duration = analysis.clip.duration_s
    if start < 0 or end > duration + 1e-6:
        problems.error(
            "outside_clip",
            f"{where}: {start:.3f}-{end:.3f} s is outside {scene.clip} (0-{duration:.3f} s)",
            hint="shorten the offset, or use a marker nearer the middle of the recording",
        )
        return None
    return start, end


def _point(
    point: FootagePoint,
    field: str,
    scene: FootageScene,
    analysis: ClipAnalysis,
    t: float,
    context: SceneContext,
    problems: Problems,
) -> float | None:
    where = f"scene {scene.id} {field}"
    if isinstance(point, float | int):
        if analysis.markers:
            problems.error(
                "seconds_on_marked_clip",
                f"{where}: {point} is in source seconds, but {scene.clip} has markers",
                hint=f"point at a marker, with offset_s to nudge it: {_marker_list(analysis)}",
            )
            return None
        return float(point)
    ref = point if isinstance(point, str) else point.marker
    match = _MARKER.match(ref)
    if match is None:
        problems.error(
            "bad_marker",
            f"{where}: '{ref}' is not a marker ID such as {scene.clip}.m.start",
            hint=_MARKERS_HINT,
        )
        return None
    if match["clip"] != scene.clip:
        problems.error(
            "cross_clip",
            f"{where}: {ref} is a marker of {match['clip']}, but the scene plays {scene.clip}",
            hint="set clip to the marker's recording, or pick one of its own markers",
        )
        return None
    marker = next((m for m in analysis.markers if m.name == match["name"]), None)
    if marker is None:
        problems.error(
            "unknown_marker",
            f"{where}: {ref} does not exist",
            hint=f"{scene.clip} has {_marker_list(analysis)}",
        )
        return None
    return marker.t + _offset(point, t, context)


def _offset(point: FootagePoint, t: float, context: SceneContext) -> float:
    if not isinstance(point, MarkerPoint):
        return 0.0
    beats = (point.offset_beats or 0.0) * context.grid.beat_s_at(t)
    return (point.offset_s or 0.0) + beats


def _marker_list(analysis: ClipAnalysis) -> str:
    names = [f"{analysis.clip.id}.m.{m.name}" for m in analysis.markers]
    if not names:
        return "no markers"
    more = len(names) - _MARKERS_SHOWN
    return ", ".join(names[:_MARKERS_SHOWN]) + (f" and {more} more" if more > 0 else "")


_SCENES: dict[str, Callable[[Scene, Slot, SceneContext], TimelineScene | None]] = {
    "title_card": _title_card,
    "footage": _footage,
    "kinetic_text": _kinetic_text,
    "proof": _proof,
    "logo_outro": _logo_outro,
}
