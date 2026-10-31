"""Recognise what the product's previous name left behind: workspaces, caches, env variables.

Nothing here moves the cache: it can hold 16 GB, so the CLI prints the command instead.
"""

import hashlib
import os
import re
import shlex
import shutil
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

import platformdirs

from motion_studio import APP_NAME, ENV_PREFIX
from motion_studio.agents import TARGETS, skill_names
from motion_studio.errors import UserError
from motion_studio.paths import CACHE_ENV, WORKSPACE_FILE

# The one constant in code that keeps the old name; see docs/renaming.md.
OLD_APP_NAME = "reelcut"
OLD_WORKSPACE_FILE = f"{OLD_APP_NAME}.toml"
OLD_ENV_PREFIX = OLD_APP_NAME.upper().replace("-", "_")
OLD_CACHE_ENV = f"{OLD_ENV_PREFIX}_{CACHE_ENV.removeprefix(f'{ENV_PREFIX}_')}"

AGENTS_MD = "AGENTS.md"
# SHA-256 of the workspace AGENTS.md that `init` wrote under the old name (v0.1.0).
OLD_AGENTS_MD_SHA256 = "3d645288224cacfa0530a984be5ae87ccfd019b86c9dffb7251a22014eb19893"

SYNC_HINT = f"run `{APP_NAME} agents sync` in the workspace to migrate it"


def unmigrated_error(workspace: Path) -> UserError:
    return UserError(
        f"{workspace / OLD_WORKSPACE_FILE} is a workspace from before the rename to {APP_NAME}",
        hint=SYNC_HINT,
    )


@dataclass(frozen=True)
class AgentsMdChange:
    path: Path
    rewritten: bool
    places: int = 0

    @property
    def line(self) -> str:
        if self.rewritten:
            return f"rewrote {self.path} from the template"
        return f"renamed {OLD_APP_NAME} to {APP_NAME} in {self.path} ({self.places} places)"


@dataclass(frozen=True)
class Migration:
    renamed: list[tuple[Path, Path]]
    agents_md: AgentsMdChange | None


def old_skill_names() -> list[str]:
    """The names the shipped skills had under the old name; creators' own skills are not here."""
    return [f"{OLD_APP_NAME}-{n.removeprefix(f'{APP_NAME}-')}" for n in skill_names()]


def migrate_workspace(workspace: Path) -> Migration:
    """Rename the old workspace file and update AGENTS.md; a no-op once migrated.

    The old skill folders stay until `remove_old_skills`, so they outlive a failed install.
    """
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
    return Migration(renamed, _migrate_agents_md(workspace / AGENTS_MD))


def _migrate_agents_md(path: Path) -> AgentsMdChange | None:
    """Replace an unedited old AGENTS.md with the template; rename the old name in an edited one.

    In an edited file only the shipped commands, skills, file and variables change, so a
    creator's own `<old name>-*` skill keeps its name.
    """
    if not path.is_file():
        return None
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() == OLD_AGENTS_MD_SHA256:
        template = files("motion_studio") / "templates" / "workspace" / AGENTS_MD
        path.write_bytes(template.read_bytes())
        return AgentsMdChange(path, rewritten=True)
    old = re.escape(OLD_APP_NAME)
    shipped = "|".join(re.escape(n.removeprefix(f"{APP_NAME}-")) for n in skill_names())
    text, places = data.decode("utf-8"), 0
    for pattern, replacement in (
        (rf"\b{old}-({shipped})\b", rf"{APP_NAME}-\1"),
        (re.escape(OLD_WORKSPACE_FILE), WORKSPACE_FILE),
        (rf"\b{re.escape(OLD_ENV_PREFIX)}_", f"{ENV_PREFIX}_"),
        (rf"(?<![-\w]){old}(?![-\w])", APP_NAME),
    ):
        text, count = re.subn(pattern, replacement, text)
        places += count
    if not places:
        return None
    path.write_text(text, encoding="utf-8")
    return AgentsMdChange(path, rewritten=False, places=places)


def remove_old_skills(workspace: Path) -> list[Path]:
    """Delete the shipped skills' old-name folders from every agent's skill directory."""
    removed: list[Path] = []
    for rel in sorted(set(TARGETS.values())):
        for name in old_skill_names():
            folder = workspace / rel / name
            if folder.is_dir() and not folder.is_symlink():
                shutil.rmtree(folder)
            elif folder.is_symlink() or folder.exists():
                folder.unlink()
            else:
                continue
            removed.append(folder)
    return removed


def old_env_warnings() -> list[str]:
    """One line per set variable with the old prefix, naming the variable that replaced it."""
    prefix = f"{OLD_ENV_PREFIX}_"
    return [
        f"{name} is no longer read; set {ENV_PREFIX}_{name.removeprefix(prefix)} instead"
        for name in sorted(os.environ)
        if name.startswith(prefix)
    ]


@dataclass(frozen=True)
class OldCache:
    path: Path
    adopt_command: str


def old_cache() -> OldCache | None:
    """The old cache, when it exists and the new default one holds no files yet.

    The old cache is where the old cache variable points, else the old platform default. A set
    new cache variable means the creator chose a location, so no old cache is suggested.
    """
    if os.environ.get(CACHE_ENV):
        return None
    override = os.environ.get(OLD_CACHE_ENV)
    old = Path(override) if override else platformdirs.user_cache_path(OLD_APP_NAME)
    new = platformdirs.user_cache_path(APP_NAME)
    if not old.is_dir():
        return None
    move = f"mv {shlex.quote(str(old))} {shlex.quote(str(new))}"
    if not new.exists():
        return OldCache(old, move)
    locks = new / "locks"
    if any(_holds_data(p, locks) for p in new.rglob("*")):
        return None
    # Commands create the new cache's empty folders and lock files; mv would nest the old
    # cache inside them.
    quoted = shlex.quote(str(new))
    clear = (
        f"find {quoted} -depth \\( -type f -empty -path {shlex.quote(f'{locks}/*')} "
        f"-o -type d -empty \\) -delete"
    )
    return OldCache(old, f"{clear} && {move}")


def _holds_data(path: Path, locks: Path) -> bool:
    if path.is_symlink():
        return True
    if not path.is_file():
        return False
    return not (path.is_relative_to(locks) and path.stat().st_size == 0)


def old_cache_error(found: OldCache) -> UserError:
    return UserError(
        f"{found.path} holds the cache from before the rename to {APP_NAME}",
        hint=f"adopt it with `{found.adopt_command}`, or delete it to download everything again",
    )
