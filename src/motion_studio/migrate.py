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
# The commands the old name shipped (v0.1.0); prose such as "<old name>'s job" is left alone.
OLD_COMMANDS = (
    "agents", "analyze", "check", "clean", "config", "docs", "doctor", "ingest", "init",
    "look", "look-asset", "music", "new", "plan", "render", "setup", "status", "words",
)  # fmt: skip
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
    warnings: list[str]


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
    agents_md = workspace / AGENTS_MD
    try:
        change = _migrate_agents_md(agents_md)
    except UnicodeDecodeError:
        return Migration(renamed, None, [f"left {agents_md} alone: it is not UTF-8"])
    return Migration(renamed, change, [])


def _migrate_agents_md(path: Path) -> AgentsMdChange | None:
    """Replace an unedited old AGENTS.md with the template; rename the old name in an edited one.

    In an edited file only the shipped commands and skills, the toml and the variable prefix
    change; a creator's own `<old name>-*` skill, paths and URLs keep the old name.
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
    commands = "|".join(re.escape(c) for c in OLD_COMMANDS)
    # Not after `/` or `.`, so a path or URL segment named after the old name keeps it.
    alone = r"(?<![-\w/.])"
    text, places = data.decode("utf-8"), 0
    for pattern, replacement in (
        (rf"(?<![-\w]){old}-({shipped})(?![-\w])", rf"{APP_NAME}-\1"),
        (rf"(?<![-\w]){re.escape(OLD_WORKSPACE_FILE)}(?![-\w]|\.\w)", WORKSPACE_FILE),
        (rf"\b{re.escape(OLD_ENV_PREFIX)}_", f"{ENV_PREFIX}_"),
        (rf"{alone}{old}(?=[ \t]+(?:(?:{commands})(?![-\w])|-))", APP_NAME),
        (rf"`{old}`", f"`{APP_NAME}`"),
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
            if not (folder.is_symlink() or folder.exists()):
                continue
            if folder.is_dir() and not folder.is_symlink():
                shutil.rmtree(folder)
            else:
                folder.unlink()
            removed.append(folder)
    return removed


def old_env_warnings() -> list[str]:
    """One line per set variable with the old prefix, naming the variable that replaced it."""
    prefix = f"{OLD_ENV_PREFIX}_"
    return [_old_env_warning(name) for name in sorted(os.environ) if name.startswith(prefix)]


def _old_env_warning(name: str) -> str:
    value = os.environ[name]
    # Pointing the new variable at the old default would contradict the `mv` that adopts it.
    if name == OLD_CACHE_ENV and Path(value) == platformdirs.user_cache_path(OLD_APP_NAME):
        return f"{name} is no longer read; unset it, then adopt the cache `{APP_NAME} doctor` names"
    return f"{name} is no longer read; set {_new_env(name, value)} instead"


def _new_env(old_name: str, value: str) -> str:
    return f"{ENV_PREFIX}_{old_name.removeprefix(f'{OLD_ENV_PREFIX}_')}={shlex.quote(value)}"


@dataclass(frozen=True)
class OldCache:
    path: Path
    adopt_command: str


def old_cache() -> OldCache | None:
    """The old cache, when it exists and the new default one holds no files yet.

    The old cache is where the old cache variable points, else the old platform default. A set
    new cache variable means the creator chose a location, so no old cache is suggested. A
    custom old location is adopted by pointing the new variable at it, not by moving it.
    """
    if os.environ.get(CACHE_ENV):
        return None
    default = platformdirs.user_cache_path(OLD_APP_NAME)
    override = os.environ.get(OLD_CACHE_ENV)
    old = Path(override) if override else default
    new = platformdirs.user_cache_path(APP_NAME)
    if not old.is_dir():
        return None
    if new.exists() and any(_holds_data(p, new / "locks") for p in new.rglob("*")):
        return None
    if override and old != default:
        return OldCache(old, f"export {_new_env(OLD_CACHE_ENV, override)}")
    # Any command, doctor included, can lay down the new cache's empty folders and lock files
    # before this runs, and mv into an existing folder nests the old cache inside it.
    target, locks = shlex.quote(str(new)), shlex.quote(str(new / "locks"))
    return OldCache(
        old,
        f"mkdir -p {locks} && find {locks} -type f -empty -delete"
        f" && find {target} -depth -type d -empty -delete"
        f" && test ! -e {target} && mv {shlex.quote(str(old))} {target}",
    )


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
