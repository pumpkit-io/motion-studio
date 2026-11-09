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

## Online video references

When a task needs a video or Reel from a URL, agents use the yt-dlp Python library (`import yt_dlp`) or its CLI to inspect metadata and download a local reference. It is a pinned runtime dependency installed by `uv sync` or `just setup`. In this checkout, use:

```sh
uv run yt-dlp --js-runtimes node --no-playlist --skip-download --dump-single-json 'URL'
uv run yt-dlp --js-runtimes node --no-playlist -P 'references' -o '%(extractor_key)s-%(id)s.%(ext)s' --print after_move:filepath 'URL'
```

`--no-playlist` selects the single video when its URL also names a playlist. Only download playlists or record livestreams when requested. The download command prints the final local path. Keep references outside existing projects' read-only `raw/` directories, analyze local media into compact text, and request contact sheets when a decision needs visual inspection. If the downloaded file is intended as source footage, pass it to the normal project-creation workflow.

Standalone editing workspaces can use `yt-dlp` on PATH, or `uv run --with 'yt-dlp[default]==2026.10.26' yt-dlp` if that executable is unavailable. Installing motion-studio as a uv tool installs the library in its tool environment, but does not necessarily expose dependency executables on PATH. The fallback requires network access on its first run. New workspaces receive these instructions through their `AGENTS.md`; `CLAUDE.md` imports it. Existing workspaces keep their instructions: `agents sync` refreshes skills only.

The `default` extra includes `yt-dlp-ejs` for YouTube challenges. YouTube also needs a supported JavaScript runtime: the examples enable Node.js 22+ with `--js-runtimes node`, using the Node installation already needed by the renderer. ffmpeg merges separate audio and video streams. See [upstream installation](https://github.com/yt-dlp/yt-dlp/wiki/Installation) and [YouTube JavaScript requirements](https://github.com/yt-dlp/yt-dlp/wiki/EJS).

Supported extraction candidates include Instagram (Reels, posts, Stories), YouTube (videos, Shorts, livestreams, playlists), TikTok, X/Twitter, Facebook, Reddit, LinkedIn, Twitch, Vimeo, Pinterest, Dailymotion, Loom and Bilibili. Extractor coverage does not guarantee that every URL or video type works: platforms change, and login, region or account restrictions may apply. Threads may work through generic extraction. Check the [upstream supported-sites list](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md) and report extraction failures or access requirements explicitly. Use authenticated cookies only when the user provides or authorizes them.

## Notes

- **Codex outside a Git repository** only checks the launch directory for `.agents/skills` and `AGENTS.md`. Open Codex in the workspace root, which is where both live.
- **Cursor and Claude Code together**: Cursor also reads `.claude/skills/` for compatibility, so with both targets installed it sees each motion-studio skill twice under the same name. The copies are identical. To avoid the duplicate, sync only the agents you use, for example `motion-studio agents sync --targets cursor`.
- **Gemini CLI and Antigravity CLI**: the Gemini CLI docs note that Google replaced Gemini CLI with Antigravity CLI (`agy`) on 2026-06-18. Third-party migration guides say Antigravity reads workspace skills from `.agents/skills/` and `AGENTS.md`; this was not checked against official Antigravity docs.
- **An agent without skills support** reads `AGENTS.md`, which lists each `.agents/skills/<name>/SKILL.md` by path.
- **Claude Code plugin packaging** is on `ROADMAP.md`, not in v0.1.0.
