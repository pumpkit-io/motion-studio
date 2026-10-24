import json
import re
from pathlib import Path

import pytest
import typer
import yaml
from typer._click import Command
from typer.core import TyperGroup
from typer.testing import CliRunner

from reelcut.cli import app

runner = CliRunner()

SKILLS = ["reelcut-edit", "reelcut-look", "reelcut-music", "reelcut-plan", "reelcut-review"]

# Verified in docs/agents.md: Claude Code reads .claude/skills; Codex, Gemini CLI and Cursor
# all read .agents/skills.
SKILL_DIRS = [".claude/skills", ".agents/skills"]


def invoke(*args: str | Path, input: str | None = None):
    return runner.invoke(app, [str(a) for a in args], input=input)


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    ws = tmp_path / "reels"
    result = invoke("init", ws)
    assert result.exit_code == 0, result.output
    monkeypatch.chdir(ws)
    return ws


def installed(ws: Path, skill_dir: str) -> list[str]:
    root = ws / skill_dir
    return sorted(p.parent.name for p in root.glob("*/SKILL.md")) if root.is_dir() else []


def test_init_installs_every_skill_in_each_agent_path(workspace: Path) -> None:
    for skill_dir in SKILL_DIRS:
        assert installed(workspace, skill_dir) == SKILLS, skill_dir


def frontmatter(skill_md: Path) -> dict[str, object]:
    text = skill_md.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{skill_md} must open with --- on line 1"
    block, _, body = text[4:].partition("\n---\n")
    assert body.strip(), f"{skill_md} has no body"
    data = yaml.safe_load(block)
    assert isinstance(data, dict), skill_md
    return data


@pytest.mark.parametrize("skill", SKILLS)
def test_every_skill_has_frontmatter_with_its_folder_name_and_a_description(
    workspace: Path, skill: str
) -> None:
    for skill_dir in SKILL_DIRS:
        data = frontmatter(workspace / skill_dir / skill / "SKILL.md")
        assert data["name"] == skill
        description = data["description"]
        # The Agent Skills format caps descriptions at 1024 characters.
        assert isinstance(description, str)
        assert 0 < len(description) <= 1024


def test_agents_sync_restores_edited_skills_and_keeps_other_skills(workspace: Path) -> None:
    edit = workspace / ".claude/skills/reelcut-edit/SKILL.md"
    pristine = edit.read_text(encoding="utf-8")
    edit.write_text("stale", encoding="utf-8")
    (edit.parent / "leftover.md").write_text("old", encoding="utf-8")
    mine = workspace / ".claude/skills/my-own/SKILL.md"
    mine.parent.mkdir()
    mine.write_text("mine", encoding="utf-8")

    result = invoke("agents", "sync")

    assert result.exit_code == 0, result.output
    assert edit.read_text(encoding="utf-8") == pristine
    assert not (edit.parent / "leftover.md").exists()
    assert mine.read_text(encoding="utf-8") == "mine"
    assert str(edit.parent) in result.output


def test_agents_sync_targets_one_agent_and_always_writes_the_shared_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = tmp_path / "bare"
    ws.mkdir()
    (ws / "reelcut.toml").write_text("", encoding="utf-8")
    monkeypatch.chdir(ws)

    result = invoke("agents", "sync", "--targets", "claude", "--json")

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["targets"] == ["claude"]
    assert installed(ws, ".claude/skills") == SKILLS
    assert installed(ws, ".agents/skills") == SKILLS
    assert len(payload["written"]) == 2 * len(SKILLS)


def test_agents_sync_rejects_an_unknown_target(workspace: Path) -> None:
    result = invoke("agents", "sync", "--targets", "claude,vim")
    assert result.exit_code == 1
    assert "vim" in result.output


def test_agents_sync_outside_a_workspace_is_a_user_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert invoke("agents", "sync").exit_code == 1


# Guide §7 commands that later tickets build, with the flags §7 gives them. Once a command is
# registered it is checked against the real CLI instead; delete its entry when you build it.
PENDING: dict[tuple[str, ...], tuple[int, set[str]]] = {
    ("render",): (13, {"--preview", "--final", "--format"}),
    ("check",): (15, {"--preview", "--final"}),
}

INLINE = re.compile(r"`(reelcut [^`]+)`")
FLAG = re.compile(r"(?<![\w-])--[a-z][a-z-]*")
WORD = re.compile(r"[a-z][a-z-]*")


def agent_docs(ws: Path) -> list[Path]:
    return [ws / "AGENTS.md", *sorted((ws / ".agents/skills").glob("*/SKILL.md"))]


def mentions(doc: Path) -> list[str]:
    """Every `reelcut ...` command in inline code or on a line of a fenced block."""
    found: list[str] = []
    fenced = False
    for line in doc.read_text(encoding="utf-8").splitlines():
        if line.startswith("```"):
            fenced = not fenced
        elif fenced and line.startswith("reelcut "):
            found.append(line.strip())
        else:
            found += INLINE.findall(line)
    return found


def cli_command(path: list[str]) -> Command | None:
    """The command reached by the longest prefix of `path`, or None if that is a group."""
    command = typer.main.get_command(app)
    for word in path:
        if not isinstance(command, TyperGroup) or word not in command.commands:
            break
        command = command.commands[word]
    return None if isinstance(command, TyperGroup) else command


def check_mention(mention: str) -> str | None:
    words: list[str] = []
    for token in mention.split()[1:]:
        if not WORD.fullmatch(token):
            break
        words.append(token)
    flags = set(FLAG.findall(mention))
    command = cli_command(words)
    if command is not None:
        known = {opt for p in command.params for opt in (*p.opts, *p.secondary_opts)}
        missing = flags - known
        return f"{mention!r}: {command.name} has no {sorted(missing)}" if missing else None
    pending = [key for key in PENDING if tuple(words[: len(key)]) == key]
    if not pending:
        return f"{mention!r}: no such command in the CLI or in PENDING"
    _, spec = PENDING[max(pending, key=len)]
    missing = flags - spec - {"--json"}
    return f"{mention!r}: guide §7 gives it no {sorted(missing)}" if missing else None


def test_every_command_in_agents_md_and_the_skills_exists_with_its_flags(
    workspace: Path,
) -> None:
    seen = [(doc.name, m) for doc in agent_docs(workspace) for m in mentions(doc)]
    assert len({m for _, m in seen}) >= 15, seen
    problems = [f"{name}: {p}" for name, m in seen if (p := check_mention(m))]
    assert not problems, "\n".join(problems)


def test_the_command_check_catches_a_wrong_flag_and_an_unknown_command() -> None:
    assert check_mention("reelcut status <slug>") is None
    assert check_mention("reelcut render <slug> --preview|--final") is None
    assert check_mention("reelcut status <slug> --verbose")
    assert check_mention("reelcut render <slug> --draft")
    assert check_mention("reelcut publish <slug>")


def test_agents_md_points_to_every_skill_file_by_a_path_that_exists(workspace: Path) -> None:
    text = (workspace / "AGENTS.md").read_text(encoding="utf-8")
    for skill in SKILLS:
        pointer = f".agents/skills/{skill}/SKILL.md"
        assert pointer in text, pointer
        assert (workspace / pointer).is_file()


def test_init_writes_the_library_skeleton_with_a_music_licensing_readme(workspace: Path) -> None:
    readme = (workspace / "library/music/README.md").read_text(encoding="utf-8")
    assert "tags.json" in readme
    assert "licence" in readme
    assert (workspace / "library/brand").is_dir()


def leaves(command: Command, path: str = "") -> list[tuple[str, Command]]:
    if isinstance(command, TyperGroup):
        return [x for name, sub in command.commands.items() for x in leaves(sub, f"{path} {name}")]
    return [(path.strip(), command)]


def test_every_command_takes_json_as_agents_md_promises() -> None:
    commands = leaves(typer.main.get_command(app))
    lacking = [name for name, c in commands if not any("--json" in p.opts for p in c.params)]
    assert not lacking


def test_claude_and_gemini_instruction_files_import_agents_md(workspace: Path) -> None:
    for name in ["CLAUDE.md", "GEMINI.md"]:
        assert (workspace / name).read_text(encoding="utf-8").strip() == "@AGENTS.md"
