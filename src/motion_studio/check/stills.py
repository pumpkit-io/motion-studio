"""`check/cuts.png`: the frames 0.2 s before and after every cut, labelled with the cut index,
and `check/contact.png`: one frame per second of a product render."""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt
from PIL import Image, ImageDraw

from motion_studio.errors import InternalError
from motion_studio.look.sheet import (
    BACKGROUND,
    GAP,
    HEADER_SIZE,
    INK,
    LABEL_SIZE,
    MARGIN,
    MAX_WIDTH,
    MUTED,
    Frame,
    asset_sheet,
    fit_frame,
    font,
    text_width,
)
from motion_studio.media.ffmpeg import read_frames

OFFSET_S = 0.2
FRAME_HEIGHT = 240
FRAME_MAX_WIDTH = 300
CUT_MARK = (220, 38, 38)
CONTACT_FPS = 1.0
CONTACT_HEIGHT = 180
# About 30 rows of frames, as for a screen recording's sheet at ingest.
MAX_CONTACT_FRAMES = 180


@dataclass(frozen=True)
class Cut:
    index: int
    t: float
    before: str
    after: str


def cuts_sheet(
    video: Path,
    size: tuple[int, int],
    duration_s: float,
    fps: int,
    cuts: Sequence[Cut],
    title: str,
    out: Path,
) -> Path:
    """Draw one cell per cut (before | after, with the words either side) and save it to `out`."""
    width, height = size
    scale = min(FRAME_HEIGHT / height, FRAME_MAX_WIDTH / width)
    fw, fh = max(2, round(width * scale / 2) * 2), max(2, round(height * scale / 2) * 2)
    cell_w = 2 * fw + 4
    cols = max(1, min(len(cuts), (MAX_WIDTH - 2 * MARGIN + GAP) // (cell_w + GAP)))
    rows = math.ceil(len(cuts) / cols)
    cell_h = LABEL_SIZE + 6 + fh + 4 + LABEL_SIZE + 4
    header = HEADER_SIZE + 2 * MARGIN + LABEL_SIZE
    sheet_w = max(cols * cell_w + (cols - 1) * GAP, text_width(title, HEADER_SIZE), 480)
    sheet_w = min(MAX_WIDTH, sheet_w + 2 * MARGIN)
    sheet_h = header + max(rows, 1) * (cell_h + GAP) + MARGIN
    sheet = Image.new("RGB", (sheet_w, sheet_h))
    sheet.paste(BACKGROUND, (0, 0, sheet_w, sheet_h))
    draw = ImageDraw.Draw(sheet)
    draw.text((MARGIN, MARGIN), title, fill=INK, font=font(HEADER_SIZE))
    legend = f"each cut: frame {OFFSET_S:.1f} s before | frame {OFFSET_S:.1f} s after"
    if not cuts:
        legend = "no cuts: the timeline is a single run"
    draw.text((MARGIN, MARGIN + HEADER_SIZE + 6), legend, fill=MUTED, font=font(LABEL_SIZE - 2))
    last = max(0.0, duration_s - 1 / fps)
    for n, cut in enumerate(cuts):
        x = MARGIN + (n % cols) * (cell_w + GAP)
        y = header + (n // cols) * (cell_h + GAP)
        label = f"cut {cut.index}  {cut.t:.2f}s"
        draw.text((x, y), label, fill=INK, font=font(LABEL_SIZE))
        top = y + LABEL_SIZE + 6
        for side, t in enumerate((cut.t - OFFSET_S, cut.t + OFFSET_S)):
            image = _frame(video, min(max(t, 0.0), last), fw, fh)
            sheet.paste(image, (x + side * (fw + 4), top))
        draw.line((x + fw + 1, top, x + fw + 1, top + fh), fill=CUT_MARK, width=3)
        words = _fit(f"{cut.before} | {cut.after}", cell_w)
        draw.text((x, top + fh + 4), words, fill=MUTED, font=font(LABEL_SIZE - 2))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return out


def contact_sheet(
    video: Path, size: tuple[int, int], duration_s: float, title: str, out: Path
) -> tuple[Path, list[str]]:
    """One frame per second of `video`, each stamped with its output time; a render longer
    than MAX_CONTACT_FRAMES seconds is sampled more sparsely, with a warning."""
    count = max(1, math.ceil(duration_s * CONTACT_FPS - 1e-6))
    warnings: list[str] = []
    if count > MAX_CONTACT_FRAMES:
        warnings.append(
            f"{duration_s:.0f} s is too long for a 1 fps contact sheet; it shows "
            f"{MAX_CONTACT_FRAMES} frames, one every {duration_s / MAX_CONTACT_FRAMES:.1f} s"
        )
        count = MAX_CONTACT_FRAMES
    step = duration_s / count
    fw, fh = fit_frame(*size, CONTACT_HEIGHT)
    times = [(i + 0.5) * step for i in range(count)]
    frames = [Frame(_decode(video, t, fw, fh), t) for t in times]
    out.parent.mkdir(parents=True, exist_ok=True)
    asset_sheet(f"{title} · {count} frames, one per {step:.1f} s", frames).save(out, optimize=True)
    return out, warnings


def _frame(video: Path, t: float, width: int, height: int) -> Image.Image:
    return Image.fromarray(_decode(video, t, width, height))


def _decode(video: Path, t: float, width: int, height: int) -> npt.NDArray[np.uint8]:
    args = ["-ss", f"{t:.3f}", "-i", video, "-frames:v", "1"]
    decoded = list(read_frames(args, width=width, height=height, filters=f"scale={width}:{height}"))
    if not decoded:
        raise InternalError(f"could not decode a frame of {video} at {t:.2f} s")
    return decoded[0]


def _fit(text: str, width: int) -> str:
    size = LABEL_SIZE - 2
    if text_width(text, size) <= width:
        return text
    before, after = text.split(" | ", 1)
    while text_width(f"…{before} | {after}…", size) > width and (len(before) > 4 or len(after) > 4):
        before = before[1:] if len(before) >= len(after) else before
        after = after[:-1] if len(after) > len(before) else after
    return f"…{before} | {after}…"
