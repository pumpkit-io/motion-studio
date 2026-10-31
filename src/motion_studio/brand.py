"""Load the `[brand]` files product scenes draw: the wordmark image and the mascot (sprite or GIF).

Nothing here fails: an asset that does not load is recorded with the reason, and the resolver
reports it only when a scene needs it.
"""

from pathlib import Path

from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from motion_studio.config import Brand
from motion_studio.edl.models import TimelineGifMascot, TimelineMascot, TimelineSpriteFrame
from motion_studio.edl.product import BrandAssets


class SpriteFrame(BaseModel):
    x: int = Field(ge=0, description="Left edge of the frame in the sheet, in sheet pixels.")
    y: int = Field(ge=0)
    ms: int = Field(gt=0, description="How long the frame shows.")


class SpriteTimings(BaseModel):
    """A mascot's frame-timing JSON: where each frame sits in the sheet and how long it shows."""

    # Exporters add their own keys (image, columns, rows, loop_ms); they are not needed.
    model_config = ConfigDict(extra="ignore")

    frame_width: int = Field(gt=0)
    frame_height: int = Field(gt=0)
    frames: list[SpriteFrame] = Field(min_length=1, description="In playing order.")
    loops: int = Field(
        default=0,
        ge=0,
        description="Times the frames play before the last one holds; 0 is forever.",
    )


def load_brand_assets(workspace: Path, brand: Brand) -> BrandAssets:
    wordmark: str | None = None
    mascot: TimelineMascot | TimelineGifMascot | None = None
    broken: dict[str, str] = {}
    if brand.wordmark is not None:
        reason = _missing(workspace, brand.wordmark)
        if reason is None:
            wordmark = brand.wordmark
        else:
            broken["wordmark"] = reason
    if brand.mascot is not None:
        try:
            if brand.mascot.gif is not None:
                mascot = _gif(workspace, brand.mascot.gif)
            else:
                assert brand.mascot.sheet is not None and brand.mascot.timings is not None
                mascot = _mascot(workspace, brand.mascot.sheet, brand.mascot.timings)
        except _Broken as exc:
            broken["mascot"] = str(exc)
    return BrandAssets(wordmark=wordmark, mascot=mascot, broken=broken)


class _Broken(Exception):
    pass


def _missing(workspace: Path, path: str) -> str | None:
    if (workspace / path).is_file():
        return None
    return f"names {path}, which does not exist"


def _gif(workspace: Path, gif: str) -> TimelineGifMascot:
    reason = _missing(workspace, gif)
    if reason is not None:
        raise _Broken(reason)
    try:
        with Image.open(workspace / gif) as image:
            kind, (width, height) = image.format, image.size
    except (OSError, UnidentifiedImageError) as exc:
        raise _Broken(f"gif {gif} is not an image: {exc}") from exc
    if kind != "GIF":
        raise _Broken(f"gif {gif} is not a GIF")
    return TimelineGifMascot(type="gif", gif=gif, width=width, height=height)


def _mascot(workspace: Path, sheet: str, timings: str) -> TimelineMascot:
    for path in (sheet, timings):
        reason = _missing(workspace, path)
        if reason is not None:
            raise _Broken(reason)
    try:
        parsed = SpriteTimings.model_validate_json((workspace / timings).read_bytes())
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in e['loc']) or 'file'}: {e['msg']}" for e in exc.errors()
        )
        raise _Broken(f"timings {timings} is not valid: {problems}") from exc
    try:
        with Image.open(workspace / sheet) as image:
            width, height = image.size
    except (OSError, UnidentifiedImageError) as exc:
        raise _Broken(f"sheet {sheet} is not an image: {exc}") from exc
    outside = [
        i
        for i, f in enumerate(parsed.frames)
        if f.x + parsed.frame_width > width or f.y + parsed.frame_height > height
    ]
    if outside:
        raise _Broken(
            f"timings {timings}: frame {outside[0]} falls outside the {width}x{height} sheet"
        )
    return TimelineMascot(
        type="sprite",
        sheet=sheet,
        sheet_width=width,
        sheet_height=height,
        frame_width=parsed.frame_width,
        frame_height=parsed.frame_height,
        frames=[TimelineSpriteFrame(x=f.x, y=f.y, ms=f.ms) for f in parsed.frames],
        loops=parsed.loops,
    )
