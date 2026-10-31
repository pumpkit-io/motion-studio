"""What every recorder shares: the checks before a take, its scratch directory, and the result.

A take is built in `build/record/<name>.partial/` and only its finished clip and sidecar are
moved into raw/, so a failed take leaves nothing there.
"""

import os
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from motion_studio import APP_NAME
from motion_studio.analysis.models import ScreenMarkers
from motion_studio.errors import UserError
from motion_studio.kind import ProjectKind, require_kind
from motion_studio.paths import ProjectPaths, project_paths
from motion_studio.state import ensure_free_disk, heavy_model_holder, project_lock


@dataclass(frozen=True)
class Take:
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


def product_project(workspace: Path, slug: str, command: str) -> ProjectPaths:
    project = project_paths(workspace, slug).require()
    require_kind(
        project,
        ProjectKind.PRODUCT,
        command,
        hint=f"record into a product project: `{APP_NAME} new <slug> --kind product`",
    )
    return project


def refuse_existing(project: ProjectPaths, stem: str) -> None:
    for existing in (project.raw / f"{stem}.mp4", project.raw / f"{stem}.markers.json"):
        if existing.exists():
            raise UserError(
                f"{existing} already exists",
                hint="pass --name <other> for a new take, or delete the old one first",
            )


def refuse_while_heavy(project: ProjectPaths) -> None:
    """Recording never takes the heavy-model lock, but a busy machine would drop frames."""
    holder = heavy_model_holder()
    if holder is not None:
        raise UserError(
            f"a heavy model is running ({holder}); it would make the recording drop frames",
            hint="wait for it to finish, then record again",
        )
    ensure_free_disk(project.root)


@contextmanager
def scratch_take(project: ProjectPaths, stem: str) -> Iterator[Path]:
    """The take's scratch directory under the project lock, removed however the take ends."""
    with project_lock(project):
        scratch = project.build / "record" / f"{stem}.partial"
        shutil.rmtree(scratch, ignore_errors=True)
        scratch.mkdir(parents=True)
        try:
            yield scratch
        finally:
            shutil.rmtree(scratch, ignore_errors=True)


def place_take(
    raw: Path, stem: str, encoded: Path, markers: ScreenMarkers, scratch: Path
) -> tuple[Path, Path]:
    """Move the encoded clip and its sidecar into raw/, the sidecar first."""
    written = scratch / "take.markers.json"
    written.write_text(markers.model_dump_json(indent=2) + "\n", encoding="utf-8")
    clip = raw / f"{stem}.mp4"
    sidecar = raw / f"{stem}.markers.json"
    raw.mkdir(parents=True, exist_ok=True)
    os.replace(written, sidecar)
    os.replace(encoded, clip)
    return clip, sidecar
