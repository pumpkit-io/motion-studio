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

## Phase 11, fixtures part (ticket #4)

Built:

- `scripts/make_fixtures.py` and `just fixtures`: regenerates, from scratch, an English clip (`say` voice Samantha, en_US) and an Italian clip (Alice, it_IT) with known silences, a hard filler (`um`, `ehm`) and an abandoned first attempt followed by its complete retake; a synthetic presenter video at 1080×1920 and 30 fps, remuxed to variable frame rate; 6 s of `testsrc2` B-roll at 1920×1080; a `mandelbrot` PNG; `prova clip è.mov` (a copy of the English clip); and `tiny.mp4` (2 s of `testsrc2` + `sine`). Generation takes about 17 s.
- Ground truth per talking clip in `tests/fixtures/ground_truth/` (utterances, fillers, silences with context, retake pair, language). The format is in `tests/fixtures/README.md`.
- A public-domain NASA portrait of Neil Armstrong (Wikimedia Commons) in `tests/fixtures/faces/` for face tests, with its source and licence in the fixtures README.
- Tests: `tests/integration/test_fixtures.py` (`slow`, `mac`) runs the script twice and checks dimensions and VFR with ffprobe, the scripted silence lengths, that the decoded audio is silent in every silence span and loud in every utterance, that the committed ground truth equals what the script writes, and that both runs give identical stream hashes. `tests/unit/test_ground_truth.py` checks in CI that the committed ground truth tiles each clip.

Checked: `say` output is byte-identical across runs for the same voice and text. mlx-whisper (`whisper-large-v3-turbo`, run once by hand, not in a test) transcribed the generated clips with `um,` and `Ehm.` as words and the abandoned attempt ending in `is.` / `è.`. An isolated `ehm` spoken by Alice outside a clip comes out as "M.", so fillers must be judged in context.

Deviations and why:

- Python instead of `scripts/make_fixtures.sh`: the script computes the ground truth from sample counts, which needs arithmetic and JSON a shell script handles badly.
- Silences are inserted as zero samples between separately spoken lines instead of `say`'s `[[slnc N]]` command, so their positions are exact rather than dependent on how `say` paces them. `[[slnc]]` was not used, so its syntax was not verified.
- The abandoned attempt is a spoken prefix of the retake ("The most important thing to remember is") rather than audio cut mid-word, so the ground-truth text is exact.
- VFR comes from a stream-copy remux with the `setts` bitstream filter (every third frame 10 ms late), not from frame drops. `r_frame_rate` reads `300/1` while `avg_frame_rate` is `30/1`; ingest must use the latter.
- `tiny.mp4` and the face photo are committed (110 KB and 245 KB) so CI tests can use them; the rest of `tests/fixtures/media/` is gitignored.

Open issues: there is no 5-minute fixture yet for the Phase 4 `packed.md` token budget check; the talking clips are about 21 s.

## Phase 3: ingest (ticket #5)

Built:

- `reelcut ingest <slug>` (`--json`), in `reelcut.ingest`. It calls the disk guard, takes the project lock, probes every visible file in `raw/` (sorted), and gives each new one the next free ID for its provisional role: `c` for a video whose audio peaks above -35 dBFS, `b` for a quieter or silent video, `i` for an image. IDs live in `project.toml` as `[clips.<id>]` with `source`, `role` and `auto_role`. A `role` that differs from `auto_role` is the creator's override; ingest never changes it, and `record_auto_role()` (for the role-finalisation ticket) only moves `role` along with `auto_role` when they agree. IDs are never renumbered or reused; a source that vanished from `raw/` keeps its ID and gets a warning.
- Mezzanines (`reelcut.media.normalise`): `media/<id>.mp4`, `fps=<project fps>` + `-fps_mode cfr`, rotation applied by ffmpeg's autorotate, long side capped at 3840 px with even dimensions, H.264 High CRF 15 `-preset fast`, GOP of one second, `yuv420p`, `+faststart`, original audio as AAC for reference. HDR (HLG, PQ) is tone-mapped per ADR 0003: `scale_vt` on macOS, `zscale` + `tonemap` (hable) where zscale exists, otherwise `colorspace` with a warning; tone-mapped output is tagged BT.709. A method that fails at run time falls through to the next with a warning. `REELCUT_TONEMAP` forces one method.
- Voice (`reelcut.audio.enhance`): 48 kHz mono extract, DeepFilterNet 3 (`deep-filter --compensate-delay`), or ffmpeg `arnndn` with the vendored `sh.rnnn` model and a warning, then an 80 Hz high-pass, padded or trimmed to the exact source sample count: `media/<id>.wav` (48 kHz) and `media/<id>_16k.wav` (16 kHz, for ASR and VAD). `install_deep_filter()` downloads the pinned 0.5.6 binary into `<cache>/bin/deep-filter` and checks its SHA-256; `doctor` reports it (warn when missing).
- Images: EXIF orientation applied, fitted within 4096 px, ICC profile converted to sRGB, saved as `media/<id>.jpg` for opaque JPEGs and `media/<id>.png` otherwise.
- `media/manifest.json` lists each clip's media (paths, size, fps, duration, HDR, tone-map method, denoiser) for later stages; `load_manifest()` and `load_clips()` read it and `project.toml`.
- Freshness: the stage is fresh when `raw/` and the parameters (recipe version, fps, available denoiser) are unchanged and every output exists; then ingest touches nothing. Each clip also has its own record (`ingest.<id>` in `state.json`), so adding a file only processes that file. Installing DeepFilterNet later makes the stage stale, so the voice gets re-cleaned.
- Every fallback prints one `warning:` line on stderr and is recorded in `state.json` under the ingest stage; warnings of clips skipped as unchanged are carried over.

Checked (acceptance):

- Fixtures (`tests/integration/test_ingest_fixtures.py`, `slow`, `mac`): every video mezzanine has `avg_frame_rate` = `r_frame_rate` = 30, no HLG/PQ transfer, and container and voice durations within one frame of the source; this includes the VFR talking clips and `prova clip è.mov`.
- HLG: a 10-bit HEVC BT.2020 HLG clip made with ffmpeg comes out tagged `bt709` primaries, transfer and matrix, with `scale_vt` on this Mac and different pixel values from the untone-mapped source. The `colorspace` fallback is tested with its warning and state record.
- Re-run with unchanged inputs leaves every file in `media/` and `project.toml` untouched (mtimes compared). A file added to `raw/` that sorts first gets `c2` while `c1` keeps its source and is not re-encoded. A `role = "broll"` override survives re-ingest.
- DeepFilterNet verified on arm64 macOS: the 0.5.6 `aarch64-apple-darwin` binary ran in the fixture test, all three talking clips report `denoiser = "deepfilternet"` and ingest raised no warnings. Ingesting the 21 s clip, the B-roll and the image took about 5 s.

Deviations and why:

- DeepFilterNet runs as the official release binary, not the `deepfilternet` pip package, which has no Python 3.12 wheel and requires numpy < 2.
- The `arnndn` fallback needs a model file, so `sh.rnnn` (RNNoise "somnolent-hogwash", speech in recording noise; not copyrighted per its README) ships inside the package and works offline.
- The provisional role uses the audio peak only; the analysis tickets replace it with speech and face evidence via `record_auto_role()`.
- `project.toml` is rewritten with `tomli-w` when new clips are added, which drops comments the creator wrote in it. Values, including overrides, are kept.
- Audio-only files and files ffprobe cannot read are skipped with a warning and get no ID.

Open issues:

- HEIC/HEIF photos are not decoded (Pillow has no HEIF support without `pillow-heif`); ingest fails with a hint to convert them. iPhones save photos as HEIC by default.
- `reelcut setup` does not exist yet; whichever ticket adds it should call `reelcut.audio.enhance.install_deep_filter()`. Until then, `deep-filter` can be put on PATH or the integration test installs it into the cache.
- The `zscale` path is not exercised on the build machine (Homebrew ffmpeg lacks zscale); CI's Ubuntu ffmpeg runs it in the HLG test.
