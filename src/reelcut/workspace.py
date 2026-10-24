"""Create workspaces and projects, report project status, and clean caches."""

import json
import os
import shutil
from dataclasses import dataclass
from importlib.resources import as_file, files
from pathlib import Path
from typing import Any

import tomli_w

from reelcut import APP_NAME
from reelcut.agents import TARGETS, sync_skills
from reelcut.config import load_config
from reelcut.errors import UserError
from reelcut.paths import WORKSPACE_FILE, ProjectPaths, project_paths
from reelcut.state import STAGES, State, load_state, project_lock, save_state, stage_status
from reelcut.target import RenderTarget

PLACEHOLDER = ".gitkeep"


def init_workspace(target: Path) -> list[Path]:
    """Copy the workspace template and every agent's skills into `target`.

    Returns the files and skill folders written.
    """
    target = target.expanduser().resolve()
    if (target / WORKSPACE_FILE).exists():
        raise UserError(f"{target} is already a workspace ({WORKSPACE_FILE} exists)")
    written: list[Path] = []
    with as_file(files("reelcut") / "templates" / "workspace") as template:
        sources = sorted(p for p in template.rglob("*") if p.is_file())
        conflicts = [
            target / p.relative_to(template)
            for p in sources
            if p.name != PLACEHOLDER and (target / p.relative_to(template)).exists()
        ]
        if conflicts:
            raise UserError(
                f"refusing to overwrite {', '.join(str(c) for c in conflicts)}",
                hint="pick an empty directory",
            )
        for source in sources:
            dest = target / source.relative_to(template)
            dest.parent.mkdir(parents=True, exist_ok=True)
            if source.name == PLACEHOLDER:
                continue
            shutil.copyfile(source, dest)
            written.append(dest)
    return written + sync_skills(target, list(TARGETS))


def new_project(
    workspace: Path, slug: str, sources: list[Path], *, title: str | None = None
) -> tuple[ProjectPaths, list[Path]]:
    """Create the project tree and hard-link (or copy) `sources` into raw/.

    A directory source contributes its visible top-level files. Nothing is created when a
    source is missing or two files would share a name in raw/.
    """
    project = project_paths(workspace, slug)
    if project.root.exists():
        raise UserError(
            f"project {slug!r} already exists at {project.root}",
            hint=f"copy more clips into {project.raw}, or pick another slug",
        )
    clips = _collect(sources)
    project.root.mkdir(parents=True)
    for directory in project.directories:
        directory.mkdir()
    meta: dict[str, Any] = {"project": {"title": title or slug}, "clips": {}}
    project.project_toml.write_text(tomli_w.dumps(meta), encoding="utf-8")
    project.notes.write_text(f"# Notes: {title or slug}\n", encoding="utf-8")
    save_state(project, State())
    return project, [_link_or_copy(clip, project.raw / clip.name) for clip in clips]


def _collect(sources: list[Path]) -> list[Path]:
    clips: list[Path] = []
    for source in sources:
        if source.is_dir():
            clips += sorted(
                p for p in source.iterdir() if p.is_file() and not p.name.startswith(".")
            )
        elif source.is_file():
            clips.append(source)
        else:
            raise UserError(f"no such file or directory: {source}")
    names = [c.name for c in clips]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    if duplicates:
        raise UserError(f"two sources share the name {', '.join(duplicates)}; rename one")
    return clips


def _link_or_copy(source: Path, dest: Path) -> Path:
    try:
        os.link(source, dest)
    except OSError:
        shutil.copy2(source, dest)
    return dest


@dataclass(frozen=True)
class StageLine:
    name: str
    status: str
    finished_at: str | None


@dataclass(frozen=True)
class ProjectStatus:
    slug: str
    clips: int
    stages: list[StageLine]
    next: str | None
    hint: str | None

    def to_json(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "clips": self.clips,
            "stages": [s.__dict__ for s in self.stages],
            "next": self.next,
            "hint": self.hint,
        }


def project_status(workspace: Path, slug: str) -> ProjectStatus:
    project = project_paths(workspace, slug).require()
    config = load_config(workspace, slug)
    state = load_state(project)
    clips = sum(1 for p in project.raw.iterdir() if not p.name.startswith("."))
    lines: list[StageLine] = []
    for stage in STAGES:
        status = (
            "skipped"
            if stage == "music" and config.music.mode == "none"
            else stage_status(project, stage)
        )
        record = state.stages.get(stage)
        finished = record.finished_at.isoformat() if record and record.finished_at else None
        lines.append(StageLine(stage, status, finished))
    if clips == 0:
        return ProjectStatus(slug, 0, lines, None, f"copy clips into {project.raw}")
    todo = next((line.name for line in lines if line.status not in ("done", "skipped")), None)
    command = _next_command(project, todo) if todo else None
    return ProjectStatus(slug, clips, lines, command, None if command else "all stages are done")


def _next_command(project: ProjectPaths, stage: str) -> str:
    slug = project.slug
    commands = {
        "ingest": f"ingest {slug}",
        "analyze": f"analyze {slug}",
        "plan": f"plan validate {slug}" if project.edl.exists() else f"plan draft {slug}",
        "music": f"music {slug}",
        RenderTarget.PREVIEW.stage: f"render {slug} {RenderTarget.PREVIEW.flag}",
        RenderTarget.PREVIEW.check_record: f"check {slug} {RenderTarget.PREVIEW.flag}",
        RenderTarget.FINAL.stage: f"render {slug} {RenderTarget.FINAL.flag}",
    }
    return f"{APP_NAME} {commands[stage]}"


def read_edl_policy(project: ProjectPaths) -> dict[str, Any] | None:
    """The EDL's `policy` object, read loosely: the EDL ticket owns full validation."""
    if not project.edl.exists():
        return None
    try:
        data = json.loads(project.edl.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise UserError(f"{project.edl} is not valid JSON: {exc}") from exc
    policy = data.get("policy") if isinstance(data, dict) else None
    return policy if isinstance(policy, dict) else None


def clean_project(project: ProjectPaths, *, everything: bool) -> list[Path]:
    """Empty cache directories and return what was removed. raw/ is never touched.

    Without `everything`, analysis, contact sheets, checks, finals, the EDL and notes stay.
    """
    project.require()
    dirs = [project.media, project.build, project.preview]
    files_ = []
    if everything:
        dirs += [project.analysis, project.contact, project.check, project.final]
        files_ = [project.edl, project.notes, project.state]
    removed: list[Path] = []
    with project_lock(project):
        for directory in dirs:
            if directory.exists():
                for child in sorted(directory.iterdir()):
                    if child.is_dir() and not child.is_symlink():
                        shutil.rmtree(child)
                    else:
                        child.unlink()
                    removed.append(child)
            directory.mkdir(exist_ok=True)
        for file in files_:
            if file.exists():
                file.unlink()
                removed.append(file)
    return removed
