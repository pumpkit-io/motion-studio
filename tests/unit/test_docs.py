"""The hand-edited docs stay in step with the CLI and with where the product name appears."""

import re
import shutil
import subprocess
from fnmatch import fnmatchcase
from pathlib import Path

import pytest
import typer
from typer._click import Command
from typer.core import TyperGroup

from reelcut import APP_NAME
from reelcut.cli import app

REPO = Path(__file__).resolve().parents[2]
CLI_DOC = REPO / "docs" / "cli.md"
RENAMING_DOC = REPO / "docs" / "renaming.md"


def leaf_commands(group: TyperGroup, prefix: tuple[str, ...] = ()) -> list[tuple[str, Command]]:
    found: list[tuple[str, Command]] = []
    for name, command in group.commands.items():
        path = (*prefix, name)
        if isinstance(command, TyperGroup):
            found.extend(leaf_commands(command, path))
        else:
            found.append((" ".join(path), command))
    return found


def sections(text: str) -> dict[str, str]:
    """Map each `## `/`### ` heading naming a command to the text up to the next heading."""
    parts = re.split(r"^#{2,3} `([^`]+)`\s*$", text, flags=re.M)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts) - 1, 2)}


def test_every_command_and_option_is_in_the_cli_reference() -> None:
    documented = sections(CLI_DOC.read_text(encoding="utf-8"))
    root = typer.main.get_command(app)
    assert isinstance(root, TyperGroup)

    missing: list[str] = []
    for path, command in leaf_commands(root):
        heading = f"{APP_NAME} {path}"
        if heading not in documented:
            missing.append(heading)
            continue
        for param in command.params:
            for opt in getattr(param, "opts", []):
                if opt.startswith("--") and f"`{opt}" not in documented[heading]:
                    missing.append(f"{heading} {opt}")

    assert not missing


def checklist_entries() -> list[str]:
    """The path or pattern that opens each `- ` item of docs/renaming.md."""
    text = RENAMING_DOC.read_text(encoding="utf-8")
    return re.findall(r"^- `([^`]+)`", text, flags=re.M)


def git_lines(*args: str) -> list[str]:
    out = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=False)
    # git grep exits 1 when nothing matches; anything else is a real failure.
    assert out.returncode in (0, 1), out.stderr
    return out.stdout.splitlines()


@pytest.fixture
def named_files() -> list[str]:
    if shutil.which("git") is None or not (REPO / ".git").exists():
        pytest.skip("needs a git checkout")
    by_content = git_lines("grep", "-l", "-i", APP_NAME)
    by_path = [p for p in git_lines("ls-files") if APP_NAME in p.lower()]
    return sorted(set(by_content) | set(by_path))


def test_renaming_checklist_covers_every_file_that_names_the_product(
    named_files: list[str],
) -> None:
    entries = checklist_entries()

    uncovered = [f for f in named_files if not any(fnmatchcase(f, e) for e in entries)]

    assert not uncovered


def test_renaming_checklist_has_no_stale_entries(named_files: list[str]) -> None:
    stale = [e for e in checklist_entries() if not any(fnmatchcase(f, e) for f in named_files)]

    assert not stale
