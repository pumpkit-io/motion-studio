"""The validate summary (guide §6.6): about ten lines the host agent reads after each change."""

from collections import Counter
from dataclasses import dataclass
from typing import Any, overload

from motion_studio.config import Config
from motion_studio.edl.grid import BeatGrid
from motion_studio.edl.issues import EdlError, Issue
from motion_studio.edl.models import EmphasisEvent, ProductEdl, TalkEdl
from motion_studio.edl.resolve import Resolution

HOOK_MS = 3000
MAX_ISSUE_LINES = 20
EVENT_ORDER = ("zoom", "push", "broll", "image", "title", "emphasis")


@dataclass
class Summary:
    language: str | None
    segments: int
    runs: int
    duration_s: float
    limit_s: float
    words_kept: int
    words_total: int
    hard_fillers_removed: int
    pauses_tightened: int
    hook: str
    hook_continues: bool
    events: dict[str, int]
    warnings: list[Issue]
    timeline: str

    @property
    def words_per_second(self) -> float:
        return round(self.words_kept / self.duration_s, 1) if self.duration_s else 0.0

    def lines(self) -> list[str]:
        events = " · ".join(
            f"emphasis {n}" if kind == "emphasis" else f"{n} {kind}"
            for kind, n in self.events.items()
        )
        lines = [
            f"✓ edl.json valid · language {self.language or 'unknown'} · "
            f"{self.segments} segments → {self.runs} runs",
            f"Duration {self.duration_s:.1f}s (limit {self.limit_s:g}s) · "
            f"words kept {self.words_kept}/{self.words_total} · "
            f"{self.words_per_second:.1f} words/s · "
            f"hard fillers removed {self.hard_fillers_removed} · "
            f"pauses tightened {self.pauses_tightened}",
            f'Hook (first 3s): "{self.hook}{"…" if self.hook_continues else ""}"',
            f"Events: {events or 'none'}",
        ]
        lines += _issue_lines("⚠", self.warnings, "warnings")
        lines.append(f"→ {self.timeline}")
        return lines

    def to_json(self) -> dict[str, Any]:
        return {
            "valid": True,
            "language": self.language,
            "segments": self.segments,
            "runs": self.runs,
            "duration_s": self.duration_s,
            "limit_s": self.limit_s,
            "words_kept": self.words_kept,
            "words_total": self.words_total,
            "words_per_second": self.words_per_second,
            "hard_fillers_removed": self.hard_fillers_removed,
            "pauses_tightened": self.pauses_tightened,
            "hook": self.hook,
            "events": self.events,
            "warnings": [w.model_dump() for w in self.warnings],
            "timeline": self.timeline,
        }


@dataclass
class ProductSummary:
    """The validate summary of a product EDL: scenes, length and the grid they sit on."""

    language: str | None
    scenes: int
    formats: list[str]
    duration_s: float
    limit_s: float
    grid: BeatGrid
    scene_types: dict[str, int]
    warnings: list[Issue]
    timeline: str

    def lines(self) -> list[str]:
        source = "from the music" if self.grid.from_music else "steady (no music yet)"
        lines = [
            f"✓ edl.json valid · product · {self.scenes} scenes · {', '.join(self.formats)}",
            f"Duration {self.duration_s:.1f}s (limit {self.limit_s:g}s) · "
            f"grid {self.grid.bpm:g} bpm, {source}",
            "Scenes: " + " · ".join(f"{n} {kind}" for kind, n in self.scene_types.items()),
        ]
        lines += _issue_lines("⚠", self.warnings, "warnings")
        lines.append(f"→ {self.timeline}")
        return lines

    def to_json(self) -> dict[str, Any]:
        return {
            "valid": True,
            "kind": "product",
            "language": self.language,
            "scenes": self.scenes,
            "formats": self.formats,
            "duration_s": self.duration_s,
            "limit_s": self.limit_s,
            "grid": {
                "bpm": round(self.grid.bpm, 2),
                "beats_per_bar": self.grid.beats_per_bar,
                "from_music": self.grid.from_music,
            },
            "scene_types": self.scene_types,
            "warnings": [w.model_dump() for w in self.warnings],
            "timeline": self.timeline,
        }


@overload
def summarize(
    edl: TalkEdl, resolution: Resolution, config: Config, timeline_path: str
) -> Summary: ...
@overload
def summarize(
    edl: ProductEdl, resolution: Resolution, config: Config, timeline_path: str
) -> ProductSummary: ...
@overload
def summarize(
    edl: TalkEdl | ProductEdl, resolution: Resolution, config: Config, timeline_path: str
) -> Summary | ProductSummary: ...
def summarize(
    edl: TalkEdl | ProductEdl, resolution: Resolution, config: Config, timeline_path: str
) -> Summary | ProductSummary:
    """Summarise a resolved EDL; `timeline_path` is where the timeline was written."""
    if isinstance(edl, ProductEdl):
        return _product_summary(edl, resolution, config, timeline_path)
    timeline = resolution.timeline
    stats = resolution.stats
    hook = [w for w in timeline.words if w.start_ms < HOOK_MS]
    counts: Counter[str] = Counter()
    for event in edl.events:
        counts[event.type] += len(event.words) if isinstance(event, EmphasisEvent) else 1
    return Summary(
        language=timeline.language,
        segments=len(edl.segments),
        runs=len(timeline.runs),
        duration_s=round(timeline.duration_frames / timeline.fps, 1),
        limit_s=edl.max_duration_s or config.defaults.max_duration_s,
        words_kept=stats.words_kept,
        words_total=stats.words_total,
        hard_fillers_removed=stats.hard_fillers_removed,
        pauses_tightened=stats.pauses_tightened,
        hook=" ".join(w.text for w in hook),
        hook_continues=len(hook) < len(timeline.words),
        events={kind: counts[kind] for kind in EVENT_ORDER if counts[kind]},
        warnings=list(resolution.warnings),
        timeline=timeline_path,
    )


def error_report(error: EdlError) -> tuple[list[str], dict[str, Any]]:
    """Human lines and JSON for an EDL that does not resolve."""
    count = len(error.problems)
    lines = [f"✗ edl.json has {count} error{'s' if count != 1 else ''}"]
    lines += _issue_lines("✗", error.problems, "errors")
    return lines, {"valid": False, "errors": [p.model_dump() for p in error.problems]}


def _issue_lines(mark: str, issues: list[Issue], noun: str) -> list[str]:
    lines = [
        f"{mark} {issue.message}" + (f" → {issue.hint}" if issue.hint else "")
        for issue in issues[:MAX_ISSUE_LINES]
    ]
    if len(issues) > MAX_ISSUE_LINES:
        lines.append(
            f"{mark} … and {len(issues) - MAX_ISSUE_LINES} more {noun} (--json lists them all)"
        )
    return lines


def _product_summary(
    edl: ProductEdl, resolution: Resolution, config: Config, timeline_path: str
) -> ProductSummary:
    timeline = resolution.timeline
    assert resolution.grid is not None
    return ProductSummary(
        language=timeline.language,
        scenes=len(timeline.scenes),
        formats=[f.name for f in timeline.formats],
        duration_s=round(timeline.duration_frames / timeline.fps, 1),
        limit_s=edl.max_duration_s or config.defaults.max_duration_s,
        grid=resolution.grid,
        scene_types=dict(Counter(s.type for s in timeline.scenes)),
        warnings=list(resolution.warnings),
        timeline=timeline_path,
    )
