"""`check/cuts.png`: the frames 0.2 s before and after every cut, labelled with the cut index."""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

from reelcut.errors import InternalError
from reelcut.look.sheet import (
    BACKGROUND,
    GAP,
    HEADER_SIZE,
    INK,
    LABEL_SIZE,
    MARGIN,
    MAX_WIDTH,
    MUTED,
    font,
    text_width,
)
from reelcut.media.ffmpeg import read_frames

OFFSET_S = 0.2
FRAME_HEIGHT = 240
FRAME_MAX_WIDTH = 300
CUT_MARK = (220, 38, 38)


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


def _frame(video: Path, t: float, width: int, height: int) -> Image.Image:
    args = ["-ss", f"{t:.3f}", "-i", video, "-frames:v", "1"]
    decoded = list(read_frames(args, width=width, height=height, filters=f"scale={width}:{height}"))
    if not decoded:
        raise InternalError(f"could not decode a frame of {video} at {t:.2f} s")
    return Image.fromarray(decoded[0])


def _fit(text: str, width: int) -> str:
    size = LABEL_SIZE - 2
    if text_width(text, size) <= width:
        return text
    before, after = text.split(" | ", 1)
    while text_width(f"…{before} | {after}…", size) > width and (len(before) > 4 or len(after) > 4):
        before = before[1:] if len(before) >= len(after) else before
        after = after[:-1] if len(after) > len(before) else after
    return f"…{before} | {after}…"
