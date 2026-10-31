"""`record web`: run a recording script in headless Chromium and add the take to raw/.

Node runs the script against the helper library (`node/studio.mjs`) and leaves JPEG
screencast frames with their timestamps, the markers and the cursor track in a scratch
directory. This module lays the frames on a constant-frame-rate grid, encodes them, writes the
markers sidecar, then moves both into raw/. A failed take leaves nothing in raw/.
"""

import bisect
import json
import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PIL import Image
from pydantic import ValidationError

from motion_studio.analysis.models import CursorSample, Element, Marker, ScreenMarkers
from motion_studio.errors import InternalError, UserError
from motion_studio.media.ffmpeg import binary, run_ffmpeg
from motion_studio.record.install import NODE_DIR, browser_env, find_recorder, node_binary
from motion_studio.record.take import (
    Take,
    log_take,
    place_take,
    product_project,
    refuse_existing,
    refuse_while_heavy,
    scratch_take,
    take_stem,
)

DEFAULT_VIEWPORT = (1600, 900)
FPS = 30
JPEG_QUALITY = 95
SCRIPT_TIMEOUT_S = 1800


def record_web(
    workspace: Path,
    slug: str,
    script: Path,
    *,
    name: str | None = None,
    viewport: tuple[int, int] = DEFAULT_VIEWPORT,
    on_step: Callable[[str], None] | None = None,
) -> Take:
    step = on_step or (lambda _msg: None)
    project = product_project(workspace, slug, "record web")
    script = script.expanduser().resolve()
    if not script.is_file():
        raise UserError(f"no recording script at {script}", hint="pass the path of a .mjs file")
    stem = take_stem(name, script)
    refuse_existing(project, stem)
    root = find_recorder()
    node = node_binary()
    binary("ffmpeg")
    refuse_while_heavy(project)

    with scratch_take(project, stem) as scratch:
        step(f"running {script.name} in headless Chromium")
        _run_script(node, root, script, scratch, viewport)
        take = json.loads((scratch / "take.json").read_text(encoding="utf-8"))
        step("encoding the frames")
        return log_take(project, stem, _encode(take, scratch, project.raw, stem))


def _run_script(
    node: str, root: Path, script: Path, scratch: Path, viewport: tuple[int, int]
) -> None:
    config = scratch / "config.json"
    config.write_text(
        json.dumps(
            {
                "script": str(script),
                "out": str(scratch),
                "width": viewport[0],
                "height": viewport[1],
                "quality": JPEG_QUALITY,
                "playwright": str(root),
            }
        ),
        encoding="utf-8",
    )
    try:
        proc = subprocess.run(
            [node, str(NODE_DIR / "runner.mjs"), str(config)],
            cwd=script.parent,
            env=browser_env(root),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=SCRIPT_TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise UserError(
            f"{script.name} ran for more than {SCRIPT_TIMEOUT_S // 60} minutes",
            hint="make the script end; nothing was added to raw/",
        ) from exc
    tail = "\n".join(proc.stderr.strip().splitlines()[-20:])
    if proc.returncode == 1:
        raise UserError(
            f"{script.name} failed:\n{tail}",
            hint="fix the script and record again; nothing was added to raw/",
        )
    if proc.returncode != 0:
        raise InternalError(f"the web recorder exited with code {proc.returncode}:\n{tail}")


def _encode(take: dict[str, Any], scratch: Path, raw: Path, stem: str) -> Take:
    frames: list[dict[str, Any]] = take["frames"]
    t0 = float(frames[0]["t"])
    end = max(float(take["end"]), float(frames[-1]["t"]) + 1 / FPS)
    with Image.open(scratch / frames[0]["file"]) as first:
        width, height = first.size
    # The screencast can send frames smaller than the viewport; boxes follow the frames.
    sx = width / take["viewport"]["width"]
    sy = height / take["viewport"]["height"]

    # Each output frame shows the last screencast frame sent by its time. The screencast only
    # sends a frame when the page changes, so a still page holds its frame for as long as it lasts.
    times = [float(f["t"]) for f in frames]
    count = max(1, round((end - t0) * FPS))
    sequence = scratch / "cfr"
    sequence.mkdir()
    for k in range(count):
        index = max(bisect.bisect_right(times, t0 + k / FPS) - 1, 0)
        os.link(scratch / frames[index]["file"], sequence / f"{k:06d}.jpg")
    encoded = scratch / "take.mp4"
    run_ffmpeg(
        [
            "-framerate", str(FPS), "-i", sequence / "%06d.jpg",
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p",
            "-c:v", "libx264", "-preset", "slow", "-crf", "12", "-r", str(FPS),
            "-movflags", "+faststart", "-an", "-y", encoded,
        ]
    )  # fmt: skip

    duration = round(count / FPS, 3)

    def clock(t: float) -> float:
        return round(min(max(float(t) - t0, 0.0), duration), 3)

    warnings: list[str] = []

    def elements(marker: dict[str, Any]) -> list[Element]:
        kept: list[Element] = []
        for e in marker["elements"]:
            w, h = round(e["w"] * sx, 1), round(e["h"] * sy, 1)
            if w <= 0 or h <= 0:
                warnings.append(
                    f"marker {marker['name']}: element {e['name']} has a {w}x{h} box, so it was "
                    "left out; mark it while it is visible"
                )
                continue
            kept.append(
                Element(name=e["name"], x=round(e["x"] * sx, 1), y=round(e["y"] * sy, 1), w=w, h=h)
            )
        return kept

    try:
        markers = ScreenMarkers(
            width=width,
            height=height,
            markers=[
                Marker(name=m["name"], t=clock(m["t"]), elements=elements(m))
                for m in take["markers"]
            ],
            cursor=_cursor(take["cursor"], t0, clock, sx, sy),
        )
    except ValidationError as exc:
        raise UserError(f"the take's markers do not validate: {exc}") from exc
    clip, sidecar = place_take(raw, stem, encoded, markers, scratch)
    return Take(
        clip=clip,
        sidecar=sidecar,
        duration_s=duration,
        width=width,
        height=height,
        fps=FPS,
        frames=count,
        markers=[m.name for m in markers.markers],
        warnings=warnings,
    )


def _cursor(
    samples: list[dict[str, Any]],
    t0: float,
    clock: Callable[[float], float],
    sx: float,
    sy: float,
) -> list[CursorSample]:
    """The track on the clip's clock; of the samples before the first frame, only the last."""
    before = [s for s in samples if float(s["t"]) < t0]
    kept = before[-1:] + [s for s in samples if float(s["t"]) >= t0]
    return [
        CursorSample(
            t=clock(s["t"]), x=round(s["x"] * sx, 1), y=round(s["y"] * sy, 1), down=s["down"]
        )
        for s in kept
    ]
