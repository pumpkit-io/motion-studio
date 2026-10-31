# Using motion-studio with coding agents

`motion-studio init <dir>` creates a workspace that a host agent opened in `<dir>` can edit from. The agent learns the workflow from two kinds of file:

- **`AGENTS.md`**: golden rules, the workflow pointer and a command quick reference. `CLAUDE.md` and `GEMINI.md` each contain `@AGENTS.md`, so Claude Code and Gemini CLI load the same text.
- **Skills**: six Agent Skills folders (`SKILL.md` with `name` and `description` frontmatter): `motion-studio-edit` (the orchestrator for talk projects) with `motion-studio-plan`, `motion-studio-product` (the orchestrator for product projects, with its recording reference in `recording.md`), and `motion-studio-look`, `motion-studio-music` and `motion-studio-review`, which both kinds use. The workspace `AGENTS.md` sends the agent to the orchestrator for the project's kind. The canonical sources are in `src/motion_studio/templates/skills/`.

`init` installs the skills for every supported agent. `motion-studio agents sync [--targets claude,codex,gemini,cursor]` reinstalls them from the installed motion-studio, for example after an upgrade. Sync copies (it does not symlink, so a workspace survives motion-studio being reinstalled elsewhere), replaces only folders named like a motion-studio skill, and leaves other skills in the same directories alone. `.agents/skills/` is always written, whatever the targets, because `AGENTS.md` links the skill files there by path for any agent that does not load skills.

## Where each agent looks

Checked against each agent's official docs on 2026-10-24.

| Agent | Workspace skill directory | Instructions file | Source |
|---|---|---|---|
| Claude Code | `.claude/skills/<name>/SKILL.md` | `CLAUDE.md` (here `@AGENTS.md`) | [code.claude.com/docs/en/skills](https://code.claude.com/docs/en/skills): "Project: `.claude/skills/<skill-name>/SKILL.md`"; skills load from the start directory and its parents up to the repository root. |
| Codex | `.agents/skills/<name>/SKILL.md` | `AGENTS.md` | [Codex: build skills](https://developers.openai.com/codex/skills) (now served at learn.chatgpt.com/docs/build-skills): REPO scope scans `$CWD/.agents/skills`, its parent inside a Git repo, and `$REPO_ROOT/.agents/skills`; `SKILL.md` "must include `name` and `description`". [AGENTS.md guide](https://developers.openai.com/codex/guides/agents-md). |
| Gemini CLI | `.agents/skills/<name>/SKILL.md` (alias of `.gemini/skills/`) | `GEMINI.md` (here `@AGENTS.md`) | [geminicli.com/docs/cli/skills](https://geminicli.com/docs/cli/skills/): workspace skills are "Located in `.gemini/skills/` or the `.agents/skills/` alias", and the alias takes precedence. [GEMINI.md docs](https://geminicli.com/docs/cli/gemini-md/): `GEMINI.md` is the default context file and supports `@file.md` imports. |
| Cursor | `.agents/skills/<name>/SKILL.md` (also `.cursor/skills/`) | `AGENTS.md` | [cursor.com/docs/context/skills](https://cursor.com/docs/context/skills): project skills load from `.agents/skills/` and `.cursor/skills/`; `name` (must match the folder) and `description` are required. [Rules docs](https://cursor.com/docs/context/rules): "Cursor supports AGENTS.md in the project root and subdirectories." |

The `TARGETS` table in `src/motion_studio/agents/__init__.py` holds these paths; change both together.

## Notes

- **Codex outside a Git repository** only checks the launch directory for `.agents/skills` and `AGENTS.md`. Open Codex in the workspace root, which is where both live.
- **Cursor and Claude Code together**: Cursor also reads `.claude/skills/` for compatibility, so with both targets installed it sees each motion-studio skill twice under the same name. The copies are identical. To avoid the duplicate, sync only the agents you use, for example `motion-studio agents sync --targets cursor`.
- **Gemini CLI and Antigravity CLI**: the Gemini CLI docs note that Google replaced Gemini CLI with Antigravity CLI (`agy`) on 2026-06-18. Third-party migration guides say Antigravity reads workspace skills from `.agents/skills/` and `AGENTS.md`; this was not checked against official Antigravity docs.
- **An agent without skills support** reads `AGENTS.md`, which lists each `.agents/skills/<name>/SKILL.md` by path.
- **Claude Code plugin packaging** is on `ROADMAP.md`, not in v0.1.0.
