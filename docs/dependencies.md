# Dependencies: verified versions and install notes

Each entry was checked against the installed version or official source on the date given. Later tickets add their own entries.

## Toolchain (build machine, 2026-10-24)

| Tool | Version | How checked |
|---|---|---|
| Python | 3.12.10 (Homebrew `python@3.12`) | `uv python find 3.12` |
| uv | 0.5.21 | `uv --version`; CI pins the same version |
| just | 1.46.0 | `just --version` |
| Node | 24.8.0 | `node --version`; CI uses Node 24 |
| npm | 11.6.0 | `npm --version` |
| ffmpeg | 9.0.1 (Homebrew) | `ffmpeg -version`; filters in BUILD_LOG.md |
| gh | 2.87.2 | `gh --version` |

## Python core dependencies

Pinned exactly in `pyproject.toml`, because `uv tool install` ignores `uv.lock`. Every one has a wheel for arm64 macOS and Python 3.12, checked against the PyPI JSON API on 2026-10-24 before pinning:

| Package | Version | arm64 macOS wheel |
|---|---|---|
| typer | 0.27.3 | `py3-none-any` |
| rich | 15.0.0 | `py3-none-any` |
| pydantic | 2.14.1 | `py3-none-any` (pydantic-core resolved by uv, has `cp312 macosx arm64`) |
| tomli-w | 1.2.0 | `py3-none-any` |
| numpy | 2.5.4 | `cp312-cp312-macosx_11_0_arm64` |
| opencv-python-headless | 5.0.0.93 | `cp37-abi3-macosx_13_0_arm64` |
| scenedetect | 0.7.2 | `py3-none-any` |
| mediapipe | 1.1.1 | `py3-none-macosx_11_0_arm64` (also `manylinux_2_28_x86_64` for CI) |
| onnxruntime | 1.31.0 | `cp312-cp312-macosx_14_0_arm64` |
| rapidfuzz | 3.14.6 | `cp312-cp312-macosx_11_0_arm64` |
| librosa | 1.0.0 | `py3-none-any` (pulls numba 0.68.0) |
| soundfile | 0.14.0 | `py2.py3-none-any` |
| pillow | 13.0.0 | `cp312-cp312-macosx_11_0_arm64` |
| platformdirs | 4.13.5 | `py3-none-any` |

Extras: `mac` = mlx-whisper 0.4.3 (`py3-none-any`; pulls torch 2.14.1), `cpu` = faster-whisper 1.2.1 (`py3-none-any`). There is no `crisper` extra in v0.1.0.

Dev group (`uv sync` installs it by default): ruff 0.17.2, pyright 1.1.414, pytest 9.1.1, pytest-cov 7.1.0, hypothesis 6.170.9, pre-commit 4.7.0.

## Renderer (npm, exact pins in `renderer/package.json`)

| Package | Version | Notes |
|---|---|---|
| remotion, @remotion/cli, @remotion/captions | 4.0.538 | `latest` dist-tag on 2026-10-24. All `remotion` and `@remotion/*` packages stay on one version. |
| react, react-dom | 19.2.3 | The version the official `template-empty` uses |
| @types/react | 19.2.7 | As in `template-empty` |
| typescript | 5.9.3 | As in `template-empty` |
| vitest | 5.0.5 | Requires Node `^22.12.0 \|\| ^24.0.0 \|\| >=26.0.0` |

Scaffold: the current command is `npx create-video@latest` (version 4.0.538), which is interactive. The renderer was written by hand from the official blank template (`remotion-dev/template-empty`, `main`) instead: same `registerRoot` entry, `remotion.config.ts` via `@remotion/cli/config`, and `tsconfig` with `moduleResolution: Bundler`. The template's ESLint config is left out; `tsc --noEmit` is the renderer lint for now.

## GitHub Actions

| Action | Version |
|---|---|
| actions/checkout | v7 (latest release v7.0.1) |
| astral-sh/setup-uv | v10.3.2 (the repo publishes no floating `v10` tag) |
| actions/setup-node | v7 (latest release v7.1.0) |
| extractions/setup-just | v4 |

## ffmpeg options (ticket #3, 2026-10-24)

| Option | ffmpeg 9.0.1 (build machine) | How the runner picks it |
|---|---|---|
| Filter graph from a file | `-/filter_complex <file>`; `-filter_complex_script` is gone ("Unrecognized option") | Trial run of `-/filter_complex`, then `-filter_complex_script` if `-h full` lists it |
| Frame-rate mode | `-fps_mode` | `-fps_mode` if `-h full` lists it, else `-vsync` |
| Progress | `-progress pipe:1 -nostats`, `out_time_us=` lines | Parsed from stdout |

## Python libraries used by the core (ticket #3)

- Typer 0.27.3 vendors Click as `typer._click`; catch `typer._click.exceptions`, not the separate `click` package.
- platformdirs 4.13.5: `user_cache_path("reelcut")` is `~/Library/Caches/reelcut` on macOS and `~/.cache/reelcut` on Linux.

## Fixture generation (ticket #4, 2026-10-24)

| Item | Value | How checked |
|---|---|---|
| `say` voices | Samantha (en_US), Alice (it_IT) | `say -v '?'` |
| `say` output flags | `-o x.wav --file-format=WAVE --data-format=LEI16@48000` | ran it; output is byte-identical across runs |
| ffmpeg `setts` bitstream filter | `setts=ts=<expr>` on a stream copy, with `-bf 0` so pts equals dts | ffmpeg 9.0.1; ffprobe shows the alternating packet durations |
| ffmpeg `streamhash` muxer | `-map 0 -f streamhash -` | ffmpeg 9.0.1; used by the determinism test |

## Agent skill paths (ticket #16, 2026-10-24)

Checked against each agent's official docs; the table, quotes and links are in `docs/agents.md`.

| Agent | Workspace skill directory | Instructions file |
|---|---|---|
| Claude Code | `.claude/skills/` | `CLAUDE.md` |
| Codex | `.agents/skills/` | `AGENTS.md` |
| Gemini CLI | `.agents/skills/` (alias of `.gemini/skills/`) | `GEMINI.md` |
| Cursor | `.agents/skills/` (also `.cursor/skills/`) | `AGENTS.md` |

All four require or recommend `name` and `description` frontmatter in `SKILL.md`; Cursor and Gemini CLI want `name` to match the folder. PyYAML 6.0.3 (already in the lock through the dev group) parses the frontmatter in the skill test.
