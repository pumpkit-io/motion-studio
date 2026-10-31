# Changelog

All notable changes to this project are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/).

## Unreleased

### Changed

- Renamed from reelcut to motion-studio: the command, the `motion_studio` package, the `motion-studio-renderer` package, the `motion-studio.toml` workspace file, the `motion-studio-*` skills, the cache directory and the `MOTION_STUDIO_` environment variables.

## 0.1.0 - 2026-10-24

The first release: a coding agent can edit talking-head footage into Reels and X videos on a Mac, offline.

### Added

- `motion-studio setup` downloads the speech-to-text, voice-activity, denoiser and face models and the Remotion renderer into a cache; `setup --music` installs ACE-Step 1.5 in its own environment and prints the weights' licence. `motion-studio doctor` checks ffmpeg and its filters, node, models, the renderer, the ACE-Step environment, the HEIC decoder, free disk and RAM; `doctor --fix` runs `setup`'s downloads for whatever of those is missing and checks again.
- Workspaces and projects: `init` (with `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `motion-studio.toml`, the library skeleton and the skills), `new`, `status`, `clean` and `config show`, with config merged from defaults, workspace, project and EDL policy.
- `ingest`: stable clip IDs and roles in `project.toml`, constant-frame-rate SDR mezzanines with rotation applied, HDR tone-mapping through VideoToolbox `scale_vt` (or `zscale`, or `colorspace` with a warning), DeepFilterNet voice cleanup with an `arnndn` fallback, and image normalisation, with HEIC and HEIF photos decoded to PNG through `sips` or `heif-convert` (skipped with a warning when neither is installed). An empty `raw/` is an error that names the folder to copy the takes into.
- `analyze`: language detection (English, Italian), word-level transcripts with mlx-whisper or faster-whisper, hard and soft fillers from per-language data files, utterances, pauses, unaligned voice, retake clusters, shots, static stretches, faces, role classification, the packed index `packed.md` and the asset catalogue `assets.md`.
- `words`, `look` and `look-asset` for exact word IDs and contact sheets, with a look budget.
- The EDL: `plan draft` writes a deterministic baseline and `plan validate` resolves it into a frame-accurate timeline with errors and warnings that carry fixes in EDL terms. Segments, drops and events (zoom, push, B-roll, image, title, emphasis) reference words and utterances by ID. `docs edl` prints the reference.
- `music`: an instrumental bed generated locally with ACE-Step 1.5 (vocal check, up to three tries), licensed library tracks with credits, or none; beats snap overlay starts.
- `render`: one ffmpeg assemble pass that keeps every A-roll clip at its own size, a Remotion composition per format (9x16, 16x9, 4x5) with face-centred reframing per run, fit-blur, jump-cut punch-ins, zooms, B-roll, images, titles, a logo and word-by-word captions in safe zones (optionally hidden over full-frame B-roll), then music ducking and two-pass loudness mastering to −14 LUFS and −1.5 dBTP with the video stream copied.
- `check`: re-transcribes the render to find clipped words at cuts, measures loudness, black and frozen frames, duration and caption density, draws the frames around every cut, and exits 1 when anything blocks delivery (on `--final`, loudness or true peak off target included).
- `agents sync` installs the five skills for Claude Code, Codex, Gemini CLI and Cursor.
- Every command takes `--json`, uses exit codes 0, 1, 2 and 3, and prints each path it writes as `wrote <path>`. In a terminal, long steps show Rich progress.
- Stage freshness compares content hashes of the inputs, cached against size and modification time.
- Pydantic contracts with generated JSON Schemas and renderer TypeScript types, checked for staleness in CI.
- Linux CI for lint, type checks, unit tests, the schema check, the resolver's coverage gate and the renderer tests; `just e2e` runs the whole pipeline on the English and Italian fixtures on a Mac.
- Documentation: README, `docs/cli.md`, `docs/edl.md`, `docs/architecture.md`, `docs/adding-a-language.md`, `docs/agents.md`, `docs/dependencies.md`, `docs/renaming.md` and `THIRD_PARTY.md`.
