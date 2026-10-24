"""`agents sync`: install the canonical skills into each agent's directory."""

import shutil
from importlib.resources import as_file, files
from pathlib import Path

from reelcut.errors import UserError

# Workspace-relative skill directories, verified against each agent's docs (docs/agents.md).
TARGETS: dict[str, str] = {
    "claude": ".claude/skills",
    "codex": ".agents/skills",
    "gemini": ".agents/skills",
    "cursor": ".agents/skills",
}

# Always written: the workspace AGENTS.md points here so an agent without skills support
# can read the files by path.
SHARED_DIR = ".agents/skills"


def parse_targets(value: str | None) -> list[str]:
    """Turn `claude,codex` into a target list; None means every supported agent."""
    if value is None:
        return list(TARGETS)
    names = [n.strip().lower() for n in value.split(",") if n.strip()]
    unknown = [n for n in names if n not in TARGETS]
    if unknown or not names:
        raise UserError(
            f"unknown agent target {', '.join(unknown) or repr(value)}",
            hint=f"choose from {','.join(TARGETS)}",
        )
    return names


def skill_names() -> list[str]:
    root = files("reelcut") / "templates" / "skills"
    return sorted(p.name for p in root.iterdir() if p.is_dir() and (p / "SKILL.md").is_file())


def sync_skills(workspace: Path, targets: list[str]) -> list[Path]:
    """Replace each reelcut skill folder in the targets' directories; return the folders.

    Skills with other names in those directories are left alone.
    """
    dirs = sorted({SHARED_DIR, *(TARGETS[t] for t in targets)})
    written: list[Path] = []
    with as_file(files("reelcut") / "templates" / "skills") as source:
        for rel in dirs:
            for name in skill_names():
                dest = workspace / rel / name
                if dest.is_symlink() or dest.is_file():
                    dest.unlink()
                elif dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(source / name, dest)
                written.append(dest)
    return written
