# Changelog

All notable changes to this project are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/).

## Unreleased

### Added

- Product videos: `new --kind product` makes a project whose kind is stored in `project.toml` and shown by `status`. Its EDL is a list of scenes (kinetic text, title cards, footage in a browser or terminal frame, proof shots and a logo outro) laid on the music's beat grid, with camera moves, highlights, masks, caption pills and flashes on footage addressed by marker and element IDs. `plan draft` writes a baseline from the screen recordings and images, ending on the logo outro. `[brand]` gains `wordmark` and `mascot`, a sprite sheet with frame timings or an animated GIF, drawn without smoothing; without a wordmark the outro sets the title in type. The `motion-studio-product` skill covers the process, and the workspace `AGENTS.md` sends the agent to the right skill by project kind.
- `record web` runs a recording script in headless Chromium and writes a constant-frame-rate clip with a markers sidecar (markers, element boxes and the cursor track). `record terminal` runs a vhs tape in a clean shell, with `Launch` and `Mark` lines. `setup --record` installs a pinned Playwright and Chromium into the cache, and `doctor` checks for `vhs` and `ttyd` and prints their install line, with a warning that it may upgrade ffmpeg, without running it.
- `look <slug> --at <scene | marker | seconds>` writes stills of the latest render, counted once per call against the look budget.
- `render --final` writes a share copy beside each final, `final/<slug>_<format>_share.mp4`, under 30 MiB for chat and phones.
- Music: `music.json` reports the tempo checked against the period of the sections (`detected_bpm`, `tracker_bpm`, `tempo_from`), the bar grid (`bars`, `beats_per_bar`), the sections and the named hits (`intro_end`, `build`, `drop`, `ending`). `music.align` lands a hit on a scene's start, extending or shortening the bed by whole bars at phrase boundaries. `music.preset` supplies a prompt (`launch`, plus the four talk moods), and `music --candidates N` generates several seeds in one model load and lists them. On a product project the bed is sized from the scenes.
- `check` on a product project loads no speech model; it writes `check/contact.png` at one frame per second, lists the masked regions and warns when the cursor covers a highlight's target. Both kinds report energy in four bands and a `small_speaker` issue, which blocks on product renders.

### Changed

- Every generated bed is shaped for small speakers (high-pass, low-shelf cut, presence and air boost, gentle compression); library tracks are left as licensed. A bed generated before shaping is shaped on the next `music` run without generating it again.
- Mastering applies a fixed gain to the target loudness and then a 4x-oversampled true-peak limiter, instead of linear loudnorm, which turned to compression when the peaks would pass the ceiling. Renders cached before this change render again.

- Renamed from reelcut to motion-studio: the command, the `motion_studio` package, the `motion-studio-renderer` package, the `motion-studio.toml` workspace file, the `motion-studio-*` skills, the cache directory and the `MOTION_STUDIO_` environment variables.
- New workspaces caption in the `clean` caption style, set in TikTok Sans 700 with a thinner outline. TikTok Sans is bundled next to Inter, so renders stay offline. Existing workspaces keep `style = "pop"` and `font = "Inter"` until they set `style = "clean"` and `font = "TikTok Sans"` under `[captions]` in `motion-studio.toml`. The thinner outline applies to every caption style.
- Titles use the caption font's weight: 700 for TikTok Sans, 800 for Inter and for brand font files.
- A caption page holds at least two words where it can: a lone word joins a neighbouring page, or the two are rebalanced into two pages of two or more words. A lone word still stands alone after a sentence end or a long silence, or when no split keeps the word, character and width caps.

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
