"""Compose: write the Remotion props and public directory, then render one format with the CLI."""

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from motion_studio.edl import Timeline
from motion_studio.errors import InternalError
from motion_studio.render.assemble import Canvas
from motion_studio.render.renderer import remotion_bin

FONT_SUFFIXES = (".ttf", ".otf", ".woff2", ".woff")
FONTS_DIR = Path("library") / "brand" / "fonts"
DEFAULT_FONT = "Inter"
PREVIEW_SCALE = 0.5
FINAL_CRF = 16
PREVIEW_CRF = 23


@dataclass(frozen=True)
class Brand:
    """The brand files a render uses; None means the renderer's built-in look."""

    font: Path | None
    logo: Path | None
    warnings: tuple[str, ...]


def find_brand(timeline: Timeline, workspace: Path, default_logo: str) -> Brand:
    """Resolve the caption font and logo named in the timeline to files in the workspace.

    `captions.font` is "Inter" (bundled), a font file path relative to the workspace, or a family
    name matched against the file names in `library/brand/fonts`. A missing default logo is not
    worth a warning: most workspaces have no logo.
    """
    warnings: list[str] = []
    font = _find_font(timeline.captions.font, workspace)
    if font is None and timeline.captions.font.casefold() != DEFAULT_FONT.casefold():
        warnings.append(
            f"caption font {timeline.captions.font!r} not found in {workspace / FONTS_DIR}; "
            f"captions use the bundled {DEFAULT_FONT}"
        )
    logo: Path | None = None
    if timeline.brand.logo:
        candidate = workspace / timeline.brand.logo
        if candidate.is_file():
            logo = candidate
        elif timeline.brand.logo != default_logo:
            warnings.append(f"brand logo {candidate} not found; rendering without a logo")
    return Brand(font=font, logo=logo, warnings=tuple(warnings))


def _find_font(name: str, workspace: Path) -> Path | None:
    if name.casefold() == DEFAULT_FONT.casefold():
        return None
    if "/" in name or name.lower().endswith(FONT_SUFFIXES):
        path = workspace / name
        return path if path.is_file() else None
    fonts = workspace / FONTS_DIR
    if not fonts.is_dir():
        return None
    wanted = _key(name)
    files = sorted(p for p in fonts.iterdir() if p.suffix.lower() in FONT_SUFFIXES)
    exact = [p for p in files if _key(p.stem) == wanted]
    # A family name also matches its styled files, such as "Montserrat-Bold.ttf".
    prefixed = [p for p in files if _key(p.stem).startswith(wanted)]
    return (exact or prefixed or [None])[0]


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.casefold())


def prepare_public(
    build: Path, assembled: Path, timeline: Timeline, project_root: Path, brand: Brand
) -> Path:
    """Fill `build/public/` with everything the composition loads through `staticFile()`."""
    public = build / "public"
    shutil.rmtree(public, ignore_errors=True)
    public.mkdir(parents=True)
    _link(assembled, public / assembled.name)
    for event in timeline.events:
        src = getattr(event, "src", None)
        if src is not None and not (public / src).exists():
            _link(project_root / src, public / src)
    if brand.font is not None:
        _link(brand.font, public / "brand" / f"font{brand.font.suffix.lower()}")
    if brand.logo is not None:
        _link(brand.logo, public / "brand" / f"logo{brand.logo.suffix.lower()}")
    return public


def _link(source: Path, target: Path) -> None:
    """Hard-link when on the same volume; copy otherwise."""
    if not source.is_file():
        raise InternalError(f"{source} is missing; run the earlier stages again")
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


def props(timeline: Timeline, fmt: str, canvas: Canvas, video: str, brand: Brand) -> dict[str, Any]:
    data = timeline.model_dump(mode="json")
    font_file = logo_file = None
    if brand.font is not None:
        font_file = f"brand/font{brand.font.suffix.lower()}"
        # A plain family name keeps CSS happy whatever the configured value looks like.
        data["captions"]["font"] = "Brand" + _key(brand.font.stem).capitalize()
    if brand.logo is not None:
        logo_file = f"brand/logo{brand.logo.suffix.lower()}"
    return {
        "timeline": data,
        "format": fmt,
        "source": {"width": canvas.width, "height": canvas.height},
        "regions": {clip: r.to_json() for clip, r in canvas.regions.items()},
        "video": video,
        "font_file": font_file,
        "logo_file": logo_file,
    }


def compose(
    renderer: Path,
    props_data: dict[str, Any],
    build: Path,
    public: Path,
    *,
    preview: bool,
    concurrency: int,
) -> Path:
    """Render `build/composed_<fmt>.mp4` with the Remotion CLI; previews at half size."""
    fmt = props_data["format"]
    props_path = build / f"props_{fmt}.json"
    props_path.write_text(json.dumps(props_data, indent=2, ensure_ascii=False), encoding="utf-8")
    out = build / f"composed_{fmt}.mp4"
    argv = [
        str(remotion_bin(renderer)),
        "render",
        "src/index.ts",
        "Reel",
        str(out),
        f"--props={props_path}",
        f"--public-dir={public}",
        f"--concurrency={concurrency}",
        "--codec=h264",
        f"--crf={PREVIEW_CRF if preview else FINAL_CRF}",
        "--log=error",
    ]
    if preview:
        argv.append(f"--scale={PREVIEW_SCALE}")
    result = subprocess.run(
        argv, cwd=renderer, stdin=subprocess.DEVNULL, capture_output=True, text=True, check=False
    )
    if result.returncode != 0 or not out.is_file():
        tail = "\n".join((result.stdout + result.stderr).splitlines()[-20:])
        raise InternalError(f"the Remotion render of {fmt} failed:\n{tail}")
    return out
