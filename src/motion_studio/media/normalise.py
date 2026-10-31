"""Normalise a raw video into a CFR, SDR, BT.709 H.264 mezzanine, and an image for overlays."""

import io
import os
import platform
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import Image, ImageCms, ImageOps

from motion_studio import ENV_PREFIX
from motion_studio.errors import DependencyError, UserError
from motion_studio.media.ffmpeg import FFmpegCaps, FFmpegError, run_ffmpeg
from motion_studio.media.probe import Probe

MAX_VIDEO_SIDE = 3840
MAX_IMAGE_SIDE = 4096
CRF = 15

Tonemap = Literal["scale_vt", "zscale", "colorspace"]
# Forces one tone-map method, e.g. to avoid VideoToolbox where it misbehaves.
TONEMAP_ENV = f"{ENV_PREFIX}_TONEMAP"

BT709_TAGS = ["-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"]

# zscale linearises, tonemap compresses the highlights, zscale re-encodes as BT.709.
ZSCALE_CHAIN = (
    "zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
    "tonemap=tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p"
)
SCALE_VT_CHAIN = (
    "format=p010le,hwupload,"
    "scale_vt=color_matrix=bt709:color_primaries=bt709:color_transfer=bt709,"
    "hwdownload,format=p010le,format=yuv420p"
)
# colorspace cannot read HLG or PQ, so it treats them as BT.2020 SDR: colours, not highlights.
COLORSPACE_CHAIN = "colorspace=all=bt709:iall=bt2020:itrc=bt2020-10:fast=0:format=yuv420p"


@dataclass(frozen=True)
class Mezzanine:
    path: Path
    width: int
    height: int
    tonemap: Tonemap | None
    warnings: tuple[str, ...]


def tonemap_methods(caps: FFmpegCaps) -> list[Tonemap]:
    """HDR to SDR methods this ffmpeg supports, best first (ADR 0003)."""
    methods: list[Tonemap] = []
    if platform.system() == "Darwin" and caps.has_filter("scale_vt"):
        methods.append("scale_vt")
    if caps.has_filter("zscale") and caps.has_filter("tonemap"):
        methods.append("zscale")
    if caps.has_filter("colorspace"):
        methods.append("colorspace")
    forced = os.environ.get(TONEMAP_ENV)
    if forced:
        if forced not in methods:
            raise DependencyError(
                f"{TONEMAP_ENV}={forced!r} is not available with this ffmpeg",
                hint=f"unset it, or use one of {', '.join(methods) or 'nothing (none found)'}",
            )
        return [forced]  # pyright: ignore[reportReturnType]
    return methods


def output_size(width: int, height: int, max_side: int = MAX_VIDEO_SIDE) -> tuple[int, int]:
    """Fit the long side within `max_side`, keeping the aspect ratio and even dimensions."""
    scale = min(1.0, max_side / max(width, height))
    return _even(width * scale), _even(height * scale)


def _even(value: float) -> int:
    return max(2, round(value / 2) * 2)


def make_mezzanine(
    source: Path,
    dest: Path,
    info: Probe,
    *,
    fps: int,
    caps: FFmpegCaps,
    progress: Callable[[float], None] | None = None,
) -> Mezzanine:
    """Write `dest` at `fps` CFR with rotation applied and HDR tone-mapped to BT.709.

    A tone-map method that fails at run time (VideoToolbox can be missing in a VM) falls
    through to the next one; every fallback adds a warning.
    """
    width, height = output_size(info.width, info.height)
    base = [f"fps={fps}", f"scale={width}:{height}:flags=lanczos", "setsar=1"]
    if info.hdr is None:
        _encode(source, dest, [*base, "format=yuv420p"], fps, caps, info.has_audio, progress)
        return Mezzanine(dest, width, height, None, ())
    methods = tonemap_methods(caps)
    warnings: list[str] = []
    if not methods:
        raise UserError(
            f"{source.name} is {info.hdr.upper()} HDR and this ffmpeg has no tone-map filter",
            hint="install an ffmpeg with zscale, scale_vt or colorspace",
        )
    for index, method in enumerate(methods):
        chain = {"scale_vt": SCALE_VT_CHAIN, "zscale": ZSCALE_CHAIN}.get(method, COLORSPACE_CHAIN)
        try:
            _encode(source, dest, [*base, chain], fps, caps, info.has_audio, progress, hw=method)
        except FFmpegError as exc:
            if index == len(methods) - 1:
                raise
            warnings.append(f"{source.name}: {method} tone-map failed ({_last(exc)}); retrying")
            continue
        if method == "colorspace":
            warnings.append(
                f"{source.name}: {info.hdr.upper()} converted with colorspace, which does not "
                "tone-map; highlights may clip (no scale_vt or zscale in this ffmpeg)"
            )
        return Mezzanine(dest, width, height, method, tuple(warnings))
    raise AssertionError("unreachable")


def _last(exc: FFmpegError) -> str:
    return exc.stderr_tail[-1].strip() if exc.stderr_tail else f"exit {exc.returncode}"


def _encode(
    source: Path,
    dest: Path,
    filters: list[str],
    fps: int,
    caps: FFmpegCaps,
    has_audio: bool,
    progress: Callable[[float], None] | None,
    *,
    hw: Tonemap | None = None,
) -> None:
    args: list[str | Path] = ["-y", "-loglevel", "error"]
    if hw == "scale_vt":
        args += ["-init_hw_device", "videotoolbox=vt", "-filter_hw_device", "vt"]
    args += ["-i", source, "-map", "0:v:0", "-vf", ",".join(filters)]
    args += [caps.fps_mode_option, "cfr", "-r", str(fps)]
    args += ["-c:v", "libx264", "-profile:v", "high", "-preset", "fast", "-crf", str(CRF)]
    args += ["-g", str(fps), "-pix_fmt", "yuv420p", *(BT709_TAGS if hw else [])]
    if has_audio:
        # Kept for reference only; later stages read the enhanced WAV.
        args += ["-map", "0:a:0", "-c:a", "aac", "-b:a", "192k"]
    tmp = dest.with_name(f".{dest.name}")
    args += ["-map_metadata", "-1", "-movflags", "+faststart", tmp]
    run_ffmpeg(args, progress=progress)
    tmp.replace(dest)


HEIF_EXTENSIONS = frozenset({".heic", ".heif"})
HEIF_HINT = (
    "install libheif's heif-convert (`brew install libheif`, `apt install libheif-examples`)"
)
HEIF_TIMEOUT_S = 120


def heif_decoder() -> str | None:
    """The tool that turns HEIC/HEIF into PNG here: macOS's sips, else libheif's heif-convert.

    Pillow cannot read HEIF, and the pillow-heif wheels bundle the GPL x265 encoder.
    """
    if platform.system() == "Darwin" and shutil.which("sips"):
        return "sips"
    if shutil.which("heif-convert"):
        return "heif-convert"
    return None


def decode_heif(source: Path, dest: Path) -> None:
    """Write `source` as the PNG `dest`."""
    decoder = heif_decoder()
    if decoder is None:
        raise DependencyError(f"nothing on this machine can decode {source.name}", hint=HEIF_HINT)
    if decoder == "sips":
        argv = ["sips", "-s", "format", "png", str(source), "--out", str(dest)]
    else:
        argv = ["heif-convert", str(source), str(dest)]
    try:
        result = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=HEIF_TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise UserError(f"{decoder} timed out decoding {source.name}") from exc
    if result.returncode != 0 or not dest.is_file():
        tail = (result.stderr or result.stdout).strip().splitlines()[-1:] or [""]
        raise UserError(
            f"cannot decode {source.name} with {decoder}: {tail[0]}",
            hint="export it as JPEG and put that in raw/ instead",
        )


def normalise_image(source: Path, dest_stem: Path) -> tuple[Path, int, int]:
    """Apply EXIF orientation, fit within 4096 px and convert to sRGB; PNG keeps alpha.

    HEIC and HEIF are decoded to PNG first; sips keeps the orientation as an EXIF tag on raw pixels.
    """
    decoded: Path | None = None
    if source.suffix.lower() in HEIF_EXTENSIONS:
        decoded = dest_stem.with_name(f".{dest_stem.name}.decoded.png")
        decode_heif(source, decoded)
    try:
        with Image.open(decoded or source) as opened:
            image = ImageOps.exif_transpose(opened)
            icc = opened.info.get("icc_profile")
            fmt = opened.format
    except OSError as exc:
        raise UserError(
            f"cannot read image {source.name}: {exc}",
            hint="convert it to JPEG or PNG and put that in raw/ instead",
        ) from exc
    finally:
        if decoded is not None:
            decoded.unlink(missing_ok=True)
    if icc:
        image = _to_srgb(image, icc)
    has_alpha = image.mode in ("RGBA", "LA", "PA") or "transparency" in image.info
    image = image.convert("RGBA" if has_alpha else "RGB")
    width, height = output_size(*image.size, max_side=MAX_IMAGE_SIDE)
    if (width, height) != image.size and max(image.size) > MAX_IMAGE_SIDE:
        image = image.resize((width, height), Image.Resampling.LANCZOS)
    jpeg = fmt == "JPEG" and not has_alpha
    dest = dest_stem.with_suffix(".jpg" if jpeg else ".png")
    tmp = dest.with_name(f".{dest.name}")
    if jpeg:
        image.save(tmp, "JPEG", quality=95)
    else:
        image.save(tmp, "PNG")
    tmp.replace(dest)
    return dest, *image.size


def _to_srgb(image: Image.Image, icc: bytes) -> Image.Image:
    try:
        source_profile = ImageCms.ImageCmsProfile(io.BytesIO(icc))
        srgb = ImageCms.createProfile("sRGB")
        mode = "RGBA" if image.mode in ("RGBA", "LA", "PA") else "RGB"
        converted = ImageCms.profileToProfile(image.convert(mode), source_profile, srgb)
    except (ImageCms.PyCMSError, OSError):
        return image
    return converted if converted is not None else image
