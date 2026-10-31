"""Product EDLs resolved to a timeline of scenes (ADR 0004), footage addressed by marker (ADR 0005).

Scenes sit back to back on the beat grid. Each type's resolver in `_SCENES` returns its
timeline scene, or None after recording its problems.
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
    CameraMove,
    CaptionPillEvent,
    FlashEvent,
    FootagePoint,
    FootageScene,
    HighlightEvent,
    KineticTextScene,
    LogoOutroScene,
    MarkerPoint,
    MaskEvent,
    ProductEdl,
    ProofScene,
    Rect,
    Scene,
    TimelineCameraKey,
    TimelineCaptionPill,
    TimelineEvent,
    TimelineFlash,
    TimelineFootage,
    TimelineGifMascot,
    TimelineHeadlineWord,
    TimelineHighlight,
    TimelineKineticLine,
    TimelineKineticText,
    TimelineLogoOutro,
    TimelineMascot,
    TimelineMask,
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
_ELEMENT = re.compile(r"^(?P<clip>[a-z]+\d+)\.e\.(?P<name>[A-Za-z0-9_][A-Za-z0-9_-]*)$")
_ELEMENTS_SHOWN = 8
# The device frame's room on the 1920x1080 canvas, the same for browser and terminal frames,
# as in renderer/src/lib/deviceFrame.ts.
_ROOM = (1600, 900)
# Past this many output pixels per recorded pixel, recorded text goes soft.
_MAX_MAGNIFICATION = 2.0
# A move without a zoom frames its target to fill this much of the footage.
_FILL = 0.7
_MARKERS_SHOWN = 8
_FLASH_FRAMES = 5
# A flash this bright reads on light footage; dark terminal footage takes a softer one.
_FLASH_STRENGTH = 0.35
_FLASH_STRENGTH_ON = {"terminal": 0.12}
# Events a scene has at most one of: both sit on the scene as a whole.
_ONCE_PER_SCENE = ("caption_pill", "flash")
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
    mascot: TimelineMascot | TimelineGifMascot | None = None
    # Why a configured asset did not load, by its key: "names x.svg, which does not exist".
    broken: Mapping[str, str] = field(default_factory=lambda: dict[str, str]())


@dataclass(frozen=True)
class SceneContext:
    clips: dict[str, ClipAnalysis]
    grid: BeatGrid
    fps: int
    problems: Problems
    brand: BrandAssets
    title: str


@dataclass(frozen=True)
class ProductScenes:
    scenes: list[TimelineScene]
    duration_frames: int
    events: list[TimelineEvent]


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
    context = SceneContext({c.clip.id: c for c in clips}, grid, fps, problems, brand, edl.title)
    _check_formats(edl, problems)
    seen: set[str] = set()
    scenes: list[TimelineScene] = []
    events: list[TimelineEvent] = []
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
        slot = Slot(t, frame, end)
        resolved = _SCENES[scene.type](scene, slot, context)
        if resolved is not None:
            scenes.append(resolved)
        events.extend(_scene_events(scene, slot, span, context))
        t, frame = end_s, end
    events.sort(key=lambda e: e.start)
    return ProductScenes(scenes, frame, events)


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
    # Without a wordmark the title is set in type; one that is configured must load.
    reasons = dict(brand.broken)
    if brand.wordmark is None and "wordmark" not in reasons and not context.title.strip():
        reasons["wordmark"] = "is not set and the EDL has no title to set in its place"
    needed = {"wordmark": "wordmark" not in reasons}
    if scene.mascot:
        needed["mascot"] = brand.mascot is not None
    for key in (k for k, loaded in needed.items() if not loaded):
        context.problems.error(
            "missing_brand_asset",
            f"scene {scene.id}: [brand] {key} {reasons.get(key, 'is not set')}",
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
        name=context.title.strip(),
    )


_BRAND_HINTS = {
    "wordmark": f'set wordmark = "library/brand/wordmark.svg" under [brand] in {WORKSPACE_FILE} '
    'or project.toml, an image path relative to the workspace, or "title" in the EDL to set it '
    "in type",
    "mascot": f"set mascot = {{ sheet = ..., timings = ... }} under [brand] in {WORKSPACE_FILE} "
    'or project.toml (a sprite sheet and its frame-timing JSON, or gif = ...), or "mascot": false '
    "on the scene",
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
    camera = _camera(scene, slot, span, analysis, context)
    if camera is None:
        return None
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
        camera=camera,
    )


def _camera(
    scene: FootageScene,
    slot: Slot,
    span: tuple[float, float],
    analysis: ClipAnalysis,
    context: SceneContext,
) -> list[TimelineCameraKey] | None:
    """The scene's moves as keyframes in frame order, or None after recording why not."""
    keys = [
        _move(i, move, scene, slot, span, analysis, context) for i, move in enumerate(scene.camera)
    ]
    resolved = [k for k in keys if k is not None]
    if len(resolved) < len(keys):
        return None
    return sorted(resolved, key=lambda k: k.frame)


def _move(
    index: int,
    move: CameraMove,
    scene: FootageScene,
    slot: Slot,
    span: tuple[float, float],
    analysis: ClipAnalysis,
    context: SceneContext,
) -> TimelineCameraKey | None:
    field = f"camera[{index}]"
    where = f"scene {scene.id} {field}"
    problems = context.problems
    at = _point(move.at, f"{field}.at", scene, analysis, slot.start_s, context, problems)
    if at is None:
        return None
    src_in, src_out = span
    if not src_in - 1e-6 <= at < src_out:
        problems.error(
            "move_outside_scene",
            f"{where}: at ({at:.3f} s) is outside the scene's footage "
            f"({src_in:.3f}-{src_out:.3f} s)",
            hint="pick a marker between the scene's from and to, or nudge it with offset_s",
        )
        return None
    box = _target_box(move.target, f"{where} target", at, scene, analysis, problems)
    if box is None:
        return None
    width, height = analysis.clip.width or 0, analysis.clip.height or 0
    zoom = _zoom(move.zoom, box, width, height, where, problems)
    if zoom is None:
        return None
    if move.zoom is None and move.target != "full" and _fill(box, width, height) < 1.0:
        problems.warn(
            "target_too_wide",
            f"{where}: the target fills more than {_FILL:.0%} of the {width}x{height} footage, "
            "so the move stays at 1x and only recentres",
            hint='target a smaller element or box, or "full" to show the whole frame',
        )
    return TimelineCameraKey(
        frame=_frame_at(at, span, slot),
        cx=round(box.x + box.w / 2, 2),
        cy=round(box.y + box.h / 2, 2),
        zoom=round(zoom, 6),
        ease=move.ease,
    )


def _target_box(
    target: str | Rect,
    where: str,
    at: float,
    scene: FootageScene,
    analysis: ClipAnalysis,
    problems: Problems,
) -> Rect | None:
    """The target as a box in footage pixels, or None after recording why not.

    An element is boxed where it was captured at the marker nearest `at`.
    """
    width, height = analysis.clip.width or 0, analysis.clip.height or 0
    if target == "full":
        return Rect(x=0, y=0, w=width, h=height)
    if isinstance(target, str):
        box = _element_box(target, where, at, scene, analysis, problems)
        if box is None:
            return None
    else:
        box = target
    slack = 0.5
    if (
        box.x < -slack
        or box.y < -slack
        or box.x + box.w > width + slack
        or box.y + box.h > height + slack
    ):
        problems.error(
            "target_outside",
            f"{where}: {round(box.x)},{round(box.y)} {round(box.w)}x{round(box.h)} is not "
            f"inside the {width}x{height} footage",
            hint="target an element captured while it was on screen, or a box inside the footage",
        )
        return None
    return box


def _element_box(
    ref: str,
    where: str,
    at: float,
    scene: FootageScene,
    analysis: ClipAnalysis,
    problems: Problems,
) -> Rect | None:
    match = _ELEMENT.match(ref)
    if match is None:
        problems.error(
            "bad_target",
            f"{where}: '{ref}' is not an element ID such as {scene.clip}.e.hook, or full",
            hint="elements are listed after each marker in analysis/packed.md; a box is "
            '{ "x": 0, "y": 0, "w": 800, "h": 450 } in footage pixels',
        )
        return None
    if match["clip"] != scene.clip:
        problems.error(
            "cross_clip",
            f"{where}: {ref} is an element of {match['clip']}, but the scene plays {scene.clip}",
            hint="target one of the scene's own elements",
        )
        return None
    captured = [(m.t, e) for m in analysis.markers for e in m.elements if e.name == match["name"]]
    if not captured:
        problems.error(
            "unknown_element",
            f"{where}: {ref} was not captured at any marker",
            hint=f"{scene.clip} has {_element_list(analysis)}",
        )
        return None
    _, element = min(captured, key=lambda c: (abs(c[0] - at), c[0]))
    return Rect(x=element.x, y=element.y, w=element.w, h=element.h)


def _zoom(
    zoom: float | None, box: Rect, width: int, height: int, where: str, problems: Problems
) -> float | None:
    """The given zoom, or one that fills 70% of the footage with the box, within the limit."""
    limit = _max_zoom(width, height)
    if zoom is None:
        return min(limit, max(1.0, _fill(box, width, height)))
    if zoom > limit + 1e-9:
        problems.error(
            "zoom_too_far",
            f"{where}: zoom {zoom:g} is past {limit:.2f}x on {width}x{height} footage",
            hint=f"zoom at most {limit:.2f}, past which recorded text goes soft, or leave zoom "
            "out to frame the target",
        )
        return None
    return zoom


def _fill(box: Rect, width: int, height: int) -> float:
    """The zoom at which the box fills 70% of the footage."""
    return _FILL * min(width / box.w, height / box.h)


def _max_zoom(width: int, height: int) -> float:
    """2x on footage shown 1:1 in the device frame (1600x900); more on larger, less on smaller."""
    rest = min(_ROOM[0] / width, _ROOM[1] / height)
    return max(1.0, _MAX_MAGNIFICATION / rest)


def _element_list(analysis: ClipAnalysis) -> str:
    names = sorted({f"{analysis.clip.id}.e.{e.name}" for m in analysis.markers for e in m.elements})
    if not names:
        return "no elements"
    more = len(names) - _ELEMENTS_SHOWN
    return ", ".join(names[:_ELEMENTS_SHOWN]) + (f" and {more} more" if more > 0 else "")


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


def _frame_at(t: float, span: tuple[float, float], slot: Slot) -> int:
    """The output frame showing source second `t` of a footage scene."""
    src_in, src_out = span
    return slot.start + round((t - src_in) / (src_out - src_in) * (slot.end - slot.start))


def _scene_events(
    scene: Scene, slot: Slot, span: tuple[float, float] | None, context: SceneContext
) -> list[TimelineEvent]:
    """The scene's events in output frames. Errors go to `context.problems`."""
    resolved: list[TimelineEvent] = []
    seen: set[str] = set()
    for index, event in enumerate(scene.events):
        field = f"events[{index}]"
        if isinstance(event, CaptionPillEvent | FlashEvent):
            if event.type in seen:
                context.problems.error(
                    "duplicate_event",
                    f"scene {scene.id} {field}: the scene already has a {event.type}",
                    hint=f"keep one {', one '.join(_ONCE_PER_SCENE)} per scene, or split the scene",
                )
                continue
            seen.add(event.type)
            resolved.append(_whole_scene_event(event, scene, slot))
        elif not isinstance(scene, FootageScene):
            context.problems.error(
                "event_needs_footage",
                f"scene {scene.id} {field}: a {event.type} needs a footage scene, not {scene.type}",
                hint="move it to the footage scene whose recording it points at",
            )
        elif span is not None:
            box = _footage_event(event, field, scene, slot, span, context)
            if box is not None:
                resolved.append(box)
    return resolved


def _whole_scene_event(
    event: CaptionPillEvent | FlashEvent, scene: Scene, slot: Slot
) -> TimelineEvent:
    if isinstance(event, CaptionPillEvent):
        return TimelineCaptionPill(
            type="caption_pill", scene=scene.id, start=slot.start, end=slot.end, text=event.text
        )
    frame = getattr(scene, "device_frame", None)
    strength = event.strength or _FLASH_STRENGTH_ON.get(str(frame), _FLASH_STRENGTH)
    return TimelineFlash(
        type="flash",
        scene=scene.id,
        start=slot.start,
        end=min(slot.end, slot.start + _FLASH_FRAMES),
        strength=strength,
    )


def _footage_event(
    event: HighlightEvent | MaskEvent,
    field: str,
    scene: FootageScene,
    slot: Slot,
    span: tuple[float, float],
    context: SceneContext,
) -> TimelineEvent | None:
    """A highlight or mask in footage pixels over its frames, or None after recording why not."""
    problems = context.problems
    analysis = context.clips[scene.clip]
    src_in, src_out = span
    where = f"scene {scene.id} {field}"

    def point(value: FootagePoint | None, name: str, default: float) -> float | None:
        if value is None:
            return default
        return _point(value, f"{field}.{name}", scene, analysis, slot.start_s, context, problems)

    start, end = point(event.start, "start", src_in), point(event.end, "end", src_out)
    if start is None or end is None:
        return None
    if end <= start:
        problems.error(
            "reversed_event",
            f"{where}: end ({end:.3f} s) is not after start ({start:.3f} s)",
            hint="swap start and end, or pick a later marker for end",
        )
        return None
    if start < src_in - 1e-6 or end > src_out + 1e-6:
        problems.error(
            "event_outside_scene",
            f"{where}: {start:.3f}-{end:.3f} s is outside the scene's footage "
            f"({src_in:.3f}-{src_out:.3f} s)",
            hint="pick markers between the scene's from and to, or leave start and end out to "
            "cover the whole scene",
        )
        return None
    box = _target_box(event.target, f"{where} target", start, scene, analysis, problems)
    if box is None:
        return None
    first = _frame_at(start, span, slot)
    target = event.target
    fields = {
        "scene": scene.id,
        "clip": scene.clip,
        "start": first,
        "end": max(first + 1, _frame_at(end, span, slot)),
        "src_start_s": round(start, 6),
        "src_end_s": round(end, 6),
        "element": target if isinstance(target, str) and target != "full" else None,
        **box.model_dump(),
    }
    if isinstance(event, HighlightEvent):
        return TimelineHighlight.model_validate(
            {**fields, "type": "highlight", "label": event.label}
        )
    return TimelineMask.model_validate({**fields, "type": "mask", "color": event.color})


_SCENES: dict[str, Callable[[Scene, Slot, SceneContext], TimelineScene | None]] = {
    "title_card": _title_card,
    "footage": _footage,
    "kinetic_text": _kinetic_text,
    "proof": _proof,
    "logo_outro": _logo_outro,
}
