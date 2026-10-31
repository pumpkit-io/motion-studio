"""The deterministic draft of a product EDL: a baseline story the host agent rewrites.

An intro title card; per screen recording, a numbered title card and its footage from the first
marker to the last; a proof scene per image; and a logo outro. Every length sits on the grid.
"""

import re
from collections.abc import Sequence
from pathlib import PurePosixPath

from motion_studio.analysis import ClipAnalysis
from motion_studio.edl.grid import BeatGrid
from motion_studio.edl.models import (
    DeviceFrame,
    EdlMusic,
    FootagePoint,
    FootageScene,
    LogoOutroScene,
    MarkerPoint,
    ProductEdl,
    ProofScene,
    Scene,
    TitleCardScene,
)
from motion_studio.edl.product import BrandAssets
from motion_studio.errors import UserError

SEED = 1
# Seconds each card should last; the draft rounds them to whole bars of the grid.
_TITLE_S = 2.0
_PROOF_S = 4.0
_OUTRO_S = 4.0
_PROMPT = (
    "fast future house, punchy claps, bright lead synth, rising build, big drop, energetic, "
    "instrumental"
)
_DIGITS = re.compile(r"\d+")


def draft_product(
    clips: Sequence[ClipAnalysis], *, title: str, grid: BeatGrid, brand: BrandAssets
) -> ProductEdl:
    recordings = sorted((c for c in clips if c.clip.role == "screen"), key=_clip_order)
    images = sorted((c for c in clips if c.clip.role == "image"), key=_clip_order)
    if not recordings and not images:
        raise UserError(
            "the project has no screen recordings or images to draft from",
            hint="record with `record web` or `record terminal`, or add files to raw/, then "
            "run ingest and analyze",
        )
    card = _bars(grid, _TITLE_S)
    scenes: list[Scene] = [
        TitleCardScene(
            type="title_card",
            id="intro",
            bars=card,
            headline=title,
            note="The hook: say what the product does for the viewer.",
        )
    ]
    for n, recording in enumerate(recordings, start=1):
        scenes.append(
            TitleCardScene(
                type="title_card",
                id=f"step{n}",
                bars=card,
                step=f"{n:02d}",
                headline=_headline(recording),
                note=f"Introduces {recording.clip.id}: name the step it shows.",
            )
        )
        scenes.append(_footage(f"demo{n}", recording))
    for n, image in enumerate(images, start=1):
        scenes.append(
            ProofScene(
                type="proof",
                id=f"proof{n}",
                bars=_bars(grid, _PROOF_S),
                image=image.clip.id,
                note="Add a headline and a badge if the image proves a result.",
            )
        )
    leftout: list[str] = []
    if brand.wordmark is not None:
        scenes.append(
            LogoOutroScene(
                type="logo_outro",
                id="outro",
                bars=_bars(grid, _OUTRO_S),
                mascot=brand.mascot is not None,
                note="Add a tagline and the product's URL.",
            )
        )
    else:
        reason = brand.broken.get("wordmark", "is not set")
        leftout.append(f"No logo outro: the [brand] wordmark {reason}.")
    return ProductEdl(
        kind="product",
        title=title,
        scenes=scenes,
        music=EdlMusic(mode="generate", prompt=_PROMPT, bpm=round(grid.bpm), seed=SEED),
        rationale=_rationale(grid, recordings, scenes, leftout),
    )


def _footage(scene_id: str, recording: ClipAnalysis) -> FootageScene:
    """The whole recording from its first marker to its last, at 1x and rounded to whole beats."""
    clip = recording.clip
    start, end = _span(recording)
    return FootageScene.model_validate(
        {
            "type": "footage",
            "id": scene_id,
            "clip": clip.id,
            "from": start,
            "to": end,
            "device_frame": _device_frame(recording),
            "note": f"{PurePosixPath(clip.source).name}: trim with markers or offsets, then "
            "add camera moves onto the elements that matter.",
        }
    )


def _span(recording: ClipAnalysis) -> tuple[FootagePoint, FootagePoint]:
    clip = recording.clip
    markers = recording.markers
    if not markers:
        return 0.0, round(clip.duration_s, 3)
    first, last = markers[0], markers[-1]
    ref = f"{clip.id}.m.{first.name}"
    if last.t > first.t:
        return ref, f"{clip.id}.m.{last.name}"
    # One moment marked: play the whole clip around it, since marked clips take no seconds.
    return (
        MarkerPoint(marker=ref, offset_s=-first.t),
        MarkerPoint(marker=ref, offset_s=round(clip.duration_s - first.t, 3)),
    )


def _device_frame(recording: ClipAnalysis) -> DeviceFrame:
    """`record terminal` takes carry markers but no cursor track and no element boxes."""
    markers = recording.markers
    if markers and not recording.cursor and not any(m.elements for m in markers):
        return "terminal"
    return "browser"


def _headline(recording: ClipAnalysis) -> str:
    words = re.sub(r"[-_.\s]+", " ", PurePosixPath(recording.clip.source).stem).strip()
    return words[:1].upper() + words[1:] if words else recording.clip.id


def _bars(grid: BeatGrid, seconds: float) -> int:
    bar_s = grid.beats_per_bar * 60 / grid.bpm
    return max(1, round(seconds / bar_s))


def _rationale(
    grid: BeatGrid, recordings: Sequence[ClipAnalysis], scenes: Sequence[Scene], notes: list[str]
) -> str:
    source = "the bed's grid" if grid.from_music else "a steady grid (no music yet)"
    parts = [
        f"Deterministic draft on {source} at {grid.bpm:.4g} bpm, {grid.beats_per_bar} beats a "
        "bar: an intro title card; per screen recording a numbered title card and its footage "
        "from its first marker to its last at 1x, rounded to whole beats; a proof scene per "
        "image; and a logo outro. Cards are whole bars.",
        "Change first: the headlines, which are placeholders from the title and the file "
        "names; then trim each footage scene and add camera moves.",
    ]
    unmarked = [r.clip.id for r in recordings if not r.markers]
    if unmarked:
        parts.append(
            f"{', '.join(unmarked)} has no markers, so its footage runs in source seconds over "
            "the whole clip."
        )
    terminal = [
        s.clip for s in scenes if isinstance(s, FootageScene) and s.device_frame == "terminal"
    ]
    if terminal:
        parts.append(
            f"{', '.join(terminal)} has markers but no cursor or elements, so it is drawn in a "
            "terminal frame."
        )
    return " ".join([*parts, *notes])


def _clip_order(analysis: ClipAnalysis) -> tuple[int, str]:
    found = _DIGITS.search(analysis.clip.id)
    return int(found.group()) if found else 0, analysis.clip.id
