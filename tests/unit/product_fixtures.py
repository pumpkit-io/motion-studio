"""A product workspace with one synthetic screen recording and its markers sidecar.

Stands in for a `record web` take: a solid-colour clip, so stills show where the footage is.
"""

import json
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from motion_studio.cli import app
from motion_studio.media.ffmpeg import run_ffmpeg

FOOTAGE_RGB = (46, 160, 67)
MARKERS = {"open": 0.5, "typed": 2.5, "done": 4.5}

runner = CliRunner()


def run_json(*args: str | Path) -> dict[str, Any]:
    result = runner.invoke(app, [*(str(a) for a in args), "--json"])
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


def recording(path: Path, width: int, height: int, duration: float = 5.0) -> Path:
    colour = "0x{:02X}{:02X}{:02X}".format(*FOOTAGE_RGB)
    source = f"color=c={colour}:size={width}x{height}:rate=30:duration={duration}"
    run_ffmpeg(["-f", "lavfi", "-i", source, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-y", path])
    sidecar = {
        "schema_version": 1,
        "width": width,
        "height": height,
        "markers": [{"name": n, "t": t} for n, t in MARKERS.items()],
    }
    path.with_suffix(".markers.json").write_text(json.dumps(sidecar), encoding="utf-8")
    return path


def product_project(workspace: Path, scratch: Path, width: int = 320, height: int = 180) -> Path:
    """`launch`, ingested and analysed, from a recording `width` by `height`."""
    clip = recording(scratch / "take.mp4", width, height)
    run_json("new", "launch", "--kind", "product", "--from", clip)
    project = workspace / "projects" / "launch"
    (project / "raw" / "take.markers.json").write_text(
        clip.with_suffix(".markers.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    run_json("ingest", "launch")
    run_json("analyze", "launch")
    return project


EDL: dict[str, Any] = {
    "kind": "product",
    "title": "Launch",
    "scenes": [
        {"id": "intro", "type": "title_card", "beats": 4, "headline": "Meet the app."},
        {
            "id": "step1",
            "type": "title_card",
            "beats": 4,
            "step": "01",
            "headline": "Pick who inspires you.",
            "accent": ["inspires"],
            "subline": "Up to three authors.",
        },
        {
            "id": "pick",
            "type": "footage",
            "clip": "c1",
            "from": "c1.m.open",
            "to": "c1.m.done",
            "beats": 8,
            "address": "example.com",
        },
    ],
    "music": {"mode": "none"},
    "rationale": "Intro, a numbered step, then its footage.",
}


def write_edl(project: Path, edl: dict[str, Any] = EDL) -> None:
    (project / "edl.json").write_text(json.dumps(edl), encoding="utf-8")
