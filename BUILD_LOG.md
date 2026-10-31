# Build log

What was built for motion-studio v0.1.0, ticket by ticket: versions pinned, deviations from the build guide and why, and open issues. Spec: GitHub issue #1. Guide: `video-harness-build-guide.md`.

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

Repository: the private remote `pumpkit-io/motion-studio` already exists (spec #1 overrides the guide's "no remote"), so Phase 0 verified it instead of running `git init`. Work happens on `feat/motion-studio-v0.1.0`; each ticket merges into it.

Also noted: a stale Intel `/usr/local/bin/python3.9` makes `uv python list` error ("Bad CPU type"); `uv python find 3.12` and everything that pins 3.12 work. `pre-commit` is not installed globally; it comes from the dev group (`uv run pre-commit install`).

## Phase 1: scaffold and tooling (ticket #2)

Built:

- The §4 layout under `src/motion_studio/` as empty modules with docstrings, `tests/unit`, `tests/integration`, `tests/fixtures`, `schemas/` and `scripts/gen_schemas.py` (an empty contract registry that later tickets fill).
- `pyproject.toml` (hatchling, Python `>=3.12,<3.14`, console script `motion-studio = "motion_studio.cli:app"`), extras `mac` (mlx-whisper, arm64 macOS marker) and `cpu` (faster-whisper), and a dev dependency group. `uv.lock` is committed.
- `motion-studio --help` and `motion-studio --version` through a Typer app in `src/motion_studio/cli/`. `APP_NAME` lives once, in `src/motion_studio/__init__.py`; `__version__` reads the package metadata.
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

- `motion_studio.errors`: `UserError` (exit 1), `DependencyError` (2), `InternalError` (3), each with an optional one-line `hint`. The Typer group in `motion_studio.cli` maps every failure onto these codes, including Click usage errors (which Click exits with 2, the code reserved for a missing dependency). With `--json`, errors print `{"ok": false, "error", "hint", "exit_code"}`; unexpected exceptions exit 3, with the traceback behind `MOTION_STUDIO_DEBUG=1`.
- `motion_studio.config`: Pydantic models for every §5.1 section (`extra="forbid"`, so typos fail with the file and key named) and `load_config(workspace, slug=None, edl_policy=None)`, which deep-merges defaults < `motion-studio.toml` < `project.toml` (minus its `[project]` and `[clips]` tables) < the EDL `policy` object (applied to `[edit]`). `Config.ensure_supported()` raises exit 2 "not implemented in v0.1.0" for `fillers_backend = "crisper"`.
- `motion_studio.paths`: `find_workspace` walks up to `motion-studio.toml`; `ProjectPaths` holds the §5 layout; slugs are validated (`[a-z0-9][a-z0-9-]*`). The cache is platformdirs' user cache dir: `~/Library/Caches/motion-studio` on macOS, `~/.cache/motion-studio` on Linux, overridable with `MOTION_STUDIO_CACHE_DIR`.
- `motion_studio.state`: `state.json` with per-stage `{status, input_hash, inputs, params_hash, outputs, finished_at, warnings, error}`; `stage_is_fresh`, `stage_status`, `mark_done`, `mark_failed`, `record_warning`; a per-project `flock` lock that fails fast; the machine-wide heavy-model lock (`<cache>/locks/heavy-model.lock`, blocking `flock`, optional timeout and wait callback); and the free-disk guard `ensure_free_disk` (20 GB default, `MOTION_STUDIO_MIN_FREE_GB` overrides).
- `motion_studio.media.ffmpeg`: `run_ffmpeg` and `run_ffprobe` take argument lists only (a string raises `TypeError`), run without a shell, raise `FFmpegError` carrying the last 20 stderr lines, and report `-progress` positions in seconds. `ffmpeg_caps()` probes the installed ffmpeg's version, filter list, filter-script option and fps-mode option.
- Commands `init`, `new`, `status`, `config show`, `clean`, `doctor`, all with `--json`. The workspace template (`src/motion_studio/templates/workspace/`) holds a placeholder `AGENTS.md`, `CLAUDE.md`, the §5.1 `motion-studio.toml` and the library and projects directories.
- `schemas/config.schema.json`, generated by `just schema`; `just schema-check` in CI fails when it is stale.
- CI installs Ubuntu's ffmpeg so the runner and probe tests run on Linux against an older ffmpeg.

Verified against the installed versions (2026-10-24):

- ffmpeg 9.0.1 accepts `-/filter_complex <file>` and has removed `-filter_complex_script` ("Unrecognized option"); `-fps_mode` is listed in `-h full`. The runner probes both by a trial run and the help text, never by version number.
- Typer 0.27.3 vendors Click as `typer._click`; the standalone `click` package in the venv is a different copy, so the exit-code mapping catches `typer._click.exceptions`.
- `platformdirs.user_cache_path("motion-studio")` is `~/Library/Caches/motion-studio` on this Mac.

Deviations and why:

- Cache dir: the guide suggests `~/.cache/motion-studio`; platformdirs' macOS default (`~/Library/Caches/motion-studio`) is used instead, as the guide allows, with the env override for tests and unusual setups.
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

- The five canonical skills in `src/motion_studio/templates/skills/` (`motion-studio-edit`, `motion-studio-plan`, `motion-studio-look`, `motion-studio-music`, `motion-studio-review`), each a folder with `SKILL.md` and `name`/`description` frontmatter, from guide §9.2–9.6.
- The workspace template: `AGENTS.md` from §9.1, `CLAUDE.md` and `GEMINI.md` (both `@AGENTS.md`), the default `motion-studio.toml` (unchanged), and `library/music/README.md` (licensing and the `tags.json` format) plus `library/brand/README.md`.
- `motion-studio agents sync [--targets claude,codex,gemini,cursor]` (`motion_studio.agents`, `motion_studio.cli.agents`). It copies the skills into `.claude/skills/` (Claude Code) and `.agents/skills/` (Codex, Gemini CLI, Cursor), replacing only motion-studio's own skill folders. `.agents/skills/` is always written. `init` now runs it for every target.
- Skill paths verified from each agent's official docs on 2026-10-24 and recorded with quotes and links in `docs/agents.md`.
- Tests (`tests/unit/test_agents.py`, CI): skills in every agent path after `init`; YAML frontmatter with the folder's name and a description of at most 1024 characters; sync restores edited skills and keeps other skills; target parsing; AGENTS.md links every skill file by a path that exists; the library README; and a check that every `motion-studio …` command in `AGENTS.md` and the skills exists in the CLI with the flags it is given. Commands later tickets build are listed in `PENDING` in that test with their guide §7 flags; once registered, a command is checked against the real CLI instead. A further test holds the `AGENTS.md` promise that every command takes `--json`.

Deviations and why:

- `GEMINI.md` added to the template: Gemini CLI reads `GEMINI.md`, not `AGENTS.md`, by default, and supports `@file` imports.
- Gemini CLI and Cursor get `.agents/skills/` rather than `.gemini/skills/` or `.cursor/skills/`: both read it, it is the path Codex requires, and one shared copy is what `AGENTS.md` links to.
- Sync always writes `.agents/skills/`, even for `--targets claude`, so the paths in `AGENTS.md` always exist.
- Skill wording refined where the implementation or other contracts force it: §9.1's dot-separated quick reference became one command per line in a code block (so the command check can read it, and with the `docs edl` command added); exit codes and `--json` are stated once in `motion-studio-edit` and `AGENTS.md`; `motion-studio-review` says to raise `pad_out_ms` in the EDL `policy` instead of a per-segment `pad_out_ms`, which §6.4's segment shape does not have; the music skill names the `tags.json` fields and the credits file from guide Phase 8. Prohibitions were rephrased as the positive target where that kept the meaning.
- Claude Code plugin packaging is not built (spec #1 moves it to `ROADMAP.md`).

Open issues:

- `PENDING` in `tests/unit/test_agents.py` lists ingest (#5), analyze and setup (#7), look and look-asset (#9), words, plan draft, plan validate and docs edl (#11), render (#13), music (#14) and check (#15). Each ticket deletes its entry when it registers the command; the test then checks the real flags.
- Gemini CLI has been succeeded by Antigravity CLI (per the Gemini CLI docs). Its use of `.agents/skills/` and `AGENTS.md` comes from third-party guides only.
- Cursor sees each skill twice when both `.claude/skills/` and `.agents/skills/` are installed (noted in `docs/agents.md`).

## Phase 4, transcript analysers and contracts (ticket #6)

Built:

- `motion_studio.analysis.models`: the §6.1 contract `ClipAnalysis` (with `ClipInfo`, `LanguageGuess`, `Word`, `Utterance`, `Pause`, `Span`, `Faces`, `FaceSample`), `TranscribedWord` (what an ASR backend returns) and `Retakes`/`RetakeCluster` for `analysis/retakes.json`. Times are seconds, rounded to milliseconds. `schemas/analysis.schema.json` is generated from `ClipAnalysis`; a test round-trips the guide's §6.1 example.
- Language data: `src/motion_studio/lang/en.toml` and `it.toml` with the §6.2 prompts and lexicons, words a finished sentence does not end on, and caption rules (`max_chars_per_page`, `keep_with_next`). `motion_studio.lang.load_language(code, dirs=None)` and `available_languages()` find languages by file name only; `[defaults] language` in the config now accepts `auto` or any code with a data file instead of a hard-coded `en | it`. A test adds a minimal Spanish file in a temp dir and runs the analysers with it.
- `analyse_transcript(clip, words, vad, language, confidence=, params=)`: filler tagging, utterances and completeness, pauses and unaligned voice, all pure. `find_retakes(clips, threshold=0.75)`: rapidfuzz `token_set_ratio` on normalised text, union-find, winner by complete, then newest, then fewest fillers. `pack_project(title, language, clips, retakes)`: the §6.3 packed index, pinned by `tests/unit/golden/packed.md` (`MOTION_STUDIO_UPDATE_GOLDEN=1` rewrites it).

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

- `motion-studio ingest <slug>` (`--json`), in `motion_studio.ingest`. It calls the disk guard, takes the project lock, probes every visible file in `raw/` (sorted), and gives each new one the next free ID for its provisional role: `c` for a video whose audio peaks above -35 dBFS, `b` for a quieter or silent video, `i` for an image. IDs live in `project.toml` as `[clips.<id>]` with `source`, `role` and `auto_role`. A `role` that differs from `auto_role` is the creator's override; ingest never changes it, and `record_auto_role()` (for the role-finalisation ticket) only moves `role` along with `auto_role` when they agree. IDs are never renumbered or reused; a source that vanished from `raw/` keeps its ID and gets a warning.
- Mezzanines (`motion_studio.media.normalise`): `media/<id>.mp4`, `fps=<project fps>` + `-fps_mode cfr`, rotation applied by ffmpeg's autorotate, long side capped at 3840 px with even dimensions, H.264 High CRF 15 `-preset fast`, GOP of one second, `yuv420p`, `+faststart`, original audio as AAC for reference. HDR (HLG, PQ) is tone-mapped per ADR 0003: `scale_vt` on macOS, `zscale` + `tonemap` (hable) where zscale exists, otherwise `colorspace` with a warning; tone-mapped output is tagged BT.709. A method that fails at run time falls through to the next with a warning. `MOTION_STUDIO_TONEMAP` forces one method.
- Voice (`motion_studio.audio.enhance`): 48 kHz mono extract, DeepFilterNet 3 (`deep-filter --compensate-delay`), or ffmpeg `arnndn` with the vendored `sh.rnnn` model and a warning, then an 80 Hz high-pass, padded or trimmed to the exact source sample count: `media/<id>.wav` (48 kHz) and `media/<id>_16k.wav` (16 kHz, for ASR and VAD). `install_deep_filter()` downloads the pinned 0.5.6 binary into `<cache>/bin/deep-filter` and checks its SHA-256; `doctor` reports it (warn when missing).
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
- `motion-studio setup` does not exist yet; whichever ticket adds it should call `motion_studio.audio.enhance.install_deep_filter()`. Until then, `deep-filter` can be put on PATH or the integration test installs it into the cache.
- The `zscale` path is not exercised on the build machine (Homebrew ffmpeg lacks zscale); CI's Ubuntu ffmpeg runs it in the HLG test.

## Phase 6, EDL models and resolver (ticket #10)

Built:

- `motion_studio.edl.models`: the §6.4 EDL (`Edl`, `Segment`, `Policy`, `DropRange`, the six event types as a discriminated union on `type`, `EdlCaptions`, `EdlMusic`) and the §6.5 timeline (`Timeline`, `Run`, `TimelineWord`, timeline events in frames, `TimelineCaptions`, `TimelineBrand`, `FormatSpec` with safe zones). `parse_edl(data)` turns schema errors into an `EdlError`. Field descriptions are written for the host agent.
- `motion_studio.edl.refs`: word, utterance and segment references with the errors §6.4 and Phase 6 ask for ("`c1.s40` does not exist; c1 has s0-s37", cross-clip ranges, reversed ranges, duplicate or reference-shaped segment IDs, segments keeping the same word).
- `motion_studio.edl.resolve.resolve(clips, edl, config, beats=None) -> Resolution(timeline, warnings, stats)`: §6.5 steps 1-10, pure. `runs.py` holds steps 1-5 and `events.py` steps 9-10. Every error found is raised at once as `EdlError` (exit 1) with a `problems` list of `Issue(code, message, hint)`; warnings come back in `Resolution.warnings`.
- `schemas/edl.schema.json`, `schemas/timeline.schema.json` and `renderer/src/types.gen.ts`, generated by `scripts/gen_schemas.py` with json-schema-to-typescript (now a renderer devDependency).
- Tests (CI): `test_edl_refs.py`, `test_resolver.py`, `test_edl_events.py`, `test_edl_models.py` (round-trips the guide's §6.4 example) and `test_resolver_properties.py` (Hypothesis, 300 examples each: runs never overlap in output or in source, duration is the sum of runs, kept words lie whole inside their run with their length intact, no run crosses a removed word, source times sit on the frame grid, reordering segments reorders the output). Mutating the midpoint clamp or the edge-word guard makes the properties fail. `just edl-coverage` (a new CI step) fails under 95% line coverage of `src/motion_studio/edl`; it measures 99.9%.

Deviations and why:

- Pause tightening keeps `max_pause_ms / 2` on each side of the cut, in place of the pads, so a tightened pause is exactly `max_pause_ms` (§6.5 step 2). Pads apply at edges next to removed words and segment ends.
- Step 4's merge joins only runs split by a pause. Runs split by a removed word or a drop range never merge, because merging would bring back the word that was cut and break the "no run crosses a removed word" property.
- Words outside a segment count as removed at its edges, so a segment's padding stops at the midpoint to the next word even when that word is in another segment.
- Snapping: run edges go to the nearest frame but never into their own edge words; midpoint limits snap to their nearest frame, so segments that meet in a gap share a boundary frame and are not a jump cut; drop-range edges are never crossed. A zero-length run is dropped with the short-run warning.
- A word whose midpoint lies inside a drop range is removed. Two segments keeping the same word is an error, so every anchor has one place in the output.
- Reframing takes one median face centre per run, not per shot inside a run.
- Defaults the guide leaves open: zoom scale 1.15, a zoom without `hold_until` holds to the end of its `at` anchor, push needs a segment ID and spans it, B-roll and image mode `full`, image motion `kenburns`. Nearest-kept-word ties go to the earlier word. B-roll shorter than its span is cut short with an `asset_short` warning. Full-frame images count as full-frame overlays for the overlap error; a title over any B-roll or image (pip included) warns.
- The timeline adds `language`, the language's `max_chars_per_page` and `keep_with_next` (loaded from `motion_studio.lang`) to the caption settings, a `src` path per overlay (the asset's mezzanine, or its source when there is none), `face` per run, and `music_path` = `build/music.wav` unless the music mode is `none`. Safe zones are constants in `resolve.py` (9x16 bottom 20%, right 12%). `beats` are output seconds, supplied by the caller.
- The timeline schema is generated in serialization mode with defaults required, so the renderer's types have no optional fields the resolver always writes.
- npm 11.6.0 dropped the platform-specific optional packages from the lockfile when adding json-schema-to-typescript (see `docs/dependencies.md`); they were merged back by hand.

Open issues:

- `plan draft`, `plan validate`, the §6.6 summary and "validating the draft for each fixture succeeds" are ticket #11. `ResolveStats` carries the summary counts (words total and kept, hard fillers removed, pauses tightened, runs per segment).
- `motion_studio.workspace.read_edl_policy` still reads `policy` loosely for `config show`; #11 can switch it to `parse_edl(...).policy.model_dump(exclude_none=True)`.

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

- No `@remotion/google-fonts`: it loads font files from Google at render time, which breaks motion-studio's offline rule. The default Inter ships in `@fontsource/inter` and is bundled; any other `captions.font` needs a file in `library/brand/fonts` (compose passes it as `font_file`), otherwise the renderer uses Inter and compose should warn.
- Paging is motion-studio's own (`pageCaptions`); `createTikTokStyleCaptions` alone pages only by time and silence, so the word, character and width caps are expressed as `pageBreakAfter`, the library's own hook.
- The renderer takes the assembled video's pixel size as a prop (`source`) instead of probing it in the browser; compose knows it from ffprobe.
- Zoom and push frames are taken as given; a zoom eases back over its easing length after `end` only while the same run continues.

Open issues:

- The logo (`brand.logo`) is not drawn; the guide names no logo layer.
- "Hide captions during full B-roll if configured" has no config key in the timeline; captions always show (the guide's default).
- Caption width is measured with spaces between words but drawn with a 0.4em gap; the 12% headroom covers the difference.
- Glyphs outside Inter's latin and latin-ext subsets (for example "→") fall back to a system font.

## Phase 4, speech: VAD, speech-to-text and language (ticket #7)

Built:

- `motion-studio analyze <slug> [--clip c1] [--json]` (`motion_studio.analyze.analyze_project`). It calls `config.ensure_supported()` first (so `fillers_backend = "crisper"` exits 2), takes the project lock, reads `media/manifest.json` and the roles in `project.toml`, sends every clip with audio whose state record (`analyze.<id>`) is stale to one speech-to-text worker, runs the #6 analysers, and writes `analysis/<clip>.json`, `analysis/retakes.json` and `analysis/packed.md`. A re-run with nothing changed is a no-op that starts no worker; `--clip` re-transcribes one clip and repacks the project. Images and silent clips get an analysis file with no words and `language: null`.
- `motion_studio.asr`: `transcribe_clips(jobs, backend=, model=)` runs `python -m motion_studio.asr.worker` as a child process while the parent holds the machine-wide heavy-model lock, so the model never loads in the motion-studio process and its memory goes back to the system when the child exits. The worker runs Silero VAD, language ID and transcription for every job with one model load and reports its pid and peak RSS. `MOTION_STUDIO_ASR_WORKER` replaces the worker command (the CI tests use a scripted stand-in).
- `ASRBackend` protocol (guide §8 Phase 4) in `motion_studio.asr.backends`, with `MlxWhisper` (default on arm64 macOS) and `FasterWhisper` (default elsewhere; CPU, int8). Both use the language file's filler prompt as `initial_prompt`, `word_timestamps`, `condition_on_previous_text=False` and `hallucination_silence_threshold=2.0`, and decode only speech windows through `clip_timestamps`.
- Silero VAD through onnxruntime (`motion_studio.asr.vad`): min speech 250 ms, min silence 100 ms, 30 ms pad, threshold 0.5, ported from the reference `get_speech_timestamps`.
- Language: each clip is detected among the languages with a data file, from up to 30 s of its VAD speech; the project language is the language with the most A-roll utterance time (`motion_studio.analysis.project_language`), or `defaults.language` when set, which also forces that language on every clip.
- `motion-studio setup [--json]` downloads DeepFilterNet (`install_deep_filter()`), Silero VAD and the Whisper model for this platform's backend (or the workspace's `asr.backend`/`asr.model`) into the cache; already-present items are reported, not fetched. `doctor` now has `vad model` and `asr model` checks (warn until setup has run) instead of the generic `models` check.

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
- The `ASRBackend` methods follow the guide's signatures, plus a `candidates` argument to `detect_language` so detection only picks languages motion-studio has data for. Confidence is the model's own probability for the chosen language.
- `setup --music` exits 2 with "not available in this build yet" until the music ticket (#14) implements it; `setup --crisper` exits 2 like the config value. The renderer (#13) and face models (#8) are not installed by setup yet; those tickets add their steps to `motion_studio.setup.run_setup`.
- Models live under `<cache>/models/huggingface` (Hugging Face cache layout), not the default `~/.cache/huggingface`, so `motion-studio clean` and the cache directory cover them.

Open issues:

- On the 5-minute concatenation Whisper sometimes attaches the first word of the next take to the end of the abandoned one ("... remember is The"); the retake still clusters, but the draft would keep a stray word. Check (#15) re-transcribes and will flag it.
- `project.toml` is an input of the analyze stage, so role finalisation (#8) writing it marks analyze stale once; the next run is then a repack, not a re-transcription (per-clip records stay fresh).

## Phase 4, visual: shots, static stretches, faces, roles and the asset catalogue (ticket #8)

Built:

- `motion-studio analyze` now also fills `shots`, `static` and `faces` in each `analysis/<clip>.json`, finalises roles, and writes `analysis/assets.md`. The per-clip state record covers the mezzanine as well as the 16 kHz WAV, and the analyze recipe is 2, so existing projects re-analyse once.
- Shots: PySceneDetect `ContentDetector` (default threshold 27) through a `SceneManager` with `auto_downscale`, on the mezzanine (`motion_studio.vision.motion.find_shots`). A clip without cuts is one shot.
- Static: ffmpeg decodes grey frames at 2 fps, 320 px wide (`motion_studio.media.ffmpeg.read_frames`, a new streaming raw-frame reader), and OpenCV `absdiff` gives the mean difference between neighbours. `motion_studio.analysis.find_static` (pure) keeps runs below 1.5 (of 255), removes VAD speech from them, and keeps pieces of 2 s or more; the last sampled frame stands for the rest of the clip.
- Faces: MediaPipe Tasks `FaceDetector` with the BlazeFace full-range model at 2 fps on frames scaled to 640 px on the long side, largest face per frame, boxes normalised to the frame. It runs in `python -m motion_studio.vision.worker` while the parent holds `heavy_model_lock("faces")`, one process for all clips. YuNet (`cv2.FaceDetectorYN`) takes over when the MediaPipe model is missing or MediaPipe fails to load; analyze then prints `warning: face detection fell back to YuNet: <reason>` and records it in `stages.analyze.warnings` of `state.json`. `MOTION_STUDIO_FACE_WORKER` replaces the worker; the unit tests use an autouse stand-in that reports a face in every sampled frame.
- Roles: `motion_studio.analysis.finalise_role` (pure): images stay images; a video is A-roll when VAD speech covers more than 30% of it and a face is in more than 50% of the sampled frames, otherwise B-roll. analyze stores it with `ingest.record_auto_role`, only when it changed, so a creator's `role` override in `project.toml` wins and the file is not rewritten on every run.
- `assets.md` (`motion_studio.analysis.pack_assets`): one section per B-roll clip and image with ID, file name, source path, duration (or "still image"), resolution, shot count, the contact sheet path `contact/<id>.png` and a blank `description:` line. Descriptions the agent writes are read back before every repack and kept. The sheets themselves come with the look ticket (#9); the path is fixed now (`ProjectPaths.asset_sheet`).
- `motion-studio setup` downloads both face models (SHA-256 checked); `doctor` has a `face model` check that warns when only YuNet, or nothing, is in the cache.
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

- `motion-studio plan draft <slug> [--force] [--json]` (`motion_studio.plan.draft_project`, pure logic in `motion_studio.edl.draft`). One segment per kept A-roll utterance, clips in ID order, segment IDs `c1-s0` (the utterance ID with a hyphen, so it can never parse as a reference) and the utterance text as `note`. Retake cluster members other than the winner are left out, which also drops an abandoned take whose complete retake won; an incomplete utterance with no retake stays. Utterances made only of hard fillers are left out. Policy `drop_fillers: "hard"`, `jumpcut_punch: true`, no events, `rationale: "deterministic draft"`, `language` from `project_language`, `title` from `[project] title`. Music `generate`, seed 1, BPM in the middle of the guide's band for the pace of the kept utterances (non-filler words per second of utterance time: under 2.3 → 90, 2.3 to 3 → 103, over 3 → 118) and a neutral prompt of matching energy that always says "instrumental". An existing `edl.json` is refused with exit 1 and a hint naming `--force`.
- `motion-studio plan validate <slug> [--json]` (`motion_studio.plan.validate_project`): reads `edl.json`, every `analysis/<clip>.json` and, when the music stage has written it, the `beats` of `build/music.json`; resolves with the #10 resolver; writes `build/timeline.json`; marks the `plan` stage done (inputs `edl.json`, `analysis/`, `project.toml`). The summary (`motion_studio.edl.summary`) has the guide §6.6 shape plus words per second on the duration line (the music skill tells the agent to pick the BPM from it). Warnings and errors print one line each with their fix, capped at 20 lines with a pointer to `--json`, so output stays under 30 lines. An EDL that does not resolve prints every error and exits 1; `--json` gives `{ok: false, valid: false, errors: [{code, message, hint}], ...}`.
- `motion-studio words <slug> <from> [<to>] [--json]`: the words of a range of word or utterance IDs in one clip, grouped under their utterance (`✗` for incomplete), five per line as `c1.w5 {ehm,} 4.87-5.17` (hard fillers in braces, soft in tildes, source seconds). Capped at 30 lines; `--json` has every word.
- `motion-studio docs edl [--json]`: prints `src/motion_studio/reference/edl.md` through `importlib.resources`, so it works from any directory and from the installed wheel (checked: the wheel contains `motion-studio/reference/edl.md`). `docs/edl.md` is a symlink to it. A test checks that every EDL field and every issue code the resolver raises is named in the reference.
- Removed `words`, `plan draft`, `plan validate` and `docs edl` from `PENDING` in `tests/unit/test_agents.py`. `motion_studio.analyze._title` is now the public `project_title`.

Checked (acceptance):

- `tests/integration/test_plan_fixtures.py` (`slow`, `mac`, `models`): on the EN and IT fixtures, ingest, analyze, `plan draft` and `plan validate` succeed; the draft has 4 of the 5 utterances (the abandoned take is skipped, its retake kept) and removes the hard filler. 6 tests pass in 22 s.
- By hand on the IT fixture: `✓ edl.json valid · language it · 4 segments → 5 runs` / `Duration 10.7s (limit 60s) · words kept 31/39 · 2.9 words/s · hard fillers removed 1 · pauses tightened 0` / `Hook (first 3s): "Ciao, bentornati sul canale. Oggi, vi faccio…"` / `Events: none` / `→ …/build/timeline.json`. EN: 4 segments → 5 runs, 11.2 s, 37/45 words. A second `plan draft` exits 1.
- `motion-studio words demo c1.s0 c1.s1` prints the 14 words of the IT fixture's first two utterances with IDs and times; `motion-studio docs edl` from `/` prints the reference.
- `just edl-coverage`: 99.9% of `src/motion_studio/edl` (draft and summary 100%).

Deviations and why:

- One segment per utterance rather than one per contiguous block: moving the hook to the front is then moving one entry, and the resolver splits at the inter-utterance pauses anyway.
- The music prompt depends on pace only, not language: the bed is instrumental, so there is nothing language-specific to say.
- The draft and summary are pure modules in `motion_studio.edl` (counted by `just edl-coverage`); file I/O is in `motion_studio.plan`, outside it.

Open issues:

- `motion_studio.workspace.read_edl_policy` (for `config show`) still reads `policy` loosely rather than through `parse_edl`.

## Phase 7: render, assemble, compose and mix (ticket #13)

Built:

- `motion-studio render <slug> [--preview|--final] [--format F ...] [--concurrency N] [--json]` (`motion_studio.render.render_project`). It calls the disk guard first (exit 2 below the threshold), validates `edl.json` when the `plan` stage is not fresh, takes the project lock, and renders each requested format (default: every format in the timeline). Preview is the default; `--preview --final` is exit 1. A re-run with nothing changed is a no-op (stage `preview` or `final` in `state.json`; inputs `build/timeline.json`, `media/manifest.json`, the music bed, brand font and logo; params recipe, formats, `[music]`, `[master]`, Remotion version).
- Assemble (`render/assemble.py`): one filter graph, written to `build/assemble.filtergraph` and passed with the probed `-/filter_complex` or `-filter_complex_script`. Per run: `trim=start_frame:end_frame` on the CFR mezzanine and `atrim=start_sample:end_sample` on the enhanced 48 kHz WAV (both exact, from the timeline's frame-grid seconds), 30 ms `afade` in and out, then one `concat`. Output `build/assembled.mp4`, H.264 CRF 14, AAC 320k 48 kHz; its frame count is asserted equal to `duration_frames` within one frame. Cached as the `render.assemble` record, so a second format or a final after a preview reuses it.
- Compose (`render/compose.py`): `build/public/` holds hard links (copy across volumes) of `assembled.mp4`, every overlay `src`, the brand font (`brand/font.<ext>`) and logo (`brand/logo.<ext>`); `build/props_<fmt>.json` adds `logo_file` to #12's props. The Remotion CLI runs from the renderer dir as `node_modules/.bin/remotion render src/index.ts Reel build/composed_<fmt>.mp4 --props --public-dir --concurrency (default 4) --codec=h264 --crf 16 (final) or 23 plus --scale=0.5 (preview) --log=error`.
- Brand (user story 65): `captions.font` is "Inter" (bundled), a font path relative to the workspace, or a family name matched against `library/brand/fonts/*.{ttf,otf,woff,woff2}` (exact stem, else a stem starting with it, such as `Montserrat-ExtraBold.ttf`). The font is used by captions and titles; the props rename the family to a plain identifier so any configured value is valid CSS. When the font is not found, compose prints one `warning:` line and records it in `state.json` under the stage. The logo (`brand.logo`) is now drawn by a new `Logo` layer: top-right corner of the format's safe area, 7% of the short side tall, hidden while a title card is on screen (they share the top of the safe area). Placement is in `lib/safezones.ts` with vitest tests.
- Mix (`render/mix.py`): music input looped with `-stream_loop -1`, `atrim` to the video, 1.5 s fade-out, `volume=<gain_db>dB`, `sidechaincompress` keyed by an `asplit` of the voice (threshold/ratio from `[music]`, attack 10 ms, release 400 ms), `amix=inputs=2:duration=first:normalize=0`; music `none` sends the voice alone. Two-pass `loudnorm` at `[master]` (pass 1 `print_format=json`, pass 2 the measured values with `linear=true`; silence falls back to one pass), `aresample=48000`, `-c:v copy`, AAC 320k, `+faststart`. The voice stem `build/voice_<fmt>.wav` (mono 48 kHz s16, from the composed file, before music) is kept for `check`.
- Renderer lookup (`render/renderer.py`): `MOTION_STUDIO_RENDERER_DIR`, then the repo's `renderer/` when it has `node_modules` (dev mode), then `<cache>/renderer/<version>/` with an install marker; none is exit 2 pointing at `setup`.
- `motion-studio setup` now installs the renderer: copies the sources (packaged into the wheel as `motion_studio/_renderer` via hatch `force-include`, or the repo's `renderer/` in a checkout) into `<cache>/renderer/<version>.partial`, runs `npm ci`, then `remotion browser ensure`, writes the marker and renames into place. `doctor`'s renderer check is `ok` only for a complete install and names the Remotion version.
- Removed `render` from `PENDING` in `tests/unit/test_agents.py`.

Pinned: nothing new. ffmpeg filter options and `remotion browser ensure` verified in `docs/dependencies.md`.

Checked (acceptance):

- `motion-studio setup --json` on the build machine installed the renderer into `~/Library/Caches/motion-studio/renderer/0.1.0.dev0` in 14 min 24 s (almost all of it the Chrome Headless Shell download); the second run reports it `present`. `motion-studio doctor`: `ok renderer: /Users/fpaolileonardi/Library/Caches/motion-studio/renderer/0.1.0.dev0 (Remotion 4.0.538)`.
- `tests/integration/test_render_fixtures.py` (`slow`, `mac`, `models`, `renderer`; run with `MOTION_STUDIO_RENDERER_DIR` set to the cache install): EN and IT fixtures ingested, analysed, drafted, given a title, a snap zoom (1.25) and a B-roll PiP card, validated, rendered. Previews: 540x960 and 960x540, frame count equal to the timeline (EN 335 frames, IT 322). After merging #8 (fixtures with a real face photo, regenerated with `just fixtures`), the render tests, `test_renderer_cli.py` and `test_setup.py` (8 tests) pass in 10 min 36 s, most of it the repo renderer's first Chrome download.
- Loudness with `ebur128=peak=true` on the 9x16 finals: EN (music `none`) −13.9 LUFS, −2.5 dBTP; IT (a 220 Hz tone bed at `build/music.wav` standing in for #14, looped from 5 s) −13.9 LUFS, −1.5 dBTP. Both within −14 ± 1 LUFS and ≤ −1 dBTP.
- Video copy: the `streamhash` MD5 of the EN final's video stream equals that of `build/composed_9x16.mp4` (`523b2bc8...`); the CI test `test_mix_copies_the_composed_video_stream_bit_for_bit` asserts the same on every run.
- Stills, opened as images: frames extracted from `preview/9x16.mp4` and `preview/16x9.mp4` (start = frame 15, cut = 3 frames after the first cut, zoom = middle of the zoom), plus full-size `remotion still` frames of the same points. What I saw:
  - Start: the brand title card "Fixture test" (white Inter 800 on the brand primary #111111) centred in the top of the safe area, the logo hidden under it; captions "Hi, welcome back" / "Oggi, vi faccio" in white with a black stroke, the active word yellow, in the lower part of the safe area, clear of the bottom 20%.
  - Cut (EN frame 64, IT 63): the jump-cut punch is visible, the presenter is larger than at the start (base scale 1.08 vs 1.0); the yellow logo disc sits in the top-right corner inside the safe area; captions moved to the next page.
  - Zoom (EN 98, IT 121): the disc is clearly larger again (scale 1.25) and the active word is yellow ("show", "monto").
  - 16x9: the vertical source is fit-blurred: sharp 9x16 column in the centre, a darkened blurred copy filling the sides; captions and title span the centre; logo top-right of the 16x9 safe area.
  - Reframing: on the regenerated fixtures every run has `face: true` (EN first run crop centre 0.474, 0.430). In the 9x16 preview the face sits near the horizontal centre and a little above the middle (about x 0.54, y 0.43 of the frame at the start, y 0.35 mid-zoom), with no empty edges. On the first pass (fixtures from before #8, a flat disc with no detected face) runs used the centre crop as designed.
- CI-level tests (`tests/unit/test_render_cli.py`, real ffmpeg, a stand-in Remotion binary that scales the assembled video): dimensions and frame counts per format, `--scale=0.5` and `--concurrency` passed, −14 ± 1 LUFS and ≤ −1 dBTP for music `none` and for a looped tone bed, the bed ducked (more than 24 dB under the voice tone where gain alone would give 20 dB) and absent from the voice stem, video stream copied, re-run no-op, EDL edit re-validates, disk guard exit 2, missing music bed exit 1 with a `music` hint, unknown format exit 1, missing renderer exit 2, font fallback warning in stderr and `state.json`, brand font and logo linked into the public dir. `tests/unit/test_renderer_install.py`: install with a stand-in npm, doctor before and after, failed `npm ci` leaves nothing installed.

Deviations and why:

- Dev mode wins over the cache: every worktree shares one cache and one dev version string, so a cached renderer may be another checkout's code. `MOTION_STUDIO_RENDERER_DIR` overrides both.
- The CLI is called as `node_modules/.bin/remotion` rather than `npx remotion`: same binary, no npx resolution step, and tests can stand it in.
- `--concurrency` is a CLI option (default 4), not a config key, so the config schema and template stay as they are.
- Previews use `--crf=23` as well as `--scale=0.5` ("fast encode" in guide §7).
- The logo layer is new renderer code (spec story 65; guide §7b puts the logo in the public dir but names no layer). A missing logo at the default path renders without a logo and no warning, since most workspaces have none; a missing logo at a configured path warns.
- Runs from clips of different sizes are scaled and padded to the first run's clip size before `concat`; with mismatched aspect ratios the crop centres of the padded runs are off (open issue).
- Guide §5.1 masters to −1.5 dBTP (user story 67); the acceptance bar is ≤ −1 dBTP. Measured values meet both.

Open issues:

- Mixed-aspect A-roll (see above) is not handled beyond letterboxing.
- The renderer is installed from the checkout that ran `setup`; a later `setup` from another checkout reports it `present` without refreshing it. Delete `<cache>/renderer/<version>` to reinstall.
- Captions still show during full B-roll (guide default; not configurable yet).

## Phase 5: look, look-asset and asset contact sheets (ticket #9)

Built:

- `motion-studio look <slug> <clip> <t0> <t1> [--frames 8] [--out PATH] [--json]` (`motion_studio.look.look_range`). Times are source seconds. Frames are taken at the centres of `--frames` equal slices of the range (1 to 24), each decoded with an input seek (`-ss` before `-i`) at 320 px tall. The sheet is 1600 px wide: a header (clip, file, range, first and last word ID), the frames in a centred grid with a timestamp under each and the nearest face sample (within 0.25 s) drawn as a cyan box, then a waveform of the range from the 16 kHz WAV with VAD regions shaded green, pauses hatched, frame times as blue lines, a time axis, and the words placed by start time in as many rows as needed so labels never overlap (hard fillers red, soft fillers orange, a bar under the waveform for each word's span), and a legend. Default output `contact/<clip>_<t0>-<t1>.png`. Prints a one-line description (words, fillers, frames with a face), the budget count and the path.
- Look budget: every `look` adds one to `look_count` in `state.json`. Past `edit.look_budget` it prints `warning: look budget exceeded (N of B sheets); ...` (stderr, and in `warnings` under `--json`) and still writes the sheet, exit 0. A range past the clip end is clamped with a warning; ranges over 20 s get a warning, as the look skill says.
- `motion-studio look-asset <slug> <asset-id> [--json]` (`motion_studio.look.look_asset`) redraws `contact/<id>.png` for a B-roll clip (6 frames across the clip) or image (the image up to 720 px tall, no timestamp). It does not count against the budget: describing each asset once is part of every edit, and analyze has already drawn the same sheet.
- `analyze` writes `contact/<id>.png` (`ProjectPaths.asset_sheet`, the path #8's `assets.md` already links) for every clip whose final role is broll or image, when the clip was analysed in that run or its sheet is missing. The sheets are outputs of the `analyze` stage, so deleting one makes the next analyze redraw it.
- Drawing is in `motion_studio.look.sheet` (pure Pillow over decoded frames); media reading and the budget are in `motion_studio.look`.
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
- Vendored font (`src/motion_studio/look/fonts/`, 81 KB, licence alongside and in THIRD_PARTY.md), for the reason above.

Open issues:

- The look counter is read and written without the project lock, so two `look` calls at the same instant could count once; it is only a warning threshold.
- In a long dense range, word labels can stack several rows deep; the look skill already steers agents to ranges under 20 s.

## Phase 9: check (ticket #15)

Built:

- `motion-studio check <slug> [--preview|--final] [--json]` (`motion_studio.check.check_project`). It refuses (exit 1, hint `render`) unless the matching render stage is `done`, and checks every format that render wrote (read from the stage's recorded outputs). Writes `check/report.md`, `check/report.json` (the `--json` payload) and `check/cuts.png`; exits 1 when anything blocks, with `ok: false` and `verdict: "blocked"` in the JSON.
- Re-transcribe and diff (`motion_studio.check.diff`): `build/voice_<first format>.wav` (the voice stem before music, the same for every format) is resampled to `check/voice_16k.wav` and transcribed with `motion_studio.asr.transcribe_clips` (same backend and model as analyze, in its subprocess under the heavy-model lock) in the timeline language. `difflib.SequenceMatcher` aligns case-folded, punctuation-free tokens; a missing or replaced word whose span is within 300 ms of a cut is a blocking `clipped_cut`, otherwise an `asr_noise` note. The fix names the policy pad on the side of the cut the word is on, with its current value, and the source neighbour to keep: remove it from `drop_words`, add a filler to `keep_words`, set the segment's `to`/`from` to it, or raise `max_pause_ms` when the cut is inside a segment.
- Cut stills (`motion_studio.check.stills`, drawn with ticket #9's sheet helpers and font): one cell per cut with `cut k  t s`, the frame 0.2 s before and after (red line between) from the first rendered format, and the two words either side of the cut.
- One ffmpeg pass per rendered file: `ebur128` (integrated, true peak, LRA; warning beyond ±1 LU or 0.5 dB over the true-peak limit, as mastering is automatic), `blackdetect` (≥ 0.5 s, blocking) and `freezedetect` (≥ 2 s, warning); stretches mostly inside an image event are ignored.
- Duration over `max_duration_s` (EDL, else config) blocks, naming the longest middle segments. Caption density: peak words starting in any 2 s window of output time, warning over 4.5 words/s. Event overlaps re-checked from the timeline: full-frame overlays overlapping block, a title over full-frame B-roll and an event past the end warn.
- State: a passing preview check marks stage `check` done; a final check uses record `check.final`. A blocked check marks the record failed with the verdict.
- Removed `check` from `PENDING` in `tests/unit/test_agents.py`; it accepts `--json`.

Checked (acceptance):

- Zero padding produces a blocking clipped cut: `tests/integration/test_check_fixtures.py` (slow, mac, models, renderer; mlx-whisper) sets `policy` pads to 0 on the EN fixture, renders a 9x16 preview and checks: exit 1 with `clipped 'videos.' (c1.w17) at cut 2 (4.07 s): heard as 'video.' → raise policy.pad_out_ms (now 0) or set segment c1-s1's `to` to c1.w18 ('The')`. The default pads (80/120 ms) on the same footage re-hear all 31 words.
- An EDL longer than `max_duration_s` blocks: the same integration file (`max_duration_s: 5`) and `test_an_edl_longer_than_max_duration_blocks` in CI.
- A good fixture render passes with exit 0: EN and IT drafts with default policy, 9x16 previews; 31 of 31 words re-heard (EN), -13.9 LUFS / -1.5 dBTP; the only finding is a caption-density warning (about 5 words/s for 2 s: macOS `say` speaks fast once pauses are tightened).
- `check/cuts.png` shows every cut with its index. Visual check, opening the PNGs from the fixture runs: EN and IT each show 4 cells in one row, labelled `cut 1  2.03s` to `cut 4  8.57s` (IT `cut 1  2.00s` to `cut 4  8.27s`), each a before/after pair split by a red line with the burned-in captions legible ("to the channel." | "Today, I want"), the alternating jump-cut punch visible as a size change of the face between the two frames, and the words either side underneath with accents intact ("la cosa più"). CI test asserts one cell per cut in the sheet's size and the `cuts_s` list.
- CI tests (`tests/unit/test_check_cli.py`, stand-in Remotion and ASR worker on ticket #13's `demo` project): pass with exit 0; a word lost before a cut blocks with a `pad_out_ms` fix and `c1.w7`; a word lost after a cut points at `pad_in_ms` and the earlier word; a misheard word far from a cut is a note; over-length blocks; the ASR job is 16 kHz mono in the timeline language; loudness per rendered format; a black picture blocks and a flat grey (frozen) picture warns; check before render is exit 1; a passing check marks the stage done.

Deviations and why:

- Words are re-transcribed once per render, from the first format's voice stem: every format's stem is the same audio (ticket #13), so transcribing each would only cost model time.
- Loudness and true peak off target are warnings, not blocking: the review skill says to re-render and report them as a bug, since the EDL cannot fix them. Frozen pictures warn rather than block, since a locked-off talking head can legitimately fall under the freeze threshold; black frames block.
- Caption density is measured over a 2 s sliding window of word starts, not per caption page: page-based counts swung with a single short word and do not match how the renderer pages captions.
- `BUILD_LOG.md` on `feat/motion-studio-v0.1.0` had committed merge-conflict markers between the #13 and #9 sections; removed them, keeping both sections.

Open issues:

- `render` fingerprints `media/manifest.json`, not the mezzanine files, so replacing a mezzanine in place does not make the render stale (the black/frozen CI test touches the manifest to force it).
- The clip window (300 ms) can flag ASR noise on a word next to a cut as a clipped cut; the fix is still harmless (more padding).

## Phase 8: music (ticket #14)

Built:

- `motion-studio setup --music [--json]` (`motion_studio.music.acestep.install`): after the usual setup steps, refuses below the free-disk threshold (exit 2) when nothing is installed yet, downloads the ACE-Step 1.5 source tarball at a pinned commit into `<cache>/envs/ace-step/src`, runs `uv sync --frozen` there (ACE-Step's own `.venv`; motion-studio's environment is untouched), downloads the pinned weights into `src/checkpoints` with the env's `huggingface_hub`, reads the licence the weights declare and writes `<cache>/envs/ace-step/install.json` last. It prints `weights licence: mit`; `--json` items carry `licence`. Idempotent: a second run reports `present`. Missing `uv` is exit 2.
- `motion-studio music <slug> [--json]` (`motion_studio.music.stage.run_music`), under the project lock, resolves the EDL in memory for the duration, then by effective mode (`edl.music.mode`, else `[music] mode`):
  - `generate`: duration = timeline + 3 s; the worker (`src/motion_studio/music/acestep_worker.py`, run with the env's Python and `-I`) loads the turbo DiT without the LM, sends the prompt, BPM, duration, seed and `[Instrumental]` lyrics, and writes a 48 kHz stereo WAV. The client holds `heavy_model_lock("music")`, enforces a timeout (600 s + 10 s per second of music; `MOTION_STUDIO_MUSIC_TIMEOUT_S` overrides; exit 3 on expiry) and sets HF offline flags so generation never touches the network. Vocal check: Silero VAD on a 16 kHz copy; more than 20% of the length heard as speech rejects the bed and retries with seed + 1, up to three seeds, then exit 1 with a hint. Exit 2 with `setup --music` in the hint when the env is missing.
  - `library`: reads `library/music/tags.json`; a named `track` without a licence is refused (exit 1); otherwise the licensed entry with the most mood tags shared with the prompt's words wins, ties to the nearest BPM, then the file name. Unlicensed entries are skipped with a warning. The track is converted to `build/music.wav` (48 kHz stereo PCM) and its attribution, if any, goes to `final/<slug>_credits.txt`.
  - `none`: deletes `build/music.wav` and writes a `music.json` with `mode: "none"` and no beats.
  - Beats: `librosa.beat.beat_track(units="time", trim=False)` on the bed, kept below the timeline's end, in `music.json.beats` (output seconds), which `plan validate` already reads for snapping.
  - Stage `music` in `state.json` is keyed on the music parameters (mode, prompt, BPM, seed, duration, model; or the library entry and files), not on `edl.json`, so an EDL edit that keeps the duration and music block does not regenerate a five-minute bed. `music` was removed from `PENDING` in `tests/unit/test_agents.py`.
- `doctor`'s `ace-step env` check is `ok` only once `install.json` exists, and shows the weights and their licence.

Checked (acceptance):

- `tests/integration/test_music_generate.py` (`slow`, `mac`, `music`): a 57 s timeline gives a 59.9 s bed in 290 s; first run 346 s. Probed by hand with a 60 s lo-fi prompt: model load 227 s, generation 137 s (DiT 72 s at 9 s/step, VAE decode 18 s), on MPS with the MLX DiT and VAE, worker peak RSS 1.8 GB. The machine was 17 GB into swap from parallel worktrees at the time; load time is mostly reading 4.7 GB of DiT weights under that pressure. The bed: 60.0 s, RMS 0.11, speech ratio 0.0, librosa tempo 89.1 for a requested 90 BPM, 85 beats.
- Vocal check with the real Silero model (`tests/unit/test_music_vocals.py`, `mac`, `models`): a `say` speech WAV is rejected (ratio above 0.5), a synth chord pad is accepted. In CI the CLI tests use a stand-in detector and worker for the retry, give-up, freshness, disk-guard, missing-env, `none` and library paths (`tests/unit/test_music_cli.py`, 10 tests).
- Library mode picks the same track twice from the same tags and refuses a named unlicensed entry (unit tests).
- `music.json` holds `prompt`, `seed`, `model` (`ACE-Step/Ace-Step1.5@19671f4 (acestep-v15-turbo)`), `licence`, `licence_source`, `bpm`, `detected_bpm`, `beats`, `attempts` and `elapsed_s`.
- ACE-Step weights licence: MIT, from the model card's front matter at the pinned revision (no LICENSE file in the weights repository); recorded in THIRD_PARTY.md and README. The open question in #1 is settled: generation stays the default and the card says its output may be used commercially.
- `tests/integration/test_setup.py::test_setup_music_installs_acestep_and_prints_the_weights_licence` passes. The first `setup --music` took 1164 s, nearly all of it the 9.4 GB weights download; `uv sync` took 39 s with a warm uv cache.

Deviations and why:

- DiT only, no 5 Hz LM (`thinking=False`): the LM plans lyrics and metadata, which a bed under speech does not need, and skipping it saves memory on 18 GB. The LM weights are still downloaded because ACE-Step's model check requires every main component, or it tries to download them at load time.
- The source comes from the commit tarball instead of `git clone`: the same files at a pinned commit without needing git.
- `music.json` is not one of the generated JSON Schema contracts; it is a Pydantic model (`motion_studio.music.stage.MusicInfo`) read only by motion-studio.

Open issues:

- Model load dominates generation time on a loaded machine; ACE-Step's API server could keep the model warm, but that conflicts with one heavy model in memory at a time.
- Same seed on MPS is not checked for bit-identical output.

## Phase 11, end-to-end part (ticket #17)

Built:

- `just e2e` (`uv run pytest tests/e2e -v -s`) runs `tests/e2e/test_pipeline.py` (markers slow, mac, models, renderer, music; so `just test` and CI skip it) once per language. Each step runs the venv's `motion-studio` executable in a subprocess with `--json`, as an editing agent would: `init`, `new demo --from <talking clip> broll.mp4 image.png`, `ingest`, `analyze`, `look-asset demo b1`, `plan draft`, then the agent's edit to `edl.json` (formats 9x16 and 16x9; a title over the hook, a full-frame image card, a 1.25 zoom over the retake winner and a B-roll PiP in the outro, anchored to word IDs from the draft's segments), `plan validate`, `music` (ACE-Step generate, the draft's prompt), `plan validate` again for beat snapping, `render demo --preview` and `check demo --preview`. edl.json is the only file the test writes into the workspace.
- Assertions against `tests/fixtures/ground_truth/<lang>_talking.json`: language detected and roles c1 aroll, b1 broll, i1 image; at least 90% of the known silences found within ±150 ms; the hard filler tagged within ±150 ms; the retake pair clustered with the complete take winning (both starts within ±150 ms); the timeline's words match the script without the filler or the abandoned take (filler absent, SequenceMatcher ratio ≥ 0.95, to allow one misheard word); music generated without vocals, with beats, and `music_path` set; both previews at 540x960 and 960x540 with the timeline's duration ±1 frame; check verdict `pass` over both formats, integrated loudness -14 ± 1 LUFS, true peak ≤ -1 dBTP and at least 90% of the words re-heard.
- Per-stage wall times, `check/report.md`, `check/cuts.png` and stills (start, first cut, title, image, zoom, B-roll, both formats) go to `build/e2e/<lang>/` (`MOTION_STUDIO_E2E_OUT` overrides); the times are also printed.

Checked (acceptance):

- `just e2e` passes on this Mac (Apple M3 Pro, 18 GB, nothing else running): 16 passed in 594 s.
- Stage timings, fixture runs (one ~23 s talking clip + 6 s B-roll + one image, an ~11 s Reel, music generate, previews in 9x16 and 16x9), seconds:

  | stage | EN | IT |
  |---|---|---|
  | init | 0.3 | 0.3 |
  | new | 0.3 | 0.3 |
  | ingest | 5.5 | 5.3 |
  | analyze (mlx-whisper, faces) | 10.5 | 8.9 |
  | look-asset | 0.8 | 0.8 |
  | plan draft | 0.3 | 0.3 |
  | plan validate | 0.3 | 0.3 |
  | music (ACE-Step, ~14 s bed) | 248.0 | 218.8 |
  | plan validate (beats) | 0.7 | 0.7 |
  | render preview (2 formats) | 40.4 | 36.9 |
  | check | 5.4 | 5.5 |
  | total | 312.5 | 278.0 |

  Music is nearly all model load: the bed is short, so the time is ACE-Step loading its weights, once per run.
- Check results: EN pass with one caption-density warning (5.0 words/s from 2.63 s), 37 of 37 words re-heard, -13.9 LUFS / -2.5 dBTP in both formats; IT pass with no findings.
- The run uses only CLI commands an editing agent would use (the list above), plus writing edl.json.
- Visual check, opening the stills from the final runs: EN 9x16 start shows the "End to end" title pill above the presenter photo and the caption "Hi, welcome back" with the active word in yellow; 0.1 s after the first cut shows "Today, I want" with no "um" and the jump-cut punch visible as a slightly larger photo than at the start; the zoom frame shows the photo larger again, cropped at the right edge, under "thing to remember"; the image card fills the frame with the Mandelbrot still under "my videos."; the B-roll PiP is a rounded test-pattern card in the upper area over the presenter, caption "watching, and see". IT 16x9 start shows the portrait source centred on a blurred fill with the title and "Ciao, bentornati sul"; the IT zoom frame reads "da ricordare è" with the accent intact; the IT first cut reads "Oggi, vi faccio" with the "ehm" gone.

Deviations and why:

- B-roll and the image go into the same project as the talking clip, and the test adds events, so the e2e also covers look-asset, overlays, beat snapping and fit-blur; the guide's list has only the talking clip.
- Previews only, as the guide's e2e step says; finals are covered by `tests/integration/test_render_fixtures.py`.

Open issues:

- No earlier ticket's code needed a fix: the first full run passed.
- The fixtures are ~23 s, so these timings say little about a 5-minute shoot; music time is dominated by the model load, which does not scale with length, while analyze and render do.

## Phase 12, documentation and open-source readiness (ticket #18)

Built:

- README per guide Phase 12: pitch, pipeline diagram, requirements, quickstart from a clone (`uv tool install --python 3.12 '.[mac]'`, `setup`, optional `setup --music`, `doctor`, `init`, `new`, then ask the agent), supported agents, configuration, licences (Remotion terms, ACE-Step weights, CrisperWhisper), security and privacy (no uploads, no telemetry, skills run shell commands), troubleshooting, and the roadmap link.
- `docs/cli.md`: the option lists generated with `uv run typer motion_studio.cli utils docs --name motion-studio`, then grouped by stage, with the conventions (exit codes, `--json`), examples, what each command writes, and the environment variables. `docs/architecture.md`: principles, pipeline, module map, the resolver, contracts, processes and memory, rendering, stage state, test seams. `docs/adding-a-language.md`: an `es.toml` walk-through (the file in it loads with `load_language`). `docs/renaming.md`: a checklist built from `git grep -n motion-studio` and `git ls-files`, grouped by what kind of change each file needs. `docs/edl.md` was already complete (its test checks every field and issue code); no change.
- `THIRD_PARTY.md` rewritten with a link for every entry: Remotion and the npm tree (285 packages, licence counts), the 16 direct Python dependencies and all 74 others in the runtime closure with their metadata licence, development tools, every model and its pinned revision, the ACE-Step environment (125 packages, four looked at by hand), and system tools.
- `tests/unit/test_docs.py` (CI): every CLI command and `--option` has its section in `docs/cli.md`; every tracked file that names the product (by content, case-insensitive, or by path) is covered by an entry in `docs/renaming.md`, and no entry is stale.
- Version 0.1.0 in `pyproject.toml` and `uv.lock`; CHANGELOG entry `0.1.0 - 2026-10-24`. The tag is left for the release step (#19).
- Developer `AGENTS.md`: `just edl-coverage` and `just e2e` in the commands, CI's four steps, and rule 14 (new commands, options, EDL fields and product-name files need their doc entries; tests enforce it). CONTRIBUTING links the language guide.
- Fix: `render` mixed the bed at `config.music.gain_db` and ignored the EDL's `music.gain_db`, so the review skill's "music too loud → lower `gain_db`" did nothing. Render now applies the EDL value (and keys freshness on it). Test: `test_the_edl_music_gain_overrides_the_config_level`.

Checked (acceptance):

- Fresh clone and README quickstart on this Mac (M3 Pro, 18 GB, macOS 27.0.1), in an empty scratch directory with uv's tool dirs pointed there so the global `motion-studio` was untouched: `git clone --branch ticket/18-docs` (main has no code yet), `uv tool install --python 3.12 '.[mac]'` (2 s, warm uv cache), `motion-studio --version` → `motion-studio 0.1.0`, `motion-studio setup` and `setup --music` (everything `present`: the shared cache already held the models and ACE-Step, and a first `setup` from a clone 20 minutes earlier had installed the 0.1.0 renderer in 26 s), `motion-studio doctor` all ok, `motion-studio init`, `motion-studio new my-video --from <dir with en_talking.mov, broll.mp4, image.png>`. Then Claude Code, headless (`claude -p "Edit my-video into a 45-second Reel and an X version." --dangerously-skip-permissions`) in the workspace, with nothing but the workspace files to go on. In 7 min 4 s it ran the whole workflow and delivered `final/my-video_9x16.mp4` (1080x1920) and `final/my-video_16x9.mp4` (1920x1080): it cut the greeting, the "um" and the abandoned take, kept the complete retake with a snap zoom and a title, left out the test-pattern B-roll and the fractal image as unrelated, generated an ACE-Step bed, and said the footage holds only ~13 s of speech so both videos are 7 s rather than 45 s. `motion-studio check my-video --final` afterwards: pass, 25 of 25 words re-heard, −13.8 LUFS / −2.6 dBTP in both formats, one caption-density warning (5.0 words/s). `motion-studio status`: every stage done. Opened stills: 9x16 at 4.5 s shows the zoomed presenter photo with the title fading out and the caption "is to keep" with "keep" in yellow; 16x9 at 1 s shows the portrait source on a blurred fill with the caption "to show you".
- Remotion terms: remotion.dev/license redirects to `LICENSE.md` on remotion-dev/remotion main, byte-identical to the pinned 4.0.538's file; summarised in README and THIRD_PARTY.md.
- `docs/renaming.md` matches `git grep -n motion-studio`: enforced by `tests/unit/test_docs.py`, and each entry's description was written from the matching lines.
- `just lint`, `just test`, `just schema-check`, `just edl-coverage` (99.89%) pass locally; CI green on the branch.

Deviations and why:

- The quickstart installs from a clone, not `uv tool install motion-studio`: motion-studio is not on PyPI and the repository is private. A stranger with access follows the same steps.
- Not a cold machine: the shared cache already held the models and ACE-Step, so setup's download times come from earlier tickets (renderer 14.5 min, ACE-Step 19 min) and are quoted in docs as such.
- No `v0.1.0` tag here; the spec tags after all tickets are done.

Open issues:

- `motion-studio doctor --fix` (user story 6) was never built; doctor prints a fix per item instead. The README does not promise `--fix`.
- CrisperWhisper's licence is now confirmed CC BY-NC 4.0 (the repository moved to `nyralabs/CrisperWhisper`); ROADMAP.md updated.

## Phase 13, adapted: hand-off (ticket #19)

Built:

- Reinstalled the global `motion-studio` from the integration branch (`uv tool install --force --reinstall-package motion-studio --python 3.12 '.[mac]'`); `motion-studio --version` prints `motion-studio 0.1.0` and `motion-studio doctor` reports every item ok, with the renderer at `~/Library/Caches/motion-studio/renderer/0.1.0`.
- `motion-studio init ~/Videos/reels` and `motion-studio new first-test --from <an empty folder>`: `~/Videos/reels/projects/first-test/raw/` exists and is empty; `motion-studio status first-test` there exits 0 with `0 clip(s) in raw/` and `next: copy clips into .../raw`.
- Re-read the workspace `AGENTS.md` and the five skills as an editing agent would, then walked the morning path (empty project, takes dropped into `raw/` afterwards). One trap: with an empty `raw/`, `ingest` and `analyze` both exited 0 and marked their stages done, then `plan draft` said "has no analysis, run analyze", so an agent would loop. `ingest` now exits 1 with `<raw> has no video or image files` and the hint `copy the takes into it, then run motion-studio ingest <slug>` (test `test_an_empty_raw_folder_is_a_user_error_naming_the_folder`), and `motion-studio-edit` step 0 tells the agent to ask for takes and wait when `status` reports 0 clips. With files copied into `raw/` after the failed ingest, `ingest`, `analyze`, `plan draft`, `plan validate`, `render --preview` and `check --preview` ran through on the fixture. `motion-studio agents sync` refreshed the skills in `~/Videos/reels`.
- `HANDOFF.md`: what was built, the morning steps, fixture timings labelled as such, known limitations from the open issues below and in earlier tickets, licence caveats (Remotion, the ACE-Step weights result, CrisperWhisper), blocked items (none) and the top five roadmap items. `docs/renaming.md` lists it under historical records.

Checked:

- Offline: under `sandbox-exec` with outbound network denied and localhost allowed (curl to huggingface.co fails with "Couldn't connect"), a fresh workspace ran `ingest`, `analyze`, `plan draft`, `plan validate`, `music` (ACE-Step generate), `plan validate`, `render --final` and `check --final` on the English fixture plus B-roll: verdict pass, 37 of 37 words re-heard, -13.9 LUFS / -2.5 dBTP, one caption-density warning. Times: 5, 9, 0, 1, 248, 1, 20 and 7 s.
- On this branch before merging: `just lint`, `just test` (344 passed), `just schema-check`, `just edl-coverage` (99.89%) and `just e2e` (16 passed in 606 s, with `MOTION_STUDIO_RENDERER_DIR` at the 0.1.0 cache install) pass.

Guide §12, definition of done:

- [x] All phases' acceptance criteria are met and logged in `BUILD_LOG.md`, except the Phase 13 dogfood on real footage, which spec #1 replaces with this hand-off and the creator's morning run.
- [x] `just lint`, `just test` and `just e2e` pass on this Mac; CI passes on Linux (see Checked, and the CI run for this branch).
- [x] A fresh workspace, an agent and "edit this into a Reel" give a checked 9x16 final without the agent writing code: headless Claude Code in ticket #18 (7 min 4 s, `check --final` pass). Only Claude Code was run; Codex, Gemini CLI and Cursor were not.
- [x] Works fully offline after `motion-studio setup --music`: the sandboxed run above.
- [x] English and Italian verified end to end: `just e2e` runs both.
- [x] README, docs, THIRD_PARTY (Remotion, ACE-Step weights, CrisperWhisper), CHANGELOG, ROADMAP and HANDOFF are complete.
- [x] The name is centralised in `APP_NAME` and `docs/renaming.md` is accurate: `tests/unit/test_docs.py` enforces it, and `HANDOFF.md` has its entry.
- [ ] Tagged `v0.1.0`: left to the orchestrator, who tags the integration branch after the final code review (PR #20 takes it to `main`).

Deviations and why:

- No dogfood on real footage and no finals for `first-test`: spec #1 (deviation "Phase 13") has the creator's morning run take its place, so `raw/` is left empty.
- No tag from this ticket: the orchestrator tags after the final review.
- The empty-`raw/` fix lands in 0.1.0 (CHANGELOG updated under 0.1.0), since that version is not tagged yet.

Open issues:

- `uv tool install` reuses its cached wheel when the version is unchanged, so reinstalling a newer checkout of 0.1.0 needs `--reinstall-package motion-studio`. Noted in `HANDOFF.md`.
- `motion-studio doctor --fix` (ticket #18's open issue) is still not built.
- A failed ingest on an empty `raw/` shows `ingest failed` in `status` until takes arrive; the `next:` line still says to copy clips in.

## Code review fixes (final review of feat/motion-studio-v0.1.0)

The final code review raised eight standards findings (S1 to S8) and seven spec findings (P1 to P7). All fifteen are fixed on `fix/code-review`, one commit per finding or tight group, each behavioural fix with a test that failed first.

Standards:

- S1, brand colours: `HexColor` in `config.py` accepts `#RGB` or `#RRGGBB` (with or without `#`) and normalises to upper-case `#RRGGBB`; anything else is a `UserError` naming the key (exit 1). It types `[brand] primary/accent` and the three caption colours, and the timeline's copies, so the schemas carry it. The renderer's `readableOn` moved to `lib/colour.ts` and now throws on a non-hex colour instead of falling back to white (vitest). The EDL has no colour fields, so validation happens at config load.
- S2, written paths: `analyze` and `ingest` no longer stop at 12 clips. Every command names its files through `path_line`: `wrote <path> (detail)`, or `unchanged <path>` on a rerun that left it alone. `analyze` also reports the asset contact sheets it draws (new `sheets` in its JSON). `look` prints `wrote <sheet>`, `new` prints `wrote <raw path> (linked into raw/)`, `setup` prints `<status> <path> (<item>)`. `plan validate` keeps its `→ build/timeline.json` line, since guide §6.6 fixes that summary format. Test: `test_written_paths.py` with 20 clips.
- S3, project language: the resolver calls `analysis.project_language` (most A-roll speech time, English fallback) instead of its own word count. A timeline now always has a language, so captions always get language rules.
- S4, `RenderTarget` (`src/motion_studio/target.py`) owns the stage name, the `--preview/--final` flag and the check record name (`check` or `check.final`). `render_project`, `check_project`, `output_path` and the `status` hints take it instead of a `final` bool.
- S5: `check` exits with `UserError.exit_code`, `doctor` with `DependencyError.exit_code`.
- S6: `cli/_output.py` holds `Reporter` (step, warn, progress), the `PreviewOption`/`FinalOption` pair and `pick_target`, which rejects both flags at once. The closures in render, check, setup, analyze, ingest and music are gone.
- S7: `Titles` takes the `LoadedFont`, both layers use `TEXT_WIDTH` from `lib/safezones.ts`.
- S8: the caption comment that restated its line is deleted.

Spec:

- P1, HEIC/HEIF (US23): `normalise_image` decodes them to PNG with `sips -s format png` on macOS or `heif-convert <in> <out>` elsewhere, then treats the PNG like any image. With neither tool, ingest skips the file with `skipped raw/<file>: nothing here decodes HEIC/HEIF; install libheif's heif-convert ...`, recorded in `state.json`, and ingests the rest. The decoder is an ingest parameter, so installing one re-runs ingest. `doctor` has a `heic decoder` line. pillow-heif was rejected: its binary wheels bundle libx265, which is GPL-2.0. Orientation: a JPEG with EXIF orientation 6 converted by `sips` to HEIC decodes to unrotated pixels plus an EXIF orientation 6 tag, so `exif_transpose` still runs after decoding (mac test `test_a_heic_photo_keeps_its_orientation`). Not done: no real iPhone HEIC was available, and Homebrew's `heif-convert` 1.23.1 on this Mac fails to load (`libx265.216.dylib` missing), so the Linux path and its argument order are unverified. A decoder that exists but fails on a file stops ingest with a `UserError`, the same as an unreadable JPEG.
- P2, mixed-shape A-roll (US51, US62): assemble centres every clip unscaled on a canvas as wide as the widest clip and as tall as the tallest (`assembly_canvas`), and the props carry each clip's region. The renderer's `framingAt` picks cover or fit-blur per run from that run's region and pans only inside it, so padding never shows and the face crop is a fraction of the run's own clip. Render `RECIPE` is 2, so earlier renders go stale. Tests: `test_a_landscape_take_beside_a_portrait_one_keeps_its_own_full_frame` (canvas 640x640, regions) and four vitest cases. Checked with the real Remotion renderer on a 720x1280 and a 1280x720 take: the landscape run fills 9x16 with no bars, the portrait run gets fit-blur in 16x9 and the landscape one covers it. Cost: a canvas mixing a 4K portrait and a 4K landscape take is 3840x3840, which makes the assembly encode larger.
- P3, `doctor --fix` (US6, guide §7): when the renderer, the VAD, ASR or face models, or DeepFilterNet are missing, it runs plain `setup`'s downloads, then checks again; JSON adds `fixed` and `fix_error`. It runs no brew, apt or npm for system tools and never fetches ACE-Step: the guide calls only the renderer `npm ci` and model downloads safe. Tests stand in for `run_setup`; the real downloads were not re-run, since this Mac already has everything.
- P4, Rich progress: `Reporter` draws a transient Rich progress line per step when stdout and stderr are TTYs and `--json` is off. Ingest encodes and the A-roll assembly feed a bar from ffmpeg's `-progress`; Remotion, music, check and setup show a spinner with the elapsed time, because the Remotion CLI runs with `--log=error` and ACE-Step reports no progress. Checked under `script` (a pseudo-terminal): the bar reaches 100% and clears before the `wrote` lines. Rich 15.0.0 API used: `Progress`, `SpinnerColumn`, `TextColumn`, `BarColumn`, `TaskProgressColumn`, `TimeElapsedColumn`, `transient=True`.
- P5, captions during full B-roll (guide §7b): `hide_during_broll` in config `[captions]` and the EDL's `captions` (default false) reaches the timeline; `captionsHidden` in `lib/captions.ts` hides them while a full-frame B-roll clip or image is showing, and keeps them over pip cards (vitest, resolver test). It covers full-frame images too, since they cover the speaker the same way.
- P6, loudness on finals (US67, US72-73): on `--final`, integrated loudness more than 1 LU from the target, or a true peak over the limit (more than 0.05 dB over, so a −1.46 dBTP reading rounds to the −1.5 limit and passes), is blocking with the fix "lower music.gain_db in edl.json (now X) and re-render", or just "re-render" without a bed. Previews keep warning, with the old 0.5 dB true-peak margin.
- P7, freshness: inputs are fingerprinted by SHA-256 of their content, cached in the project's `.hashes.json` against size and mtime, so unchanged files are not read again and `status` stays fast. A touched but unchanged file no longer makes a stage stale. Render and assemble list the mezzanines and voice files of the runs' clips, and render the B-roll and image files, so a mezzanine replaced in place re-renders; the check tests no longer touch the manifest to force that. Not done: a file rewritten with the same size and mtime is still trusted (the fast path the review asked to keep). The first run after upgrading re-runs every stage once, since the fingerprints changed format.

Checked:

- `just lint`, `just test` (368 Python, 42 vitest), `just schema-check` and `just edl-coverage` (99.88%) pass.
- `just e2e` after `just fixtures`: 16 passed in 576 s, with the repo renderer (`renderer/node_modules`, so P2 and P5 were in the composition). The tests marked `mac` and `renderer` (HEIC, real Remotion) were also run: 44 passed and 2 skipped. The real-Remotion test `test_renderer_cli.py` first failed because its hand-made props had no `regions` and its timeline fixture no `hide_during_broll`; both are added. The 9 faster-whisper cases of `test_analyze_fixtures.py` error because this venv was synced with only the `mac` extra (`faster_whisper is not installed`), which no change here touches.

Open issues:

- The global `motion-studio` tool is not reinstalled from this branch; that is for whoever merges it (`uv tool install --editable . --reinstall-package motion-studio` from the main checkout). A non-editable install of 0.1.0 also keeps the renderer cached under `renderer/0.1.0`, which predates P2 and P5, so it needs `rm -rf ~/Library/Caches/motion-studio/renderer/0.1.0` and `motion-studio setup` (a checkout with `renderer/node_modules` uses its own renderer and is not affected).
- HEIC from a real iPhone and the Linux `heif-convert` path are unverified (P1).

## Rename to motion-studio (ticket #27, spec #25)

Built:

- The product is motion-studio: distribution `motion-studio`, command `motion-studio`, import package `motion_studio` (`git mv src/<old> src/motion_studio`), renderer package `motion-studio-renderer`, workspace file `motion-studio.toml`, skills `motion-studio-edit`, `-plan`, `-look`, `-music` and `-review`, and the base exception `MotionStudioError`. Followed `docs/renaming.md` sections 1 to 6 in order, with one scripted pass that kept the two spellings apart: the hyphen for the command, files, folders and hints, the underscore for module paths and imports.
- `ENV_PREFIX` in `src/motion_studio/__init__.py` is `APP_NAME` upper-cased with hyphens turned into underscores (`MOTION_STUDIO`); the ten `APP_NAME.upper()` variable names use it. The renderer's install marker is `f".{APP_NAME}-installed"`.
- Historical records (ADRs, this log, HANDOFF, the build guide, past CHANGELOG entries) are rewritten under the new name, branch names in this log included (`feat/motion-studio-v0.1.0` was pushed under the old name). One new CHANGELOG line records the rename; `git grep -i` for the old name finds only it.
- `docs/renaming.md` describes the new names, the `ENV_PREFIX` rule and the rewritten-history policy in section 7. `tests/unit/test_docs.py` now searches for both spellings (`motion-studio` and `motion_studio`), since files that only import the package never contain the hyphenated name.
- Regenerated: `uv.lock` (`uv lock`), `schemas/` (`just schema`), and `renderer/package-lock.json` with `npm install --package-lock-only` (npm 11.6.0), which again dropped the 27 platform optional packages; they were put back from the previous lock, so the committed diff is the two `name` fields. The `docs/cli.md` option lists were compared line by line with `uv run typer motion_studio.cli utils docs --name motion-studio` and match.
- `docs/edl.md` is a symlink; it now points at `../src/motion_studio/reference/edl.md`.

Checked:

- `just lint`, `just test` (368 Python, 42 vitest), `just schema-check` and `just edl-coverage` (99.88%) pass.
- `just e2e`: 16 passed in 573 s, with `MOTION_STUDIO_CACHE_DIR` pointing at the existing cache under the old name (no new cache was downloaded), the repo renderer, and the fixture media copied from the main checkout. This runs the workers as `python -m motion_studio.asr.worker` and `motion_studio.vision.worker`.

Not done here: widening the descriptions (ticket #28) and migrating old workspaces and warning on old environment variables (ticket #29).

## Migrating old workspaces (ticket #29, spec #25)

Built:

- `src/motion_studio/migrate.py` holds `OLD_APP_NAME`, the one constant that keeps the previous name; the old workspace file, env prefix and cache path derive from it. `docs/renaming.md` has a new section, "Where the previous name stays", listing it and CHANGELOG, and `tests/unit/test_docs.py` fails when the previous name appears anywhere else.
- `agents sync` migrates first: it renames the old `.toml` to `motion-studio.toml` (contents unchanged), removes the old-name skill folders from `.claude/skills/` and `.agents/skills/`, then installs the skills, printing `renamed <old> -> <new>` and `removed <path>` (`renamed`, `removed` in JSON). Both `.toml` files present: exit 1 naming both, nothing touched. `find_workspace` fails with exit 1 and the `agents sync` hint in an unmigrated workspace; `find_workspace(unmigrated=True)` lets sync through. `paths` imports `migrate` inside `find_workspace`, since `migrate` imports `paths`.
- Every command prints `warning: <OLD>_X is no longer read; set MOTION_STUDIO_X instead` on stderr for each set variable with the old prefix, before running.
- Old cache: when the old platform cache directory exists, `MOTION_STUDIO_CACHE_DIR` is unset and the new cache holds no files, `doctor` adds an `old cache` warning whose fix is the adopting command, quoted with `shlex.quote`. Plain `mv` when the new directory is absent; when commands have already laid down its empty folders, `find <new> -depth -type d -empty -delete && mv <old> <new>`, so `mv` does not nest the old cache inside it and nothing with files is ever deleted. Nothing is moved automatically (the spec's proposal).
- Deviation: `setup` does not just print the command, it exits 1 with it as the hint before downloading, because carrying on would download everything into the new cache and make the `mv` impossible (US12: "so that I do not download everything again by accident"). Deleting the old directory, or setting `MOTION_STUDIO_CACHE_DIR`, lets setup run. `doctor --fix` reports that as `fix: setup stopped: ...`, next to its own `old cache` line.

Checked:

- `tests/unit/test_migration.py` drives each case through `CliRunner`, including running the printed command through `/bin/sh` on a cache path with a space and checking the models arrive in the new cache. `just lint`, `just test`, `just schema-check` and `just edl-coverage` pass.

