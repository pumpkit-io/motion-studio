"""What `check` reads off a product timeline: masked regions, the cursor over highlight targets,
the scenes that hold still on purpose, and the scenes to shorten when the video runs long."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from motion_studio import APP_NAME
from motion_studio.analysis.models import CursorSample
from motion_studio.check.report import Finding
from motion_studio.edl import Timeline
from motion_studio.edl.models import TimelineFootage, TimelineHighlight, TimelineMask


@dataclass(frozen=True)
class MaskedRegion:
    scene: str
    clip: str
    element: str | None
    box: tuple[float, float, float, float]
    start: int
    end: int
    fps: int

    @property
    def look_at(self) -> float:
        """Output seconds of the region's middle frame, the moment to inspect with `look --at`."""
        return round((self.start + (self.end - self.start) // 2) / self.fps, 2)

    def line(self, slug: str) -> str:
        x, y, w, h = self.box
        what = self.element or f"box {x:g},{y:g} {w:g}x{h:g}"
        return (
            f"{self.scene}: {what} of {self.clip}, frames {self.start}-{self.end - 1} "
            f"({self.start / self.fps:.2f}-{self.end / self.fps:.2f} s); "
            f"see it with `{APP_NAME} look {slug} --at {self.look_at:g}`"
        )

    def to_json(self) -> dict[str, Any]:
        x, y, w, h = self.box
        return {
            "scene": self.scene,
            "clip": self.clip,
            "element": self.element,
            "x": x,
            "y": y,
            "w": w,
            "h": h,
            "start": self.start,
            "end": self.end,
            "start_s": round(self.start / self.fps, 3),
            "end_s": round(self.end / self.fps, 3),
            "look_at_s": self.look_at,
        }


def masked_regions(timeline: Timeline) -> list[MaskedRegion]:
    return [
        MaskedRegion(e.scene, e.clip, e.element, (e.x, e.y, e.w, e.h), e.start, e.end, timeline.fps)
        for e in timeline.events
        if isinstance(e, TimelineMask)
    ]


def still_scenes(timeline: Timeline) -> list[tuple[float, float]]:
    """Output seconds of every scene that is not footage: cards, proofs and the outro may hold
    still, and on a near-black brand primary, or the outro's fade, read as black frames."""
    fps = timeline.fps
    return [
        (s.start / fps, s.end / fps) for s in timeline.scenes if not isinstance(s, TimelineFootage)
    ]


def cursor_findings(
    timeline: Timeline, cursors: Mapping[str, Sequence[CursorSample]], slug: str
) -> list[Finding]:
    """A warning for each highlight whose target the recorded cursor sits on while it shows.

    Terminal footage has no cursor track, so its scenes are skipped.
    """
    scenes = {s.id: s for s in timeline.scenes if isinstance(s, TimelineFootage)}
    found: list[Finding] = []
    for event in timeline.events:
        if not isinstance(event, TimelineHighlight):
            continue
        scene = scenes.get(event.scene)
        if scene is None or scene.device_frame == "terminal":
            continue
        sample = _covering(cursors.get(event.clip, ()), event)
        if sample is None:
            continue
        src_t = max(sample.t, event.src_start_s)
        frame = scene.start + round((src_t - scene.src_in_s) / scene.rate * timeline.fps)
        out_t = round(min(max(frame, event.start), event.end - 1) / timeline.fps, 2)
        target = event.element or f"box {event.x:g},{event.y:g} {event.w:g}x{event.h:g}"
        found.append(
            Finding(
                "warning",
                "cursor_over_target",
                f"the cursor covers highlight target {target} in scene {event.scene} "
                f"at {out_t:.2f} s ({src_t:.2f} s into {event.clip})",
                "park the cursor off the target in the recording script (`r.park(...)`) and "
                "record a new take, or start the highlight after the cursor leaves; "
                f"see it with `{APP_NAME} look {slug} --at {out_t:g}`",
            )
        )
    return found


def _covering(track: Sequence[CursorSample], event: TimelineHighlight) -> CursorSample | None:
    """The first sample on the target while the highlight shows.

    The recorder samples only when the cursor moves, so the last sample before the highlight
    starts is where the cursor sits as it draws in.
    """
    held = [s for s in track if s.t <= event.src_start_s][-1:]
    during = [s for s in track if event.src_start_s < s.t < event.src_end_s]
    for sample in held + during:
        inside_x = event.x <= sample.x <= event.x + event.w
        if inside_x and event.y <= sample.y <= event.y + event.h:
            return sample
    return None


def longest_middle_scenes(timeline: Timeline, count: int = 3) -> str:
    """The longest scenes between the first and the last, which the cut should come from."""
    scenes = timeline.scenes
    middle = scenes[1:-1] or scenes
    ranked = sorted(middle, key=lambda s: s.start - s.end)[:count]
    return ", ".join(f"{s.id} ({(s.end - s.start) / timeline.fps:.1f} s)" for s in ranked)
