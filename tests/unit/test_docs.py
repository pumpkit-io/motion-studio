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

from motion_studio import APP_NAME
from motion_studio.cli import app
from motion_studio.migrate import OLD_APP_NAME

REPO = Path(__file__).resolve().parents[2]
CLI_DOC = REPO / "docs" / "cli.md"
RENAMING_DOC = REPO / "docs" / "renaming.md"
OLD_NAME_HEADING = "\n## Where the previous name stays\n"


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
    """The path or pattern that opens each `- ` item of docs/renaming.md, old-name ones aside."""
    text = RENAMING_DOC.read_text(encoding="utf-8").split(OLD_NAME_HEADING, 1)[0]
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
    # The import package spells the name with an underscore, which `-` in APP_NAME does not match.
    names = (APP_NAME, APP_NAME.replace("-", "_"))
    by_content = git_lines("grep", "-l", "-i", *(arg for n in names for arg in ("-e", n)))
    by_path = [p for p in git_lines("ls-files") if any(n in p.lower() for n in names)]
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


def old_name_entries() -> list[str]:
    """The entries under the renaming doc's section on where the previous name stays."""
    text = RENAMING_DOC.read_text(encoding="utf-8")
    section = text.split(OLD_NAME_HEADING, 1)[1].split("\n## ", 1)[0]
    return re.findall(r"^- `([^`]+)`", section, flags=re.M)


def test_the_previous_name_appears_only_where_the_renaming_doc_allows() -> None:
    if shutil.which("git") is None or not (REPO / ".git").exists():
        pytest.skip("needs a git checkout")
    entries = old_name_entries()
    by_content = git_lines("grep", "-l", "-i", "-e", OLD_APP_NAME)
    by_path = [p for p in git_lines("ls-files") if OLD_APP_NAME in p.lower()]

    named = sorted({*by_content, *by_path})

    stray = [f for f in named if not any(fnmatchcase(f, e) for e in entries)]
    stale = [e for e in entries if not any(fnmatchcase(f, e) for f in named)]

    assert entries
    assert not stray
    assert not stale
