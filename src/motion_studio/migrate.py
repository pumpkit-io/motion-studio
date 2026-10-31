"""Recognise what the product's previous name left behind: workspaces, caches, env variables.

Nothing here moves the cache: it can hold 16 GB, so the CLI prints the command instead.
"""

import os
import shlex
import shutil
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import platformdirs

from motion_studio import APP_NAME, ENV_PREFIX
from motion_studio.agents import TARGETS
from motion_studio.errors import UserError
from motion_studio.paths import CACHE_ENV, WORKSPACE_FILE

# The one place outside CHANGELOG that keeps the old name; see docs/renaming.md.
OLD_APP_NAME = "reelcut"
OLD_WORKSPACE_FILE = f"{OLD_APP_NAME}.toml"
OLD_ENV_PREFIX = OLD_APP_NAME.upper().replace("-", "_")

SYNC_HINT = f"run `{APP_NAME} agents sync` in the workspace to migrate it"


def unmigrated_error(workspace: Path) -> UserError:
    return UserError(
        f"{workspace / OLD_WORKSPACE_FILE} is a workspace from before the rename to {APP_NAME}",
        hint=SYNC_HINT,
    )


@dataclass(frozen=True)
class Migration:
    renamed: list[tuple[Path, Path]] = field(default_factory=lambda: list[tuple[Path, Path]]())
    removed: list[Path] = field(default_factory=lambda: list[Path]())


def migrate_workspace(workspace: Path) -> Migration:
    """Rename the old workspace file and delete the old skill folders; a no-op once migrated."""
    old, new = workspace / OLD_WORKSPACE_FILE, workspace / WORKSPACE_FILE
    if old.exists() and new.exists():
        raise UserError(
            f"both {old} and {new} exist",
            hint=f"keep your settings in {WORKSPACE_FILE}, delete {OLD_WORKSPACE_FILE}, then sync",
        )
    renamed: list[tuple[Path, Path]] = []
    if old.exists():
        old.rename(new)
        renamed.append((old, new))
    removed: list[Path] = []
    for rel in sorted(set(TARGETS.values())):
        for folder in sorted((workspace / rel).glob(f"{OLD_APP_NAME}-*")):
            if folder.is_dir() and not folder.is_symlink():
                shutil.rmtree(folder)
            else:
                folder.unlink()
            removed.append(folder)
    return Migration(renamed, removed)


def old_env_warnings(environ: Mapping[str, str] | None = None) -> list[str]:
    """One line per set variable with the old prefix, naming the variable that replaced it."""
    env = os.environ if environ is None else environ
    prefix = f"{OLD_ENV_PREFIX}_"
    return [
        f"{name} is no longer read; set {ENV_PREFIX}_{name.removeprefix(prefix)} instead"
        for name in sorted(env)
        if name.startswith(prefix)
    ]


@dataclass(frozen=True)
class OldCache:
    path: Path
    adopt: str


def old_cache() -> OldCache | None:
    """The old default cache, when it exists and the new one holds no files yet.

    A cache env override means the creator chose a location, so the old one is not suggested.
    """
    if os.environ.get(CACHE_ENV):
        return None
    old = platformdirs.user_cache_path(OLD_APP_NAME)
    new = platformdirs.user_cache_path(APP_NAME)
    if not old.is_dir():
        return None
    move = f"mv {shlex.quote(str(old))} {shlex.quote(str(new))}"
    if not new.exists():
        return OldCache(old, move)
    if any(p.is_file() or p.is_symlink() for p in new.rglob("*")):
        return None
    # Commands create the new cache's empty folders; mv would nest the old cache inside them.
    return OldCache(old, f"find {shlex.quote(str(new))} -depth -type d -empty -delete && {move}")


def old_cache_error(found: OldCache) -> UserError:
    return UserError(
        f"{found.path} holds the cache from before the rename to {APP_NAME}",
        hint=f"adopt it with `{found.adopt}`, or delete it to download everything again",
    )
