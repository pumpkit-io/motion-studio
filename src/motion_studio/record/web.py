"""`record web`: run a recording script in headless Chromium and add the take to raw/.

Node runs the script against the helper library (`node/studio.mjs`) and leaves JPEG
screencast frames with their timestamps, the markers and the cursor track in a scratch
directory. This module lays the frames on a constant-frame-rate grid, encodes them, writes the
markers sidecar, then moves both into raw/. A failed take leaves nothing in raw/.
"""

import bisect
import json
import os
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image
from pydantic import ValidationError

from motion_studio import APP_NAME
from motion_studio.analysis.models import CursorSample, Element, Marker, ScreenMarkers
from motion_studio.errors import InternalError, UserError
from motion_studio.kind import ProjectKind, require_kind
from motion_studio.media.ffmpeg import binary, run_ffmpeg
from motion_studio.paths import project_paths
from motion_studio.record.install import NODE_DIR, browser_env, find_recorder, node_binary
from motion_studio.state import ensure_free_disk, heavy_model_holder, project_lock

DEFAULT_VIEWPORT = (1600, 900)
FPS = 30
JPEG_QUALITY = 95
SCRIPT_TIMEOUT_S = 1800


@dataclass(frozen=True)
class WebTake:
    clip: Path
    sidecar: Path
    duration_s: float
    width: int
    height: int
    fps: int
    frames: int
    markers: list[str]

    def to_json(self) -> dict[str, Any]:
        return {
            "clip": str(self.clip),
            "sidecar": str(self.sidecar),
            "duration_s": self.duration_s,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "frames": self.frames,
            "markers": self.markers,
        }


def record_web(
    workspace: Path,
    slug: str,
    script: Path,
    *,
    name: str | None = None,
    viewport: tuple[int, int] = DEFAULT_VIEWPORT,
    on_step: Callable[[str], None] | None = None,
) -> WebTake:
    step = on_step or (lambda _msg: None)
    project = project_paths(workspace, slug).require()
    require_kind(
        project,
        ProjectKind.PRODUCT,
        "record web",
        hint=f"record into a product project: `{APP_NAME} new <slug> --kind product`",
    )
    script = script.expanduser().resolve()
    if not script.is_file():
        raise UserError(f"no recording script at {script}", hint="pass the path of a .mjs file")
    stem = name or script.stem
    clip = project.raw / f"{stem}.mp4"
    sidecar = project.raw / f"{stem}.markers.json"
    for existing in (clip, sidecar):
        if existing.exists():
            raise UserError(
                f"{existing} already exists",
                hint="pass --name <other> for a new take, or delete the old one first",
            )
    root = find_recorder()
    node = node_binary()
    binary("ffmpeg")
    holder = heavy_model_holder()
    if holder is not None:
        raise UserError(
            f"a heavy model is running ({holder}); it would make the recording drop frames",
            hint="wait for it to finish, then record again",
        )
    ensure_free_disk(project.root)

    with project_lock(project):
        scratch = project.build / "record" / f"{stem}.partial"
        shutil.rmtree(scratch, ignore_errors=True)
        scratch.mkdir(parents=True)
        try:
            step(f"running {script.name} in headless Chromium")
            _run_script(node, root, script, scratch, viewport)
            take = json.loads((scratch / "take.json").read_text(encoding="utf-8"))
            step("encoding the frames")
            result = _encode(take, scratch, project.raw, stem)
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
    return result


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


def _encode(take: dict[str, Any], scratch: Path, raw: Path, stem: str) -> WebTake:
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

    try:
        markers = ScreenMarkers(
            width=width,
            height=height,
            markers=[
                Marker(
                    name=m["name"],
                    t=clock(m["t"]),
                    elements=[
                        Element(
                            name=e["name"],
                            x=round(e["x"] * sx, 1),
                            y=round(e["y"] * sy, 1),
                            w=round(e["w"] * sx, 1),
                            h=round(e["h"] * sy, 1),
                        )
                        for e in m["elements"]
                    ],
                )
                for m in take["markers"]
            ],
            cursor=_cursor(take["cursor"], t0, clock, sx, sy),
        )
    except ValidationError as exc:
        raise UserError(f"the take's markers do not validate: {exc}") from exc
    written = scratch / "take.markers.json"
    written.write_text(markers.model_dump_json(indent=2) + "\n", encoding="utf-8")

    clip = raw / f"{stem}.mp4"
    sidecar = raw / f"{stem}.markers.json"
    raw.mkdir(parents=True, exist_ok=True)
    os.replace(written, sidecar)
    os.replace(encoded, clip)
    return WebTake(
        clip=clip,
        sidecar=sidecar,
        duration_s=duration,
        width=width,
        height=height,
        fps=FPS,
        frames=len(frames),
        markers=[m.name for m in markers.markers],
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
