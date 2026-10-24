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

## Analysis (ticket #6, 2026-10-24)

| Item | Value | How checked |
|---|---|---|
| rapidfuzz | 3.14.6 | `fuzz.token_set_ratio` run in the venv: float 0-100, a word subset scores 100 |

## Ingest (ticket #5, 2026-10-24)

| Item | Value | How checked |
|---|---|---|
| DeepFilterNet | `deep-filter` 0.5.6 release binary (latest release, 2023-08-31) | `gh release view v0.5.6 -R Rikorose/DeepFilterNet`; ran `--help`, `--version` and a 48 kHz mono WAV through it on arm64 macOS 27 |
| `deep-filter` flags | `--compensate-delay` (`-D`), `-o <dir>` (writes `<dir>/<input name>`) | `deep-filter --help`; with `-D` the output is about 30 ms shorter, so ingest pads back to the input length |
| `deepfilternet` pip package | 0.5.6: no cp312 wheel for `deepfilterlib`, `numpy<2` | PyPI JSON API; unusable with Python 3.12 and numpy 2.5, hence the binary |
| Binary SHA-256 (pinned in `reelcut.audio.enhance`) | aarch64-apple-darwin `4601e7f4…1081`, x86_64-apple-darwin `d3be8400…5b50f`, x86_64-unknown-linux-musl `70775e25…2ef7da`, aarch64-unknown-linux-gnu `14e02a1c…57166` | computed from the downloads |
| ffmpeg `arnndn` | needs a model file (`m=`); no built-in default | `ffmpeg -h filter=arnndn` (9.0.1) |
| RNNoise model | `sh.rnnn` from GregorR/rnnoise-models `3eee541` | vendored in the package |
| ffmpeg `scale_vt` (ADR 0003) | options `w`, `h`, `color_matrix`, `color_primaries`, `color_transfer`; needs VideoToolbox frames: `-init_hw_device videotoolbox=vt -filter_hw_device vt` and `format=p010le,hwupload,scale_vt=…,hwdownload,format=p010le` (downloading as `nv12` fails) | `ffmpeg -h filter=scale_vt`; tone-mapped a 10-bit HLG HEVC clip and checked the tags with ffprobe |
| ffmpeg `colorspace` | cannot read HLG or PQ transfers; the fallback reads them as `bt2020-10` | `ffmpeg -h filter=colorspace` |
| ffmpeg autorotate | on by default when filtering; the output has no display matrix | ingest test with `-display_rotation 90` (input option, ffmpeg 6+) |
| `-fps_mode cfr` + `fps=` filter | gives `avg_frame_rate` = `r_frame_rate` = project fps on the VFR fixtures | ffprobe in the fixture test |

## EDL and timeline (ticket #10, 2026-10-24)

| Item | Value | How checked |
|---|---|---|
| json-schema-to-typescript | 16.0.0 (MIT, Node >= 16) | `npm view`; `json2ts --help` for `--bannerComment`, `--unknownAny` and stdin input. Renderer devDependency; `scripts/gen_schemas.py` runs `renderer/node_modules/.bin/json2ts` |
| hypothesis | 6.170.9 | `st.composite`, `st.DrawFn`, `st.permutations`, `st.randoms(use_true_random=False)` run in the property tests |
| pydantic | 2.14.1 | `json_schema_serialization_defaults_required` with `model_json_schema(mode="serialization")` marks defaulted timeline fields required |

npm 11.6.0 drops every platform-specific optional package (`@rolldown/binding-*`, `lightningcss-*`, `fsevents`) from `package-lock.json` whenever it rewrites the lock, after which vitest cannot find its native binding (npm/cli#4828). The entries were merged back from the previous lock and `npm ci` verified. Re-check the lock diff after any renderer dependency change.

## Renderer composition (ticket #12, 2026-10-24)

| Package | Version | Licence | Why |
|---|---|---|---|
| @remotion/layout-utils | 4.0.538 | MIT | `measureText({ text, fontFamily, fontSize, fontWeight })` for the caption width cap |
| @remotion/fonts | 4.0.538 | MIT | `loadFont({ family, url, weight, unicodeRange })`; calls `delayRender` until the font is in `document.fonts` |
| @fontsource/inter | 5.3.0 (published 2026-07-19) | OFL-1.1 | Inter 800 woff2 files (latin, latin-ext) bundled by Remotion's webpack, so the default font needs no network |

Remotion APIs checked against the installed 4.0.538 type definitions:

- `@remotion/captions`: `Caption = { text, startMs, endMs, timestampMs, confidence, pageBreakAfter? }`; `createTikTokStyleCaptions({ captions, combineTokensWithinMilliseconds, breakOnSilenceAfterMilliseconds? })` returns `{ pages: TikTokPage[] }` with `{ text, startMs, durationMs, tokens: { text, fromMs, toMs }[] }`. A caption's `pageBreakAfter: true` closes the page; with `combineTokensWithinMilliseconds: Infinity` that is the only break.
- `remotion`: `<OffthreadVideo>` takes `trimBefore` (frames; `startFrom` is deprecated as of this version), `muted`, `style`. `CalculateMetadataFunction<Props>` receives `{ props, defaultProps, abortSignal, compositionId, isRendering }` and may return `width`, `height`, `fps`, `durationInFrames`.

Remotion CLI flags (`npx remotion render --help` and `npx remotion still --help`, @remotion/cli 4.0.538), each used in `tests/integration/test_renderer_cli.py`:

| Flag | Value used | Checked |
|---|---|---|
| `render <entry> <composition> <output>` | `src/index.ts Reel <out.mp4>` | positional form in `remotion --help` |
| `--props` | path to a JSON file | accepts a file path (the render test passes one) |
| `--public-dir` | the build's public directory | `staticFile()` paths resolve inside it |
| `--concurrency` | 4 | |
| `--codec` | `h264` | |
| `--crf` | 16 | |
| `--scale` | 0.5 (preview) or 1 | 16x9 at 0.5 renders 960x540 |
| `--log` | `error` | |
| `still ... --frame=<n>` | stills for visual checks | `remotion still --help` |

The first render downloads Chrome Headless Shell (about 570 MB) into `renderer/node_modules/.remotion/`; `npx remotion browser ensure` does that ahead of time.

## Speech (ticket #7, 2026-10-24)

| Item | Value | How checked |
|---|---|---|
| Silero VAD | `silero_vad.onnx` from tag v6.2.3 (latest release, 2026-09-23), `raw.githubusercontent.com/snakers4/silero-vad/v6.2.3/src/silero_vad/data/silero_vad.onnx`, SHA-256 pinned in `reelcut.asr.vad` | `gh release list`; ONNX inputs `input` [1, 64 + 512], `state` [2, 1, 128], `sr` int64; outputs probability and new state, as in `OnnxWrapper` of that tag's `utils_vad.py` |
| mlx-whisper 0.4.3 | `transcribe(audio, path_or_hf_repo=, word_timestamps=, initial_prompt=, condition_on_previous_text=, hallucination_silence_threshold=, clip_timestamps=[start, end, ...], language=)`; words carry `word`, `start`, `end`, `probability`. Language ID: `model.detect_language(mel)` returns `(tokens, {code: prob})` for one 30 s mel segment; model loaded with `mlx_whisper.transcribe.ModelHolder.get_model(path, mx.float16)` | Read from the installed package source |
| MLX model | `mlx-community/whisper-large-v3-turbo` @ `a4aaeec0636e6fef84abdcbe3544cb2bf7e9f6fb` (1.6 GB `weights.safetensors`) | Hugging Face API |
| faster-whisper 1.2.1 | `WhisperModel(path, device="cpu", compute_type="int8")`; `transcribe(..., word_timestamps=True, vad_filter=False, clip_timestamps=[...], hallucination_silence_threshold=, condition_on_previous_text=False)`; `detect_language(audio)` returns `(code, prob, [(code, prob), ...])` | Read from the installed package source |
| CTranslate2 model | `dropbox-dash/faster-whisper-large-v3-turbo` @ `0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf`. faster-whisper's own `large-v3-turbo` alias names `mobiuslabsgmbh/...`, which Hugging Face now redirects to this repository | Hugging Face API (HTTP 307 on the old name) |
| huggingface_hub | 2.3.0 (pulled by both backends); models go to `<cache>/models/huggingface` through `snapshot_download(cache_dir=...)` | `uv pip show` |

## Music (ticket #14, 2026-10-24)

| Item | Value | How checked |
|---|---|---|
| ACE-Step 1.5 source | `ace-step/ACE-Step-1.5` @ `ca1e85fe9430179831e6bc6be790c332190a3866` (main on 2026-10-24), package `ace-step` 1.5.0, Python `>=3.11,<3.13` | `gh api`; `pyproject.toml` at that commit |
| Install on Apple Silicon | The official README and `docs/en/INSTALL.md`: get the source, `uv sync`; macOS gets `torch>=2.9.1`, `mlx>=0.25.2` and `mlx-lm` by platform markers, and the MLX DiT and VAE are used automatically on MPS. reelcut downloads the commit tarball and runs `uv sync --frozen` in `<cache>/envs/ace-step/src` | README, INSTALL.md and the startup log (`MLX-DiT ... initialized`, `Native MLX VAE initialized`) |
| Weights | `ACE-Step/Ace-Step1.5` @ `19671f406d603126926c1b7e2adc169acbcade22`: `acestep-v15-turbo` (DiT, 8 steps), `vae`, `Qwen3-Embedding-0.6B`, `acestep-5Hz-lm-1.7B`; 9.4 GB in `src/checkpoints`, where `initialize_service(project_root=...)` looks | Hugging Face API; `MAIN_MODEL_COMPONENTS` in `acestep/model_downloader.py` |
| Python API | `AceStepHandler().initialize_service(project_root, config_path="acestep-v15-turbo", device="auto")` returns `(status, ok)`; `generate_music(dit_handler, llm_handler, GenerationParams, GenerationConfig, save_dir)`; `llm_handler=None` with `thinking=False` runs the DiT alone (`use_lm` is False) | `docs/en/INFERENCE.md`; `acestep/inference.py`, `init_service_orchestrator.py` |
| Duration, BPM, seed | `GenerationParams(duration=<s>, bpm=<int>, seed=<int>)` with `GenerationConfig(batch_size=1, use_random_seed=False, seeds=[seed], audio_format="wav")`; output 48 kHz stereo WAV, normalised to −1 dBFS peak | INFERENCE.md; the generated file |
| Instrumental | No hard switch on the DiT path: `GenerationParams.instrumental` is only read by the LM. The lyrics tag `[Instrumental]` is the convention ACE-Step's own UI and training data use, so reelcut sends it and runs the VAD check | `grep` of `acestep/` |
| librosa | 1.0.0: `beat.beat_track(*, y, sr, units="time", trim=False)` returns `(tempo, beats)`; `load(path, sr=, mono=)` | `inspect.signature` on the installed package |
