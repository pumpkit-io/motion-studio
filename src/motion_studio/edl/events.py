"""Steps 9-10 of guide §6.5: events to output frames, overlap checks and beat snapping."""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from motion_studio.analysis import ClipAnalysis
from motion_studio.edl.issues import Problems
from motion_studio.edl.models import (
    BrollEvent,
    EmphasisEvent,
    Event,
    ImageEvent,
    PushEvent,
    TimelineBroll,
    TimelineEvent,
    TimelineImage,
    TimelinePush,
    TimelineTitle,
    TimelineWord,
    TimelineZoom,
    TitleEvent,
    ZoomEvent,
)
from motion_studio.edl.refs import RefIndex, parse_ref

# B-roll and image starts move to a beat at most this far away. Speech cuts never move.
BEAT_SNAP_S = 0.080

Edge = Literal["start", "end"]


@dataclass
class OutputMap:
    """Where the kept words and segments landed in the output."""

    fps: int
    words: Mapping[str, TimelineWord]
    kept: Mapping[str, Sequence[int]]
    segments: Mapping[str, tuple[int, int] | None]


@dataclass
class ResolvedEvents:
    events: list[TimelineEvent]
    emphasis: set[str]


def resolve_events(
    events: Sequence[Event],
    index: RefIndex,
    out: OutputMap,
    beats: Sequence[float] | None,
    problems: Problems,
) -> ResolvedEvents:
    resolver = _Resolver(index, out, beats or (), problems)
    placed: list[tuple[int, TimelineEvent]] = []
    emphasis: set[str] = set()
    for n, event in enumerate(events, start=1):
        where = f"event {n} ({event.type})"
        if isinstance(event, EmphasisEvent):
            emphasis |= resolver.emphasis(event, where)
            continue
        resolved = resolver.event(event, where)
        if resolved is not None:
            placed.append((n, resolved))
    _check_overlaps(placed, out.fps, problems)
    placed.sort(key=lambda item: item[1].start)
    return ResolvedEvents([e for _, e in placed], emphasis)


class _Resolver:
    def __init__(
        self, index: RefIndex, out: OutputMap, beats: Sequence[float], problems: Problems
    ) -> None:
        self.index = index
        self.out = out
        self.beats = beats
        self.problems = problems

    def event(self, event: Event, where: str) -> TimelineEvent | None:
        match event:
            case ZoomEvent():
                hold = (
                    ("at", event.at)
                    if event.hold_until is None
                    else ("hold_until", event.hold_until)
                )
                span = self._span(where, ("at", event.at), hold)
                if span is None:
                    return None
                return TimelineZoom(
                    type="zoom", start=span[0], end=span[1], scale=event.scale, ease=event.ease
                )
            case PushEvent():
                span = self._segment(event.from_, where)
                if span is None:
                    return None
                return TimelinePush(type="push", start=span[0], end=span[1], scale=event.scale)
            case BrollEvent():
                asset = self._asset(event.asset, "broll", where)
                span = self._span(where, ("start", event.start), ("end", event.end))
                if asset is None or span is None:
                    return None
                if event.asset_in_s >= asset.clip.duration_s:
                    self.problems.error(
                        "bad_asset",
                        f"{where}: asset_in_s {event.asset_in_s:.2f} is past the end of "
                        f"{event.asset} ({asset.clip.duration_s:.2f} s)",
                    )
                    return None
                start, end = self._snap(span[0]), span[1]
                end = self._fit(asset, event.asset_in_s, start, end, where)
                return TimelineBroll(
                    type="broll",
                    asset=event.asset,
                    src=_src(asset),
                    start=start,
                    end=end,
                    asset_in_s=event.asset_in_s,
                    mode=event.mode,
                )
            case ImageEvent():
                asset = self._asset(event.asset, "image", where)
                span = self._span(where, ("start", event.start), ("end", event.end))
                if asset is None or span is None:
                    return None
                return TimelineImage(
                    type="image",
                    asset=event.asset,
                    src=_src(asset),
                    start=self._snap(span[0]),
                    end=span[1],
                    mode=event.mode,
                    motion=event.motion,
                )
            case TitleEvent():
                span = self._span(where, ("start", event.start), ("end", event.end))
                if span is None:
                    return None
                return TimelineTitle(type="title", text=event.text, start=span[0], end=span[1])
            case EmphasisEvent():  # pragma: no cover - handled by emphasis()
                return None

    def emphasis(self, event: EmphasisEvent, where: str) -> set[str]:
        found: set[str] = set()
        for ref in event.words:
            parsed = parse_ref(ref)
            if parsed is not None and parsed.kind == "s":
                self.problems.error("bad_ref", f"{where}: {ref} is an utterance; list its words")
                continue
            target = self.index.word_index(ref, where, self.problems)
            if target is None:
                continue
            if ref in self.out.words:
                found.add(ref)
            else:
                self._dropped(f"{where}: {ref} is cut from the edit", target)
        return found

    def _span(
        self, where: str, start: tuple[str, str], end: tuple[str, str]
    ) -> tuple[int, int] | None:
        start_f = self._anchor(start[1], "start", f"{where}: {start[0]}", where)
        end_f = self._anchor(end[1], "end", f"{where}: {end[0]}", where)
        if start_f is None or end_f is None:
            return None
        if end_f <= start_f:
            self.problems.error(
                "event_range",
                f"{where}: {end[0]} {end[1]} comes before {start[0]} {start[1]}",
                hint="swap the anchors, or check the segment order",
            )
            return None
        return start_f, end_f

    def _anchor(self, ref: str, edge: Edge, label: str, where: str) -> int | None:
        if ref in self.out.segments:
            span = self.out.segments[ref]
            if span is None:
                self.problems.error("dropped_anchor", f"{label} {ref} keeps no words")
                return None
            return span[0] if edge == "start" else span[1]
        parsed = parse_ref(ref)
        if parsed is None:
            self.problems.error(
                "bad_ref", f"{label} '{ref}' is not a segment, word or utterance ID"
            )
            return None
        target = self.index.word_index(
            ref, where, self.problems, end="first" if edge == "start" else "last"
        )
        if target is None:
            return None
        clip_id = target[0]
        if parsed.kind == "w":
            word = self.out.words.get(ref)
            if word is None:
                self._dropped(f"{label} {ref} is cut from the edit", target)
                return None
        else:
            utterance = self.index.clips[clip_id].utterances[parsed.index]
            first, last = _word_index(utterance.first_word), _word_index(utterance.last_word)
            inside = [j for j in self.out.kept.get(clip_id, ()) if first <= j <= last]
            if not inside:
                self._dropped(f"{label} {ref} has no word in the edit", target)
                return None
            chosen = inside[0] if edge == "start" else inside[-1]
            word = self.out.words[f"{clip_id}.w{chosen}"]
        return _frame(word.start_ms if edge == "start" else word.end_ms, self.out.fps)

    def _segment(self, ref: str, where: str) -> tuple[int, int] | None:
        if ref not in self.out.segments and parse_ref(ref) is not None:
            self.problems.error("bad_ref", f"{where}: from must be a segment ID, not {ref}")
            return None
        start = self._anchor(ref, "start", f"{where}: from", where)
        end = self._anchor(ref, "end", f"{where}: from", where)
        if start is None or end is None:
            return None
        return start, end

    def _dropped(self, message: str, target: tuple[str, int]) -> None:
        clip_id, i = target
        kept = self.out.kept.get(clip_id, ())
        if not kept:
            self.problems.error("dropped_anchor", f"{message}; no word of {clip_id} is kept")
            return
        nearest = min(kept, key=lambda j: (abs(j - i), j))
        self.problems.error(
            "dropped_anchor",
            f"{message}; nearest kept word: {clip_id}.w{nearest}",
            hint=f"anchor to {clip_id}.w{nearest}",
        )

    def _asset(self, asset_id: str, role: str, where: str) -> ClipAnalysis | None:
        analysis = self.index.clips.get(asset_id)
        if analysis is not None and analysis.clip.role == role:
            return analysis
        same = ", ".join(c for c, a in self.index.clips.items() if a.clip.role == role) or "none"
        kind, plural = ("a B-roll clip", "B-roll") if role == "broll" else ("an image", "images")
        self.problems.error("bad_asset", f"{where}: {asset_id} is not {kind}; {plural}: {same}")
        return None

    def _fit(self, asset: ClipAnalysis, asset_in: float, start: int, end: int, where: str) -> int:
        """End B-roll where the clip runs out, with a warning."""
        fps = self.out.fps
        left = asset.clip.duration_s - asset_in
        if (end - start) / fps <= left + 1e-6:
            return end
        self.problems.warn(
            "asset_short",
            f"{where}: {asset.clip.id} has {left:.2f} s from asset_in_s, "
            f"shown for {(end - start) / fps:.2f} s: cut short",
            hint="lower asset_in_s, or end the event on an earlier word",
        )
        return start + math.floor(left * fps + 1e-6)

    def _snap(self, start: int) -> int:
        """Move an overlay start to the nearest beat within BEAT_SNAP_S."""
        t = start / self.out.fps
        close = [b for b in self.beats if abs(b - t) <= BEAT_SNAP_S + 1e-9]
        if not close:
            return start
        beat = min(close, key=lambda b: (abs(b - t), b))
        return max(0, math.floor(beat * self.out.fps + 0.5))


def _check_overlaps(
    placed: Sequence[tuple[int, TimelineEvent]], fps: int, problems: Problems
) -> None:
    overlays = [(n, e) for n, e in placed if isinstance(e, TimelineBroll | TimelineImage)]
    full = [(n, e) for n, e in overlays if e.mode == "full"]
    for k, (n, a) in enumerate(full):
        for m, b in full[k + 1 :]:
            overlap = min(a.end, b.end) - max(a.start, b.start)
            if overlap > 0:
                problems.error(
                    "overlay_overlap",
                    f"events {n} ({a.type} {a.asset}) and {m} ({b.type} {b.asset}) "
                    f"overlap by {overlap / fps:.2f} s",
                    hint="full-frame overlays cannot overlap: move one, or set mode pip",
                )
    for n, title in placed:
        if not isinstance(title, TimelineTitle):
            continue
        for m, overlay in overlays:
            overlap = min(title.end, overlay.end) - max(title.start, overlay.start)
            if overlap > 0:
                problems.warn(
                    "title_over_broll",
                    f"event {n} (title) overlaps event {m} ({overlay.type} {overlay.asset}) "
                    f"by {overlap / fps:.2f} s",
                    hint="move the title, or accept it drawn over the overlay",
                )


def _frame(ms: int, fps: int) -> int:
    return math.floor(ms * fps / 1000 + 0.5)


def _word_index(word_id: str) -> int:
    return int(word_id.rsplit(".w", 1)[1])


def _src(analysis: ClipAnalysis) -> str:
    return analysis.clip.mezzanine or analysis.clip.source
