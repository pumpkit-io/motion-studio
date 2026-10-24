# Build log

What was built for reelcut v0.1.0, ticket by ticket: versions pinned, deviations from the build guide and why, and open issues. Spec: GitHub issue #1. Guide: `video-harness-build-guide.md`.

## Phase 0: environment (ticket #2)

Checked on 2026-10-24.

| Item | Value |
|---|---|
| Machine | arm64 Apple Silicon (`uname -m` = arm64) |
| macOS | 27.0.1 (build 26A434) |
| RAM | 18 GB (`hw.memsize` = 19327352832) |
| Free disk | 125 GiB of 460 GiB on `/` |
| Homebrew | 7.0.7 |
| ffmpeg | 9.0.1 (Homebrew) |
| Node / npm | 24.8.0 / 11.6.0 |
| Python | 3.12.10 (Homebrew `python@3.12`) |
| uv | 0.5.21 |
| just | 1.46.0 |
| git | 2.50.1 (Apple Git-155) |
| gh | 2.87.2, logged in |

ffmpeg filters (`ffmpeg -hide_banner -filters`):

| Filter | Present |
|---|---|
| tonemap | yes |
| loudnorm | yes |
| sidechaincompress | yes |
| ebur128 | yes |
| blackdetect | yes |
| freezedetect | yes |
| arnndn | yes |
| colorspace | yes |
| scale_vt | yes |
| zscale | **no** |
| libplacebo | no |

`zscale` is missing from Homebrew's ffmpeg. ADR 0003 covers it: on macOS, ingest tone-maps HLG and PQ to BT.709 with VideoToolbox `scale_vt`; it uses `zscale` + `tonemap` where `zscale` exists, and otherwise falls back to `colorspace` with a warning. The system ffmpeg is not replaced.

Repository: the private remote `pumpkit-io/reelcut` already exists (spec #1 overrides the guide's "no remote"), so Phase 0 verified it instead of running `git init`. Work happens on `feat/reelcut-v0.1.0`; each ticket merges into it.

Also noted: a stale Intel `/usr/local/bin/python3.9` makes `uv python list` error ("Bad CPU type"); `uv python find 3.12` and everything that pins 3.12 work. `pre-commit` is not installed globally; it comes from the dev group (`uv run pre-commit install`).

## Phase 1: scaffold and tooling (ticket #2)

Built:

- The §4 layout under `src/reelcut/` as empty modules with docstrings, `tests/unit`, `tests/integration`, `tests/fixtures`, `schemas/` and `scripts/gen_schemas.py` (an empty contract registry that later tickets fill).
- `pyproject.toml` (hatchling, Python `>=3.12,<3.14`, console script `reelcut = "reelcut.cli:app"`), extras `mac` (mlx-whisper, arm64 macOS marker) and `cpu` (faster-whisper), and a dev dependency group. `uv.lock` is committed.
- `reelcut --help` and `reelcut --version` through a Typer app in `src/reelcut/cli/`. `APP_NAME` lives once, in `src/reelcut/__init__.py`; `__version__` reads the package metadata.
- ruff (lint and format), pyright (standard mode, strict on `edl/` and `analysis/`), pytest with strict markers `slow`, `mac`, `models`, `renderer`, `music`.
- `.pre-commit-config.yaml` with local hooks that run the project's pinned tools.
- `justfile`: `setup`, `lint`, `fmt`, `test`, `test-all`, `schema`, `schema-check`, `ci`.
- `renderer/`: a minimal Remotion v4 TypeScript project with one composition, `Reel`. All Remotion packages pinned to 4.0.538.
- `.github/workflows/ci.yml`: on every pushed branch and on pull requests, Ubuntu runs `uv sync --locked --extra cpu`, `npm ci`, `just lint`, `just schema-check` and `just test`.
- LICENSE (MIT), README, CONTRIBUTING, CHANGELOG, ROADMAP (guide §13 plus parakeet-mlx, CrisperWhisper and Claude Code plugin packaging), THIRD_PARTY, `docs/dependencies.md`. The developer section was added to `AGENTS.md` above the existing `## Agent skills` block, and `CLAUDE.md` contains `@AGENTS.md`.

Pinned versions: see `docs/dependencies.md`. Every core dependency was checked for an arm64 macOS wheel for Python 3.12 on PyPI before pinning.

Deviations and why:

- No `crisper` extra and no `parakeet-mlx` in `mac`, per spec #1.
- Core dependencies are pinned with `==` in `pyproject.toml`, not just in `uv.lock`, because `uv tool install` ignores the lockfile and §10 asks for determinism.
- The renderer was written from the official blank template rather than by running the interactive `npx create-video`. ESLint is left out for now; `tsc --noEmit` lints the renderer.
- `vitest run --passWithNoTests` until the renderer libraries (camera, caption paging) and their tests land.
- `ruff` excludes `*.md`: ruff 0.17 formats Python blocks inside Markdown and would rewrite the guide's code samples.
- TypeScript type generation from `schemas/timeline.schema.json` is not wired yet; `schema-check` already covers `renderer/src/types.gen.ts` so it applies as soon as the contracts ticket generates it.
- CI pins uv 0.5.21 to match the build machine so `uv sync --locked` reads the same lockfile format.

Open issues: none.

## Phase 2: core (ticket #3)

Built:

- `reelcut.errors`: `UserError` (exit 1), `DependencyError` (2), `InternalError` (3), each with an optional one-line `hint`. The Typer group in `reelcut.cli` maps every failure onto these codes, including Click usage errors (which Click exits with 2, the code reserved for a missing dependency). With `--json`, errors print `{"ok": false, "error", "hint", "exit_code"}`; unexpected exceptions exit 3, with the traceback behind `REELCUT_DEBUG=1`.
- `reelcut.config`: Pydantic models for every §5.1 section (`extra="forbid"`, so typos fail with the file and key named) and `load_config(workspace, slug=None, edl_policy=None)`, which deep-merges defaults < `reelcut.toml` < `project.toml` (minus its `[project]` and `[clips]` tables) < the EDL `policy` object (applied to `[edit]`). `Config.ensure_supported()` raises exit 2 "not implemented in v0.1.0" for `fillers_backend = "crisper"`.
- `reelcut.paths`: `find_workspace` walks up to `reelcut.toml`; `ProjectPaths` holds the §5 layout; slugs are validated (`[a-z0-9][a-z0-9-]*`). The cache is platformdirs' user cache dir: `~/Library/Caches/reelcut` on macOS, `~/.cache/reelcut` on Linux, overridable with `REELCUT_CACHE_DIR`.
- `reelcut.state`: `state.json` with per-stage `{status, input_hash, inputs, params_hash, outputs, finished_at, warnings, error}`; `stage_is_fresh`, `stage_status`, `mark_done`, `mark_failed`, `record_warning`; a per-project `flock` lock that fails fast; the machine-wide heavy-model lock (`<cache>/locks/heavy-model.lock`, blocking `flock`, optional timeout and wait callback); and the free-disk guard `ensure_free_disk` (20 GB default, `REELCUT_MIN_FREE_GB` overrides).
- `reelcut.media.ffmpeg`: `run_ffmpeg` and `run_ffprobe` take argument lists only (a string raises `TypeError`), run without a shell, raise `FFmpegError` carrying the last 20 stderr lines, and report `-progress` positions in seconds. `ffmpeg_caps()` probes the installed ffmpeg's version, filter list, filter-script option and fps-mode option.
- Commands `init`, `new`, `status`, `config show`, `clean`, `doctor`, all with `--json`. The workspace template (`src/reelcut/templates/workspace/`) holds a placeholder `AGENTS.md`, `CLAUDE.md`, the §5.1 `reelcut.toml` and the library and projects directories.
- `schemas/config.schema.json`, generated by `just schema`; `just schema-check` in CI fails when it is stale.
- CI installs Ubuntu's ffmpeg so the runner and probe tests run on Linux against an older ffmpeg.

Verified against the installed versions (2026-10-24):

- ffmpeg 9.0.1 accepts `-/filter_complex <file>` and has removed `-filter_complex_script` ("Unrecognized option"); `-fps_mode` is listed in `-h full`. The runner probes both by a trial run and the help text, never by version number.
- Typer 0.27.3 vendors Click as `typer._click`; the standalone `click` package in the venv is a different copy, so the exit-code mapping catches `typer._click.exceptions`.
- `platformdirs.user_cache_path("reelcut")` is `~/Library/Caches/reelcut` on this Mac.

Deviations and why:

- Cache dir: the guide suggests `~/.cache/reelcut`; platformdirs' macOS default (`~/Library/Caches/reelcut`) is used instead, as the guide allows, with the env override for tests and unusual setups.
- Freshness fingerprints files by path, size and mtime, not content, so `status` stays instant on gigabytes of footage. An edit that keeps size and mtime would go unnoticed.
- `status` judges each stage from the inputs and parameters its last run recorded; a config change shows up when the stage itself checks `stage_is_fresh` with the current parameters. Stage names: ingest, analyze, plan, music, preview, check, final. Music shows `skipped` when `music.mode = "none"`.
- `clean` empties `media/`, `build/` and `preview/`. `--all` (confirmed, or `--yes`) also empties `analysis/`, `contact/`, `check/`, `final/` and deletes `edl.json`, `notes.md` and `state.json`. Nothing ever touches `raw/` or `project.toml`.
- `new` takes `--from a b c` as well as repeated `--from`, hard-links where the volume allows and copies otherwise, takes a directory's visible top-level files, and refuses an existing slug. It creates every §5 directory up front.
- `init` does not run `agents sync` yet; the agent-layer ticket adds it. `doctor --fix` is left for the setup ticket. Until `setup` exists, the renderer, models and ACE-Step env are warnings in `doctor`, not failures; required items are ffmpeg, ffprobe, the eight §3.3 filters (zscale is optional per ADR 0003), a filter-script option, node 20+, npm and the platform's ASR backend.

Open issues: none.
