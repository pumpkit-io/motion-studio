"""Workspace discovery, project paths and cache directories."""

import os
import re
from dataclasses import dataclass
from pathlib import Path

import platformdirs

from reelcut import APP_NAME
from reelcut.errors import UserError

WORKSPACE_FILE = f"{APP_NAME}.toml"
PROJECTS_DIR = "projects"
CACHE_ENV = f"{APP_NAME.upper()}_CACHE_DIR"

SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def find_workspace(start: Path | None = None) -> Path:
    """Walk up from `start` (default: cwd) to the first directory holding the workspace file."""
    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / WORKSPACE_FILE).is_file():
            return candidate
    raise UserError(
        f"no {WORKSPACE_FILE} found in {here} or any parent directory",
        hint=f"run `{APP_NAME} init <dir>` and work inside that workspace",
    )


def validate_slug(slug: str) -> str:
    if not SLUG_PATTERN.fullmatch(slug):
        raise UserError(
            f"invalid project slug {slug!r}",
            hint="use lowercase letters, digits and hyphens, starting with a letter or digit",
        )
    return slug


@dataclass(frozen=True)
class ProjectPaths:
    """Every path in one project; the layout is guide §5."""

    workspace: Path
    slug: str

    @property
    def root(self) -> Path:
        return self.workspace / PROJECTS_DIR / self.slug

    @property
    def project_toml(self) -> Path:
        return self.root / "project.toml"

    @property
    def raw(self) -> Path:
        return self.root / "raw"

    @property
    def media(self) -> Path:
        return self.root / "media"

    @property
    def analysis(self) -> Path:
        return self.root / "analysis"

    @property
    def contact(self) -> Path:
        return self.root / "contact"

    @property
    def edl(self) -> Path:
        return self.root / "edl.json"

    @property
    def build(self) -> Path:
        return self.root / "build"

    @property
    def preview(self) -> Path:
        return self.root / "preview"

    @property
    def check(self) -> Path:
        return self.root / "check"

    @property
    def final(self) -> Path:
        return self.root / "final"

    @property
    def notes(self) -> Path:
        return self.root / "notes.md"

    @property
    def state(self) -> Path:
        return self.root / "state.json"

    @property
    def lock(self) -> Path:
        return self.root / ".lock"

    @property
    def hash_cache(self) -> Path:
        return self.root / ".hashes.json"

    @property
    def directories(self) -> tuple[Path, ...]:
        return (
            self.raw,
            self.media,
            self.analysis,
            self.contact,
            self.build,
            self.preview,
            self.check,
            self.final,
        )

    def asset_sheet(self, clip_id: str) -> Path:
        """The contact sheet of one B-roll clip or image, which assets.md links to."""
        return self.contact / f"{clip_id}.png"

    def require(self) -> "ProjectPaths":
        """Return self, or fail with a user error when the project does not exist."""
        if not self.project_toml.is_file():
            raise UserError(
                f"no project {self.slug!r} in {self.workspace / PROJECTS_DIR}",
                hint=f"run `{APP_NAME} new {self.slug} --from <files>`",
            )
        return self


def project_paths(workspace: Path, slug: str) -> ProjectPaths:
    return ProjectPaths(workspace, validate_slug(slug))


def cache_dir() -> Path:
    """The machine-wide cache shared by every workspace and worktree.

    platformdirs' user cache dir (`~/Library/Caches/<app>` on macOS, `~/.cache/<app>` on Linux),
    unless the cache env var points elsewhere.
    """
    override = os.environ.get(CACHE_ENV)
    path = Path(override) if override else platformdirs.user_cache_path(APP_NAME)
    path.mkdir(parents=True, exist_ok=True)
    return path


def models_dir() -> Path:
    return cache_dir() / "models"


def envs_dir() -> Path:
    return cache_dir() / "envs"


def renderer_dir() -> Path:
    return cache_dir() / "renderer"


def locks_dir() -> Path:
    path = cache_dir() / "locks"
    path.mkdir(parents=True, exist_ok=True)
    return path
