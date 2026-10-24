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

## Phase 10: agent layer (ticket #16)

Built:

- The five canonical skills in `src/reelcut/templates/skills/` (`reelcut-edit`, `reelcut-plan`, `reelcut-look`, `reelcut-music`, `reelcut-review`), each a folder with `SKILL.md` and `name`/`description` frontmatter, from guide §9.2–9.6.
- The workspace template: `AGENTS.md` from §9.1, `CLAUDE.md` and `GEMINI.md` (both `@AGENTS.md`), the default `reelcut.toml` (unchanged), and `library/music/README.md` (licensing and the `tags.json` format) plus `library/brand/README.md`.
- `reelcut agents sync [--targets claude,codex,gemini,cursor]` (`reelcut.agents`, `reelcut.cli.agents`). It copies the skills into `.claude/skills/` (Claude Code) and `.agents/skills/` (Codex, Gemini CLI, Cursor), replacing only reelcut's own skill folders. `.agents/skills/` is always written. `init` now runs it for every target.
- Skill paths verified from each agent's official docs on 2026-10-24 and recorded with quotes and links in `docs/agents.md`.
- Tests (`tests/unit/test_agents.py`, CI): skills in every agent path after `init`; YAML frontmatter with the folder's name and a description of at most 1024 characters; sync restores edited skills and keeps other skills; target parsing; AGENTS.md links every skill file by a path that exists; the library README; and a check that every `reelcut …` command in `AGENTS.md` and the skills exists in the CLI with the flags it is given. Commands later tickets build are listed in `PENDING` in that test with their guide §7 flags; once registered, a command is checked against the real CLI instead. A further test holds the `AGENTS.md` promise that every command takes `--json`.

Deviations and why:

- `GEMINI.md` added to the template: Gemini CLI reads `GEMINI.md`, not `AGENTS.md`, by default, and supports `@file` imports.
- Gemini CLI and Cursor get `.agents/skills/` rather than `.gemini/skills/` or `.cursor/skills/`: both read it, it is the path Codex requires, and one shared copy is what `AGENTS.md` links to.
- Sync always writes `.agents/skills/`, even for `--targets claude`, so the paths in `AGENTS.md` always exist.
- Skill wording refined where the implementation or other contracts force it: §9.1's dot-separated quick reference became one command per line in a code block (so the command check can read it, and with the `docs edl` command added); exit codes and `--json` are stated once in `reelcut-edit` and `AGENTS.md`; `reelcut-review` says to raise `pad_out_ms` in the EDL `policy` instead of a per-segment `pad_out_ms`, which §6.4's segment shape does not have; the music skill names the `tags.json` fields and the credits file from guide Phase 8. Prohibitions were rephrased as the positive target where that kept the meaning.
- Claude Code plugin packaging is not built (spec #1 moves it to `ROADMAP.md`).

Open issues:

- `PENDING` in `tests/unit/test_agents.py` lists ingest (#5), analyze and setup (#7), look and look-asset (#9), words, plan draft, plan validate and docs edl (#11), render (#13), music (#14) and check (#15). Each ticket deletes its entry when it registers the command; the test then checks the real flags.
- Gemini CLI has been succeeded by Antigravity CLI (per the Gemini CLI docs). Its use of `.agents/skills/` and `AGENTS.md` comes from third-party guides only.
- Cursor sees each skill twice when both `.claude/skills/` and `.agents/skills/` are installed (noted in `docs/agents.md`).

## Phase 4, transcript analysers and contracts (ticket #6)

Built:

- `reelcut.analysis.models`: the §6.1 contract `ClipAnalysis` (with `ClipInfo`, `LanguageGuess`, `Word`, `Utterance`, `Pause`, `Span`, `Faces`, `FaceSample`), `TranscribedWord` (what an ASR backend returns) and `Retakes`/`RetakeCluster` for `analysis/retakes.json`. Times are seconds, rounded to milliseconds. `schemas/analysis.schema.json` is generated from `ClipAnalysis`; a test round-trips the guide's §6.1 example.
- Language data: `src/reelcut/lang/en.toml` and `it.toml` with the §6.2 prompts and lexicons, words a finished sentence does not end on, and caption rules (`max_chars_per_page`, `keep_with_next`). `reelcut.lang.load_language(code, dirs=None)` and `available_languages()` find languages by file name only; `[defaults] language` in the config now accepts `auto` or any code with a data file instead of a hard-coded `en | it`. A test adds a minimal Spanish file in a temp dir and runs the analysers with it.
- `analyse_transcript(clip, words, vad, language, confidence=, params=)`: filler tagging, utterances and completeness, pauses and unaligned voice, all pure. `find_retakes(clips, threshold=0.75)`: rapidfuzz `token_set_ratio` on normalised text, union-find, winner by complete, then newest, then fewest fillers. `pack_project(title, language, clips, retakes)`: the §6.3 packed index, pinned by `tests/unit/golden/packed.md` (`REELCUT_UPDATE_GOLDEN=1` rewrites it).

Verified (2026-10-24): rapidfuzz 3.14.6 `fuzz.token_set_ratio(a, b)` returns a float 0-100 and scores a word subset as 100.

Deviations and why:

- Completeness also treats an utterance as stopping short when its last word is in the language's `incomplete_endings` (articles, prepositions, auxiliaries), even with a full stop. The fixtures showed Whisper writes the abandoned "remember is" as "is." (ticket #4), so punctuation alone misses abandoned takes. An ellipsis counts as trailing off. "Long pause" is the utterance gap (500 ms) or the clip end.
- A lexicon match that is shorter than 80 ms or overlaps no VAD region keeps the word but leaves `filler` null. Dropping words outside VAD is ticket #7's job (the ASR stage).
- Start-only soft fillers also match after leading fillers ("Ehm, allora, ..." tags both).
- Utterances with fewer than three non-filler words never join a retake cluster: `token_set_ratio` scores any subset as identical, so "Yes." would otherwise cluster with every line containing "yes" and the draft would drop real lines.
- "Newest" is ordered by clip index, then position in the clip (a later clip is a later recording). With that total order the fewest-fillers rule only breaks exact ties, which real transcripts cannot produce; tests prove complete beats newest and newest beats fewer fillers.
- `pauses` includes the head silence (`after_word: null`) and the tail silence; gaps under 300 ms are not recorded. The packed index shows pauses of 0.7 s or more after the word they follow and places unaligned voice after the word before it.
- Packed index details the guide leaves open: the clip heading ends with a face position (left/centred/right from the median face centre) when face samples exist; consecutive soft fillers share one `~...~`; retake lines read `- R1: c2.s0 ≈ c1.s2 (1.00), c1.s1 ✗ (1.00) → draft keeps c2.s0` (each loser with its similarity to the winner) instead of the guide's single score; empty retake and static sections are omitted.
- No `retakes.schema.json`: the ticket asks only for the analysis schema. The model exists for the analyze stage to write `retakes.json`.

Open issues: none.

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

## Phase 6, EDL models and resolver (ticket #10)

Built:

- `reelcut.edl.models`: the §6.4 EDL (`Edl`, `Segment`, `Policy`, `DropRange`, the six event types as a discriminated union on `type`, `EdlCaptions`, `EdlMusic`) and the §6.5 timeline (`Timeline`, `Run`, `TimelineWord`, timeline events in frames, `TimelineCaptions`, `TimelineBrand`, `FormatSpec` with safe zones). `parse_edl(data)` turns schema errors into an `EdlError`. Field descriptions are written for the host agent.
- `reelcut.edl.refs`: word, utterance and segment references with the errors §6.4 and Phase 6 ask for ("`c1.s40` does not exist; c1 has s0-s37", cross-clip ranges, reversed ranges, duplicate or reference-shaped segment IDs, segments keeping the same word).
- `reelcut.edl.resolve.resolve(clips, edl, config, beats=None) -> Resolution(timeline, warnings, stats)`: §6.5 steps 1-10, pure. `runs.py` holds steps 1-5 and `events.py` steps 9-10. Every error found is raised at once as `EdlError` (exit 1) with a `problems` list of `Issue(code, message, hint)`; warnings come back in `Resolution.warnings`.
- `schemas/edl.schema.json`, `schemas/timeline.schema.json` and `renderer/src/types.gen.ts`, generated by `scripts/gen_schemas.py` with json-schema-to-typescript (now a renderer devDependency).
- Tests (CI): `test_edl_refs.py`, `test_resolver.py`, `test_edl_events.py`, `test_edl_models.py` (round-trips the guide's §6.4 example) and `test_resolver_properties.py` (Hypothesis, 300 examples each: runs never overlap in output or in source, duration is the sum of runs, kept words lie whole inside their run with their length intact, no run crosses a removed word, source times sit on the frame grid, reordering segments reorders the output). Mutating the midpoint clamp or the edge-word guard makes the properties fail. `just edl-coverage` (a new CI step) fails under 95% line coverage of `src/reelcut/edl`; it measures 99.9%.

Deviations and why:

- Pause tightening keeps `max_pause_ms / 2` on each side of the cut, in place of the pads, so a tightened pause is exactly `max_pause_ms` (§6.5 step 2). Pads apply at edges next to removed words and segment ends.
- Step 4's merge joins only runs split by a pause. Runs split by a removed word or a drop range never merge, because merging would bring back the word that was cut and break the "no run crosses a removed word" property.
- Words outside a segment count as removed at its edges, so a segment's padding stops at the midpoint to the next word even when that word is in another segment.
- Snapping: run edges go to the nearest frame but never into their own edge words; midpoint limits snap to their nearest frame, so segments that meet in a gap share a boundary frame and are not a jump cut; drop-range edges are never crossed. A zero-length run is dropped with the short-run warning.
- A word whose midpoint lies inside a drop range is removed. Two segments keeping the same word is an error, so every anchor has one place in the output.
- Reframing takes one median face centre per run, not per shot inside a run.
- Defaults the guide leaves open: zoom scale 1.15, a zoom without `hold_until` holds to the end of its `at` anchor, push needs a segment ID and spans it, B-roll and image mode `full`, image motion `kenburns`. Nearest-kept-word ties go to the earlier word. B-roll shorter than its span is cut short with an `asset_short` warning. Full-frame images count as full-frame overlays for the overlap error; a title over any B-roll or image (pip included) warns.
- The timeline adds `language`, the language's `max_chars_per_page` and `keep_with_next` (loaded from `reelcut.lang`) to the caption settings, a `src` path per overlay (the asset's mezzanine, or its source when there is none), `face` per run, and `music_path` = `build/music.wav` unless the music mode is `none`. Safe zones are constants in `resolve.py` (9x16 bottom 20%, right 12%). `beats` are output seconds, supplied by the caller.
- The timeline schema is generated in serialization mode with defaults required, so the renderer's types have no optional fields the resolver always writes.
- npm 11.6.0 dropped the platform-specific optional packages from the lockfile when adding json-schema-to-typescript (see `docs/dependencies.md`); they were merged back by hand.

Open issues:

- `plan draft`, `plan validate`, the §6.6 summary and "validating the draft for each fixture succeeds" are ticket #11. `ResolveStats` carries the summary counts (words total and kept, hard fillers removed, pauses tightened, runs per segment).
- `reelcut.workspace.read_edl_policy` still reads `policy` loosely for `config show`; #11 can switch it to `parse_edl(...).policy.model_dump(exclude_none=True)`.

## Phase 7b, Remotion renderer (ticket #12)

Built:

- `renderer/src/Root.tsx`: composition `Reel` with `calculateMetadata` (`src/props.ts`): width and height from the chosen format, fps and duration from the timeline. Props (`ReelProps`): `{ timeline, format, source: { width, height }, video, font_file }`; `render/compose.py` (#13) writes them.
- `lib/camera.ts`: cover-fit, face centre placed at x 0.5 / y 0.4 and clamped so no edge shows; scale = run base scale (jump-cut punch), replaced by a zoom (`snap`: 4-frame spring; `smooth`: 10-frame cubic ease, both easing back out unless the zoom ends on a cut) and multiplied by a push-in (linear 1.0 to scale). `layoutFor` picks fit-blur for a portrait source in a landscape format.
- Layers: `BaseVideo` (`OffthreadVideo` of `assembled.mp4`, with a blurred, darkened cover copy behind the sharp box in fit-blur), `Broll` (`full`: cover with a 6-frame crossfade in and out, muted, `trimBefore` = `asset_in_s`; `pip`: rounded card with a shadow, upper third on portrait formats and top right on landscape; images with Ken Burns 1.0 to 1.08 plus a 3% pan), `Titles` (bold card on `brand.primary`, black or white text by luminance, spring in, 8-frame spring out), `Captions`.
- `lib/captions.ts` `pageCaptions`: pages break on `max_words_per_page`, the language's `max_chars_per_page`, a width cap measured with `@remotion/layout-utils` `measureText`, after a sentence end and at a 700 ms silence; a full page never ends on a `keep_with_next` word; a single word wider than the page gets a `fit` font scale. The break points become `pageBreakAfter` on `Caption[]`, which `createTikTokStyleCaptions` turns into pages. A page stays up to 500 ms after its last word, or until the next page. Styles: `pop` (active word in `highlight_color` with a 1.08 spring pop), `karaoke` (spoken words in `highlight_color`), `clean` (no per-word colour); emphasis words take `brand.accent`. Captions sit 3% above the bottom of the format's safe zone, centred in it.
- `lib/fonts.ts`: brand font file through `@remotion/fonts` `loadFont` + `staticFile`, else Inter 800 bundled from `@fontsource/inter`.
- Tests: vitest `camera.test.ts` (cover, clamping on every edge, never below cover, fit-blur layout, punch per run, snap/smooth zoom timing, ease-out vs a cut, push linearity, zoom-in-push composition, per-run framing with no smoothing across cuts) and `captions.test.ts` (word cap, width cap with "precipitevolissimevolmente", fit scale, uppercase measuring, character cap, keep-with-next, sentence and silence breaks, page timing and emphasis). `tests/integration/test_renderer_cli.py` (`slow`, `renderer`) renders the hand-made `tests/fixtures/renderer/timeline.json` (validated against the pydantic `Timeline`) with the Remotion CLI.

Versions pinned: @remotion/layout-utils and @remotion/fonts 4.0.538 (same as every other `@remotion/*`), @fontsource/inter 5.3.0. CLI flags and APIs are in `docs/dependencies.md`.

Checked (acceptance):

- vitest: 30 tests pass; `tsc --noEmit` clean.
- Hand-made timeline (120 frames, 2 runs with a punch, snap zoom, pip B-roll, full Ken Burns image, title, 9 Italian words): `render` to 9x16 gives 1080x1920, 16x9 gives 1920x1080 and 16x9 `--scale=0.5` gives 960x540, each with 120 frames at 30/1 (ffprobe `-count_frames`). About 17-26 s per full-size render on the build machine, concurrency 4.
- Stills I opened (frames 20, 46, 70, 110 of each format; source is the Armstrong photo cropped so the face is at (0.689, 0.267)). 9x16 start: title card "3 ore → 10 minuti" dark with white text near the top of the safe zone; caption "Ho costruito tutto" with "costruito" yellow and popped, white words with black stroke, spaced, at about 75% height, clear of the right UI strip. 9x16 cut (frame 46, punch 1.08): image visibly tighter and shifted toward the face than frame 20; "precipitevolissimevolmente" alone on its page, shrunk to fit inside the safe width. 9x16 zoom (frame 70, 1.2): clearly tighter; the pip test card sits in the upper third with rounded corners and shadow, and covers the face, because this face sits high in the frame (resolver warns only for titles over B-roll). 9x16 image: Mandelbrot fills the frame, caption "Ecco come." with "Ecco" in the orange accent (emphasis) and "come." yellow (active). 16x9: fit-blur shows the whole vertical frame centred over a blurred, darkened copy with no hard edges; title and captions are centred; the pip card moved to the top right, clear of the speaker; the full image covers 16:9.

Deviations and why:

- No `@remotion/google-fonts`: it loads font files from Google at render time, which breaks reelcut's offline rule. The default Inter ships in `@fontsource/inter` and is bundled; any other `captions.font` needs a file in `library/brand/fonts` (compose passes it as `font_file`), otherwise the renderer uses Inter and compose should warn.
- Paging is reelcut's own (`pageCaptions`); `createTikTokStyleCaptions` alone pages only by time and silence, so the word, character and width caps are expressed as `pageBreakAfter`, the library's own hook.
- The renderer takes the assembled video's pixel size as a prop (`source`) instead of probing it in the browser; compose knows it from ffprobe.
- Zoom and push frames are taken as given; a zoom eases back over its easing length after `end` only while the same run continues.

Open issues:

- The logo (`brand.logo`) is not drawn; the guide names no logo layer.
- "Hide captions during full B-roll if configured" has no config key in the timeline; captions always show (the guide's default).
- Caption width is measured with spaces between words but drawn with a 0.4em gap; the 12% headroom covers the difference.
- Glyphs outside Inter's latin and latin-ext subsets (for example "→") fall back to a system font.

## Phase 4, speech: VAD, speech-to-text and language (ticket #7)

Built:

- `reelcut analyze <slug> [--clip c1] [--json]` (`reelcut.analyze.analyze_project`). It calls `config.ensure_supported()` first (so `fillers_backend = "crisper"` exits 2), takes the project lock, reads `media/manifest.json` and the roles in `project.toml`, sends every clip with audio whose state record (`analyze.<id>`) is stale to one speech-to-text worker, runs the #6 analysers, and writes `analysis/<clip>.json`, `analysis/retakes.json` and `analysis/packed.md`. A re-run with nothing changed is a no-op that starts no worker; `--clip` re-transcribes one clip and repacks the project. Images and silent clips get an analysis file with no words and `language: null`.
- `reelcut.asr`: `transcribe_clips(jobs, backend=, model=)` runs `python -m reelcut.asr.worker` as a child process while the parent holds the machine-wide heavy-model lock, so the model never loads in the reelcut process and its memory goes back to the system when the child exits. The worker runs Silero VAD, language ID and transcription for every job with one model load and reports its pid and peak RSS. `REELCUT_ASR_WORKER` replaces the worker command (the CI tests use a scripted stand-in).
- `ASRBackend` protocol (guide §8 Phase 4) in `reelcut.asr.backends`, with `MlxWhisper` (default on arm64 macOS) and `FasterWhisper` (default elsewhere; CPU, int8). Both use the language file's filler prompt as `initial_prompt`, `word_timestamps`, `condition_on_previous_text=False` and `hallucination_silence_threshold=2.0`, and decode only speech windows through `clip_timestamps`.
- Silero VAD through onnxruntime (`reelcut.asr.vad`): min speech 250 ms, min silence 100 ms, 30 ms pad, threshold 0.5, ported from the reference `get_speech_timestamps`.
- Language: each clip is detected among the languages with a data file, from up to 30 s of its VAD speech; the project language is the language with the most A-roll utterance time (`reelcut.analysis.project_language`), or `defaults.language` when set, which also forces that language on every clip.
- `reelcut setup [--json]` downloads DeepFilterNet (`install_deep_filter()`), Silero VAD and the Whisper model for this platform's backend (or the workspace's `asr.backend`/`asr.model`) into the cache; already-present items are reported, not fetched. `doctor` now has `vad model` and `asr model` checks (warn until setup has run) instead of the generic `models` check.

Pinned: Silero VAD v6.2.3 (`silero_vad.onnx`, SHA-256 checked), `mlx-community/whisper-large-v3-turbo` @ `a4aaeec0`, `dropbox-dash/faster-whisper-large-v3-turbo` @ `0a363e91`. Details in `docs/dependencies.md`; licences in `THIRD_PARTY.md`.

Checked (acceptance), `tests/integration/test_analyze_fixtures.py` (`slow`, `mac`, `models`), parametrised over both backends, all 11 tests pass (3.5 min, including the faster-whisper run forced through `project.toml`):

- Languages: `en_talking` and `prova clip è` detected `en`, `it_talking` `it` (confidence 0.999 to 1.0 on both backends); project language `en`.
- Silences: all 16 known silences of the EN and IT fixtures (head, between utterances, around the filler, tail) match a VAD gap within ±150 ms, so 100% against the 90% bar.
- Retakes: in both clips the abandoned take is `complete: false`, the full take `complete: true`, and they share a cluster whose winner is complete.
- `packed.md` for a 5 min 13 s clip (`en_talking` concatenated 15 times): about 2,040 tokens (chars/4), under 2,500.
- Memory and lock: the worker reports a peak RSS of about 0.9 GB (mlx) and 2.0 to 2.3 GB (faster-whisper); after analyze its pid no longer exists and neither `mlx_whisper` nor `faster_whisper` is imported in the test process. With the heavy-model lock held by another thread, `analyze` prints `waiting for the heavy-model lock (test-holder ...)` and continues once it is released. The CI stand-in worker checks that the lock is held while it runs.
- Timing on the build machine: transcribing the EN and IT fixtures (21 s each) in one worker takes about 8 s with mlx-whisper and 25 s with faster-whisper, model load included.

Deviations and why:

- Whisper skipped the whole last sentence of the EN fixture when decoding the full 21 s file (both backends, with or without the hallucination guard and prompt). Each backend therefore decodes VAD speech grouped into windows of at most 28 s (`clip_timestamps`), and any speech region of 0.5 s or more that still has no word is transcribed again on its own.
- Words are fitted to VAD after transcription: a word outside every region is dropped, and a word overlapping a region is clamped to the region it overlaps most. Whisper stretched "is..." of the abandoned take across the 0.9 s pause, which hid both the pause and the incomplete utterance; clamping restores them.
- The heavy-model lock is held by the parent for the life of the worker rather than taken inside the worker, so the stand-in worker in CI can verify it and a waiting message reaches the CLI.
- The `ASRBackend` methods follow the guide's signatures, plus a `candidates` argument to `detect_language` so detection only picks languages reelcut has data for. Confidence is the model's own probability for the chosen language.
- `setup --music` exits 2 with "not available in this build yet" until the music ticket (#14) implements it; `setup --crisper` exits 2 like the config value. The renderer (#13) and face models (#8) are not installed by setup yet; those tickets add their steps to `reelcut.setup.run_setup`.
- Models live under `<cache>/models/huggingface` (Hugging Face cache layout), not the default `~/.cache/huggingface`, so `reelcut clean` and the cache directory cover them.

Open issues:

- On the 5-minute concatenation Whisper sometimes attaches the first word of the next take to the end of the abandoned one ("... remember is The"); the retake still clusters, but the draft would keep a stray word. Check (#15) re-transcribes and will flag it.
- `project.toml` is an input of the analyze stage, so role finalisation (#8) writing it marks analyze stale once; the next run is then a repack, not a re-transcription (per-clip records stay fresh).

## Phase 4, visual: shots, static stretches, faces, roles and the asset catalogue (ticket #8)

Built:

- `reelcut analyze` now also fills `shots`, `static` and `faces` in each `analysis/<clip>.json`, finalises roles, and writes `analysis/assets.md`. The per-clip state record covers the mezzanine as well as the 16 kHz WAV, and the analyze recipe is 2, so existing projects re-analyse once.
- Shots: PySceneDetect `ContentDetector` (default threshold 27) through a `SceneManager` with `auto_downscale`, on the mezzanine (`reelcut.vision.motion.find_shots`). A clip without cuts is one shot.
- Static: ffmpeg decodes grey frames at 2 fps, 320 px wide (`reelcut.media.ffmpeg.read_frames`, a new streaming raw-frame reader), and OpenCV `absdiff` gives the mean difference between neighbours. `reelcut.analysis.find_static` (pure) keeps runs below 1.5 (of 255), removes VAD speech from them, and keeps pieces of 2 s or more; the last sampled frame stands for the rest of the clip.
- Faces: MediaPipe Tasks `FaceDetector` with the BlazeFace full-range model at 2 fps on frames scaled to 640 px on the long side, largest face per frame, boxes normalised to the frame. It runs in `python -m reelcut.vision.worker` while the parent holds `heavy_model_lock("faces")`, one process for all clips. YuNet (`cv2.FaceDetectorYN`) takes over when the MediaPipe model is missing or MediaPipe fails to load; analyze then prints `warning: face detection fell back to YuNet: <reason>` and records it in `stages.analyze.warnings` of `state.json`. `REELCUT_FACE_WORKER` replaces the worker; the unit tests use an autouse stand-in that reports a face in every sampled frame.
- Roles: `reelcut.analysis.finalise_role` (pure): images stay images; a video is A-roll when VAD speech covers more than 30% of it and a face is in more than 50% of the sampled frames, otherwise B-roll. analyze stores it with `ingest.record_auto_role`, only when it changed, so a creator's `role` override in `project.toml` wins and the file is not rewritten on every run.
- `assets.md` (`reelcut.analysis.pack_assets`): one section per B-roll clip and image with ID, file name, source path, duration (or "still image"), resolution, shot count, the contact sheet path `contact/<id>.png` and a blank `description:` line. Descriptions the agent writes are read back before every repack and kept. The sheets themselves come with the look ticket (#9); the path is fixed now (`ProjectPaths.asset_sheet`).
- `reelcut setup` downloads both face models (SHA-256 checked); `doctor` has a `face model` check that warns when only YuNet, or nothing, is in the cache.
- Fixtures: the talking clips' presenter is now the public-domain Armstrong photo (cropped to the face, 720 px wide on the 1080x1920 frame) instead of a skin-coloured disc, and it holds still through a silent tail that is now 3 s instead of 1 s. The ground truth JSON is regenerated; the fixture test expects the 3 s tail.

Pinned: `blaze_face_full_range.tflite` float16 version 1 (Apache-2.0, from its model card) and OpenCV Zoo `face_detection_yunet_2023mar.onnx` at commit `48b10fa5` (MIT). APIs and URLs in `docs/dependencies.md`, licences in `THIRD_PARTY.md`.

Checked (acceptance):

- Face photo (`tests/integration/test_faces.py`, `models`): MediaPipe finds one face in `neil_armstrong_960.jpg` at centre (0.61, 0.28), width 0.18, score 0.88; with only the YuNet model in a cache, `detect_faces` reports `yunet` with the reason "the MediaPipe face model is not in the cache" and finds the same face within 0.06.
- Static tail (`test_analyze_fixtures.py`, both backends): each talking fixture has exactly one static stretch, starting within 0.6 s of the 3 s silent tail and ending at the clip end (EN: 20.0 to 22.83 s), and `packed.md` lists it under "Static / no-speech stretches".
- Roles: the B-roll fixture is `broll`, the image `image`, and the three talking clips `aroll`, both in the `--json` output and as `auto_role` in `project.toml`; a face is found in every sampled frame of the talking clips.
- `assets.md` on the fixtures lists `b1 · broll.mp4` (6.0s, 1920x1080, 1 shot) and `i1 · image.png` (still image, 1600x1200, 1 shot), each with its contact sheet path and a blank description, and no talking clip.
- YuNet fallback warning: the CI test with the stand-in worker reporting YuNet checks the `warning:` line on stderr and the entry in `state.json`.
- Timing: analysing the EN fixture, the B-roll and the image takes about 9 s on the build machine with mlx-whisper, face pass and shot detection included.

Deviations and why:

- BlazeFace full range instead of the guide's unnamed BlazeFace variant (usually short range): on a 1080x1920 frame short range missed the face below about 15% of the frame width, and full range found it at 6%. Phone footage shot from a tripod has faces that small.
- A video with speech but no face is B-roll, as the rule says. The fixtures therefore needed a real face; screen recordings with a voice-over will be classified B-roll and need a `role = "aroll"` override in `project.toml`.
- The contact sheet linked from `assets.md` does not exist until #9 writes it.

Open issues:

- The static threshold (1.5 of 255 at 2 fps) is tuned on synthetic footage; real phone noise on a locked-off shot may sit above it, so static stretches in real footage may be missed. Check it in the morning test.
- Face samples are absent for frames without a face, so `face_sample_count` (from the duration) and the worker's ffmpeg `fps=2` frame count can differ by one frame; the ratio is only used against the 50% threshold.

## Phase 6, CLI: plan draft, plan validate, words, docs edl (ticket #11)

Built:

- `reelcut plan draft <slug> [--force] [--json]` (`reelcut.plan.draft_project`, pure logic in `reelcut.edl.draft`). One segment per kept A-roll utterance, clips in ID order, segment IDs `c1-s0` (the utterance ID with a hyphen, so it can never parse as a reference) and the utterance text as `note`. Retake cluster members other than the winner are left out, which also drops an abandoned take whose complete retake won; an incomplete utterance with no retake stays. Utterances made only of hard fillers are left out. Policy `drop_fillers: "hard"`, `jumpcut_punch: true`, no events, `rationale: "deterministic draft"`, `language` from `project_language`, `title` from `[project] title`. Music `generate`, seed 1, BPM in the middle of the guide's band for the pace of the kept utterances (non-filler words per second of utterance time: under 2.3 → 90, 2.3 to 3 → 103, over 3 → 118) and a neutral prompt of matching energy that always says "instrumental". An existing `edl.json` is refused with exit 1 and a hint naming `--force`.
- `reelcut plan validate <slug> [--json]` (`reelcut.plan.validate_project`): reads `edl.json`, every `analysis/<clip>.json` and, when the music stage has written it, the `beats` of `build/music.json`; resolves with the #10 resolver; writes `build/timeline.json`; marks the `plan` stage done (inputs `edl.json`, `analysis/`, `project.toml`). The summary (`reelcut.edl.summary`) has the guide §6.6 shape plus words per second on the duration line (the music skill tells the agent to pick the BPM from it). Warnings and errors print one line each with their fix, capped at 20 lines with a pointer to `--json`, so output stays under 30 lines. An EDL that does not resolve prints every error and exits 1; `--json` gives `{ok: false, valid: false, errors: [{code, message, hint}], ...}`.
- `reelcut words <slug> <from> [<to>] [--json]`: the words of a range of word or utterance IDs in one clip, grouped under their utterance (`✗` for incomplete), five per line as `c1.w5 {ehm,} 4.87-5.17` (hard fillers in braces, soft in tildes, source seconds). Capped at 30 lines; `--json` has every word.
- `reelcut docs edl [--json]`: prints `src/reelcut/reference/edl.md` through `importlib.resources`, so it works from any directory and from the installed wheel (checked: the wheel contains `reelcut/reference/edl.md`). `docs/edl.md` is a symlink to it. A test checks that every EDL field and every issue code the resolver raises is named in the reference.
- Removed `words`, `plan draft`, `plan validate` and `docs edl` from `PENDING` in `tests/unit/test_agents.py`. `reelcut.analyze._title` is now the public `project_title`.

Checked (acceptance):

- `tests/integration/test_plan_fixtures.py` (`slow`, `mac`, `models`): on the EN and IT fixtures, ingest, analyze, `plan draft` and `plan validate` succeed; the draft has 4 of the 5 utterances (the abandoned take is skipped, its retake kept) and removes the hard filler. 6 tests pass in 22 s.
- By hand on the IT fixture: `✓ edl.json valid · language it · 4 segments → 5 runs` / `Duration 10.7s (limit 60s) · words kept 31/39 · 2.9 words/s · hard fillers removed 1 · pauses tightened 0` / `Hook (first 3s): "Ciao, bentornati sul canale. Oggi, vi faccio…"` / `Events: none` / `→ …/build/timeline.json`. EN: 4 segments → 5 runs, 11.2 s, 37/45 words. A second `plan draft` exits 1.
- `reelcut words demo c1.s0 c1.s1` prints the 14 words of the IT fixture's first two utterances with IDs and times; `reelcut docs edl` from `/` prints the reference.
- `just edl-coverage`: 99.9% of `src/reelcut/edl` (draft and summary 100%).

Deviations and why:

- One segment per utterance rather than one per contiguous block: moving the hook to the front is then moving one entry, and the resolver splits at the inter-utterance pauses anyway.
- The music prompt depends on pace only, not language: the bed is instrumental, so there is nothing language-specific to say.
- The draft and summary are pure modules in `reelcut.edl` (counted by `just edl-coverage`); file I/O is in `reelcut.plan`, outside it.

Open issues:

- `reelcut.workspace.read_edl_policy` (for `config show`) still reads `policy` loosely rather than through `parse_edl`.

## Phase 5: look, look-asset and asset contact sheets (ticket #9)

Built:

- `reelcut look <slug> <clip> <t0> <t1> [--frames 8] [--out PATH] [--json]` (`reelcut.look.look_range`). Times are source seconds. Frames are taken at the centres of `--frames` equal slices of the range (1 to 24), each decoded with an input seek (`-ss` before `-i`) at 320 px tall. The sheet is 1600 px wide: a header (clip, file, range, first and last word ID), the frames in a centred grid with a timestamp under each and the nearest face sample (within 0.25 s) drawn as a cyan box, then a waveform of the range from the 16 kHz WAV with VAD regions shaded green, pauses hatched, frame times as blue lines, a time axis, and the words placed by start time in as many rows as needed so labels never overlap (hard fillers red, soft fillers orange, a bar under the waveform for each word's span), and a legend. Default output `contact/<clip>_<t0>-<t1>.png`. Prints a one-line description (words, fillers, frames with a face), the budget count and the path.
- Look budget: every `look` adds one to `look_count` in `state.json`. Past `edit.look_budget` it prints `warning: look budget exceeded (N of B sheets); ...` (stderr, and in `warnings` under `--json`) and still writes the sheet, exit 0. A range past the clip end is clamped with a warning; ranges over 20 s get a warning, as the look skill says.
- `reelcut look-asset <slug> <asset-id> [--json]` (`reelcut.look.look_asset`) redraws `contact/<id>.png` for a B-roll clip (6 frames across the clip) or image (the image up to 720 px tall, no timestamp). It does not count against the budget: describing each asset once is part of every edit, and analyze has already drawn the same sheet.
- `analyze` writes `contact/<id>.png` (`ProjectPaths.asset_sheet`, the path #8's `assets.md` already links) for every clip whose final role is broll or image, when the clip was analysed in that run or its sheet is missing. The sheets are outputs of the `analyze` stage, so deleting one makes the next analyze redraw it.
- Drawing is in `reelcut.look.sheet` (pure Pillow over decoded frames); media reading and the budget are in `reelcut.look`.
- Removed `look` and `look-asset` from `PENDING` in `tests/unit/test_agents.py`; both accept `--json`.

Checked (acceptance):

- Smoke tests (`tests/unit/test_look_cli.py`, CI): on an ingested and analysed tiny project, the `look` sheet is 800 to 1600 px wide, at least 400 px tall and not blank (pixel standard deviation > 20); a second `look` with `look_budget = 1` warns `look budget exceeded (2 of 1 sheets)`, exits 0 and writes the sheet, and `state.json` has `look_count` 2; every `contact sheet:` link in `assets.md` (`contact/b1.png`, `contact/i1.png`) exists and is at most 1600 px wide; a deleted asset sheet comes back on the next analyze; `look-asset` redraws it without counting; a wrong clip, an A-roll `look-asset`, an image `look`, an empty range, a range past the end and `--frames 0` each exit 1 with a hint.
- Visual check, by opening the PNGs from real ingest and analyze (mlx-whisper, BlazeFace) of the fixtures:
  - IT fixture, `look it c1 3.5 11`: every word label is legible at 18 px; "ehm," is red and the rest black; the cyan face box sits on the face in all 8 frames; the 1.3 s pause after "video." and the gap before "La cosa" are hatched and the VAD regions shaded. On the first try "più" and "è..." drew as boxes: Pillow's bundled font (Aileron) has no Latin-1 accents, so the sheet now uses a vendored Latin cut of DejaVu Sans; redrawn, both read correctly.
  - EN fixture, the whole 22.8 s clip at 12 frames: two rows of 8 and 4 frames; labels stack into up to five rows where speech is dense and stay legible; "um," is red; the static 3 s tail shows as hatched pause.
  - Soft fillers: on the tiny test project's sheet a sentence-initial "So" (a start-only soft filler) is orange next to the red "um". The fixtures have no soft filler.
  - `contact/b1.png` (testsrc2 B-roll, 6 frames in a 2x3 grid, 1178 px wide) and `contact/i1.png` (the Mandelbrot image, 992 px wide) are clear, with header and timestamps legible.

Deviations and why:

- `look-asset` does not count against `look_budget` (guide §7 says only `look` does; see above).
- Sheets for a range are always 1600 px wide, even for a few portrait frames, so word labels have room; asset sheets are as wide as their frames.
- Vendored font (`src/reelcut/look/fonts/`, 81 KB, licence alongside and in THIRD_PARTY.md), for the reason above.

Open issues:

- The look counter is read and written without the project lock, so two `look` calls at the same instant could count once; it is only a warning threshold.
- In a long dense range, word labels can stack several rows deep; the look skill already steers agents to ranges under 20 s.
