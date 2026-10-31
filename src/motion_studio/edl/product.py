"""Product EDLs resolved to a timeline of scenes (ADR 0004), footage addressed by marker (ADR 0005).

Scenes follow each other on the beat grid with no gap. Each scene type has one resolver in
`_SCENES`, which returns the timeline scene for the frames it was given, or None after recording
its problems.
"""

import re
import string
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from motion_studio.analysis import ClipAnalysis
from motion_studio.config import Config
from motion_studio.edl.grid import BeatGrid
from motion_studio.edl.issues import Problems
from motion_studio.edl.models import (
    CameraMove,
    FootagePoint,
    FootageScene,
    MarkerPoint,
    ProductEdl,
    Rect,
    Scene,
    TimelineCameraKey,
    TimelineFootage,
    TimelineHeadlineWord,
    TimelineScene,
    TimelineTitleCard,
    TitleCardScene,
)

PRODUCT_FORMATS = ("16x9",)
# Clip roles a footage scene can play.
FOOTAGE_ROLES = ("screen", "broll")
_MARKER = re.compile(r"^(?P<clip>[a-z]+\d+)\.m\.(?P<name>[A-Za-z0-9_][A-Za-z0-9_-]*)$")
_ELEMENT = re.compile(r"^(?P<clip>[a-z]+\d+)\.e\.(?P<name>[A-Za-z0-9_][A-Za-z0-9_-]*)$")
_ELEMENTS_SHOWN = 8
# The browser frame's room on the 1920x1080 canvas, as in renderer/src/lib/deviceFrame.ts.
_ROOM = (1600, 900)
# Past this many output pixels per recorded pixel, recorded text goes soft.
_MAX_MAGNIFICATION = 2.0
# A move without a zoom frames its target to fill this much of the footage.
_FILL = 0.7
_MARKERS_SHOWN = 8
_MARKERS_HINT = "markers are listed under each screen recording in analysis/packed.md"


@dataclass(frozen=True)
class Slot:
    """Where a scene sits: output seconds on the grid, and its frames."""

    start_s: float
    start: int
    end: int


@dataclass(frozen=True)
class SceneContext:
    clips: dict[str, ClipAnalysis]
    grid: BeatGrid
    fps: int
    problems: Problems


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
) -> ProductScenes:
    """Every scene on the grid. Errors go to `problems`; the caller raises them."""
    fps = config.defaults.fps
    context = SceneContext({c.clip.id: c for c in clips}, grid, fps, problems)
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
    words = scene.headline.split()
    accents = {_bare(a) for a in scene.accent}
    missing = sorted(accents - {_bare(w) for w in words})
    if missing:
        context.problems.error(
            "unknown_accent",
            f"scene {scene.id}: accent {', '.join(missing)} is not a word of the headline",
            hint="list words exactly as the headline spells them",
        )
        return None
    return TimelineTitleCard(
        type="title_card",
        id=scene.id,
        start=slot.start,
        end=slot.end,
        step=scene.step,
        headline=[TimelineHeadlineWord(text=w, accent=_bare(w) in accents) for w in words],
        subline=scene.subline,
    )


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
    frame = slot.start + round((at - src_in) / (src_out - src_in) * (slot.end - slot.start))
    return TimelineCameraKey(
        frame=frame,
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
        return min(limit, max(1.0, _FILL * min(width / box.w, height / box.h)))
    if zoom > limit + 1e-9:
        problems.error(
            "zoom_too_far",
            f"{where}: zoom {zoom:g} is past {limit:.2f}x on {width}x{height} footage",
            hint=f"zoom at most {limit:.2f}, past which recorded text goes soft, or leave zoom "
            "out to frame the target",
        )
        return None
    return zoom


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


_SCENES: dict[str, Callable[[Scene, Slot, SceneContext], TimelineScene | None]] = {
    "title_card": _title_card,
    "footage": _footage,
}
