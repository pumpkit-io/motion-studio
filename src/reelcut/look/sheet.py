"""Pillow drawing for contact sheets: frame grids, a waveform panel and word labels.

Pure functions over decoded frames and analysis data; reading media is `reelcut.look`'s job.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import numpy as np
import numpy.typing as npt
from PIL import Image, ImageDraw, ImageFont

from reelcut.analysis import FaceSample, Pause, Span, Word

# DejaVu Sans cut to Latin, Latin-1 and Latin Extended: Pillow's own font has no "è" or "ù".
FONT = Path(__file__).parent / "fonts" / "DejaVuSans-Latin.ttf"
MAX_WIDTH = 1600
FRAME_HEIGHT = 320
MARGIN = 16
GAP = 10

BACKGROUND = (250, 250, 248)
INK = (24, 24, 27)
MUTED = (113, 113, 122)
WAVE = (63, 63, 70)
SPEECH = (209, 242, 220)
HATCH = (161, 161, 170)
FRAME_MARK = (37, 99, 235)
# Face boxes stay clear of the filler reds and oranges so the two never read alike.
FACE = (0, 200, 255)
FILLER_COLOURS = {"hard": (220, 38, 38), "soft": (234, 120, 0)}

HEADER_SIZE = 22
LABEL_SIZE = 18
WAVE_HEIGHT = 140
LANE_HEIGHT = 26


@dataclass
class Frame:
    image: npt.NDArray[np.uint8]
    t: float
    face: FaceSample | None = None


@cache
def font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT, size)


def text_width(text: str, size: int) -> int:
    left, _, right, _ = font(size).getbbox(text)
    return math.ceil(right - left)


def grid_columns(frame_width: int, count: int, max_width: int = MAX_WIDTH) -> int:
    room = max_width - 2 * MARGIN + GAP
    return max(1, min(count, room // (frame_width + GAP)))


def fit_frame(width: int, height: int, max_height: int = FRAME_HEIGHT) -> tuple[int, int]:
    """Even pixel size for one frame: `max_height` tall unless that would overflow the sheet."""
    scale = min(max_height / height, (MAX_WIDTH - 2 * MARGIN) / width)
    return max(2, round(width * scale / 2) * 2), max(2, round(height * scale / 2) * 2)


def draw_frames(
    sheet: Image.Image, frames: Sequence[Frame], top: int, *, stamps: bool = True
) -> int:
    """Paste the frames as a centred grid with face boxes and timestamps; return the next y."""
    if not frames:
        return top
    draw = ImageDraw.Draw(sheet)
    fh, fw = frames[0].image.shape[:2]
    cols = grid_columns(fw, len(frames), sheet.width)
    cell_h = fh + (LABEL_SIZE + 8 if stamps else 0)
    left = (sheet.width - (cols * fw + (cols - 1) * GAP)) // 2
    for i, frame in enumerate(frames):
        x = left + (i % cols) * (fw + GAP)
        y = top + (i // cols) * (cell_h + GAP)
        sheet.paste(Image.fromarray(frame.image), (x, y))
        if frame.face is not None:
            draw_face(draw, frame.face, x, y, fw, fh)
        if stamps:
            stamp = f"{frame.t:.2f}s"
            draw.text(
                (x + (fw - text_width(stamp, LABEL_SIZE)) // 2, y + fh + 4),
                stamp,
                fill=INK,
                font=font(LABEL_SIZE),
            )
    rows = math.ceil(len(frames) / cols)
    return top + rows * cell_h + (rows - 1) * GAP


def draw_face(
    draw: ImageDraw.ImageDraw, face: FaceSample, x: int, y: int, width: int, height: int
) -> None:
    box = (
        x + (face.cx - face.w / 2) * width,
        y + (face.cy - face.h / 2) * height,
        x + (face.cx + face.w / 2) * width,
        y + (face.cy + face.h / 2) * height,
    )
    draw.rectangle(box, outline=FACE, width=3)


def frames_height(frames: Sequence[Frame], width: int, *, stamps: bool = True) -> int:
    if not frames:
        return 0
    fh, fw = frames[0].image.shape[:2]
    rows = math.ceil(len(frames) / grid_columns(fw, len(frames), width))
    return rows * (fh + (LABEL_SIZE + 8 if stamps else 0)) + (rows - 1) * GAP


def asset_sheet(title: str, frames: Sequence[Frame], *, stamps: bool = True) -> Image.Image:
    """A header and the frames of one B-roll clip or image."""
    fw = frames[0].image.shape[1]
    cols = grid_columns(fw, len(frames))
    grid_w = cols * fw + (cols - 1) * GAP
    width = min(MAX_WIDTH, max(grid_w, text_width(title, HEADER_SIZE), 480) + 2 * MARGIN)
    header = HEADER_SIZE + 2 * MARGIN
    sheet = Image.new("RGB", (width, header + frames_height(frames, width, stamps=stamps) + MARGIN))
    sheet.paste(BACKGROUND, (0, 0, *sheet.size))
    ImageDraw.Draw(sheet).text((MARGIN, MARGIN), title, fill=INK, font=font(HEADER_SIZE))
    draw_frames(sheet, frames, header, stamps=stamps)
    return sheet


def range_sheet(
    title: str,
    frames: Sequence[Frame],
    *,
    t0: float,
    t1: float,
    samples: npt.NDArray[np.float32] | None,
    vad: Sequence[Span],
    pauses: Sequence[Pause],
    words: Sequence[Word],
) -> Image.Image:
    """Frames, then the waveform of [t0, t1] with speech, pauses, frame times and word labels."""
    width = MAX_WIDTH
    plot_w = width - 2 * MARGIN
    lanes = word_lanes(words, t0, t1, plot_w)
    header = HEADER_SIZE + 2 * MARGIN
    strip = frames_height(frames, width)
    lane_count = max(1, max(lanes, default=-1) + 1)
    height = (
        header
        + strip
        + MARGIN
        + WAVE_HEIGHT
        + LABEL_SIZE
        + 10
        + lane_count * LANE_HEIGHT
        + LABEL_SIZE
        + 2 * MARGIN
    )
    sheet = Image.new("RGB", (width, height))
    sheet.paste(BACKGROUND, (0, 0, width, height))
    draw = ImageDraw.Draw(sheet)
    draw.text((MARGIN, MARGIN), title, fill=INK, font=font(HEADER_SIZE))
    top = draw_frames(sheet, frames, header) + MARGIN

    def x_of(t: float) -> float:
        return MARGIN + (min(max(t, t0), t1) - t0) / (t1 - t0) * plot_w

    wave_box = (MARGIN, top, MARGIN + plot_w, top + WAVE_HEIGHT)
    for span in vad:
        if span.end > t0 and span.start < t1:
            draw.rectangle((x_of(span.start), top, x_of(span.end), top + WAVE_HEIGHT), fill=SPEECH)
    for pause in pauses:
        if pause.end > t0 and pause.start < t1:
            hatch(draw, (x_of(pause.start), top, x_of(pause.end), top + WAVE_HEIGHT))
    draw_wave(draw, samples, wave_box)
    for frame in frames:
        x = x_of(frame.t)
        draw.line((x, top, x, top + WAVE_HEIGHT), fill=FRAME_MARK, width=1)
    draw.rectangle(wave_box, outline=MUTED, width=1)

    axis = top + WAVE_HEIGHT + 4
    for tick in ticks(t0, t1):
        x = x_of(tick)
        draw.line((x, axis - 4, x, axis), fill=MUTED)
        label = f"{tick:g}s"
        lx = min(max(x - text_width(label, LABEL_SIZE) / 2, MARGIN), width - MARGIN - 40)
        draw.text((lx, axis), label, fill=MUTED, font=font(LABEL_SIZE))

    lanes_top = axis + LABEL_SIZE + 10
    for word, lane in zip(words, lanes, strict=True):
        colour = FILLER_COLOURS.get(word.filler or "", INK)
        y = lanes_top + lane * LANE_HEIGHT
        x0, x1 = x_of(word.start), max(x_of(word.end), x_of(word.start) + 2)
        draw.line((x0, top + WAVE_HEIGHT - 3, x1, top + WAVE_HEIGHT - 3), fill=colour, width=4)
        draw.text((x0, y), word.text, fill=colour, font=font(LABEL_SIZE))

    legend_y = lanes_top + lane_count * LANE_HEIGHT + MARGIN // 2
    draw_legend(draw, MARGIN, legend_y)
    return sheet


def word_lanes(words: Sequence[Word], t0: float, t1: float, plot_w: int) -> list[int]:
    """Give each label the first row where it does not overlap the label before it."""
    ends: list[float] = []
    lanes: list[int] = []
    for word in words:
        x = (max(word.start, t0) - t0) / (t1 - t0) * plot_w
        right = x + text_width(word.text, LABEL_SIZE) + 6
        lane = next((i for i, end in enumerate(ends) if end <= x), len(ends))
        if lane == len(ends):
            ends.append(right)
        else:
            ends[lane] = right
        lanes.append(lane)
    return lanes


def ticks(t0: float, t1: float, target: int = 10) -> list[float]:
    raw = (t1 - t0) / target
    step = next((s for s in (0.1, 0.2, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60) if s >= raw), 60 * raw)
    first = math.ceil(t0 / step - 1e-9) * step
    return [round(first + i * step, 3) for i in range(int((t1 - first) / step + 1e-9) + 1)]


def hatch(draw: ImageDraw.ImageDraw, box: tuple[float, float, float, float]) -> None:
    left, top, right, bottom = box
    height = bottom - top
    x = left - height
    while x < right:
        start = (max(x, left), top + (max(x, left) - x))
        end_x = min(x + height, right)
        draw.line((*start, end_x, top + (end_x - x)), fill=HATCH, width=1)
        x += 8


def draw_wave(
    draw: ImageDraw.ImageDraw,
    samples: npt.NDArray[np.float32] | None,
    box: tuple[int, int, int, int],
) -> None:
    left, top, right, bottom = box
    mid = (top + bottom) / 2
    if samples is None or samples.size == 0:
        draw.text((left + 8, mid - LABEL_SIZE / 2), "no audio", fill=MUTED, font=font(LABEL_SIZE))
        return
    columns = right - left
    edges = np.linspace(0, samples.size, columns + 1).astype(int)
    peak = float(np.abs(samples).max()) or 1.0
    half = (bottom - top) / 2 - 4
    for i in range(columns):
        chunk = samples[edges[i] : max(edges[i + 1], edges[i] + 1)]
        if chunk.size == 0:
            continue
        hi, lo = float(chunk.max()) / peak, float(chunk.min()) / peak
        draw.line((left + i, mid - hi * half, left + i, mid - lo * half), fill=WAVE)


def draw_legend(draw: ImageDraw.ImageDraw, x: float, y: float) -> None:
    items: list[tuple[str, tuple[int, int, int]]] = [
        ("word", INK),
        ("hard filler", FILLER_COLOURS["hard"]),
        ("soft filler", FILLER_COLOURS["soft"]),
        ("speech (VAD)", (120, 190, 140)),
        ("pause (hatched)", HATCH),
        ("frame time", FRAME_MARK),
        ("face box", FACE),
    ]
    for label, colour in items:
        draw.rectangle((x, y + 4, x + 12, y + 16), fill=colour)
        draw.text((x + 18, y), label, fill=INK, font=font(LABEL_SIZE - 2))
        x += 18 + text_width(label, LABEL_SIZE - 2) + 22
