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
