# Architecture

motion-studio is a deterministic CLI that a coding agent drives. The agent makes every editorial choice by writing `edl.json`; motion-studio turns footage into text the agent can read and renders the edit it describes. motion-studio never calls a language model (ADR 0001) and never sends anything over the network after `setup`. Terms used here are defined in `GLOSSARY.md`.

## Principles

1. The agent reads; it never watches. Video becomes a compact index (`packed.md`) plus contact sheets on request.
2. The agent edits data, not code. Rendering code is fixed and tested.
3. The EDL names words and utterances by ID; the resolver does the timing arithmetic (ADR 0002).
4. `plan draft` writes a deterministic baseline; the agent refines it.
5. Every stage is idempotent and resumable, keyed by input fingerprints in `state.json`.
6. Short stdout, detail in files, `--json` for machines.
7. One heavy model in memory at a time: speech-to-text, face detection and music each run in a child process under a machine-wide lock.
8. Pydantic models are the only source of the data contracts; JSON Schemas and the renderer's TypeScript types are generated from them.

## Pipeline

```
recording script ──record web──► raw/<name>.mp4 + raw/<name>.markers.json   (product projects)
vhs tape ──record terminal──► raw/<name>.mp4 + raw/<name>.markers.json   (product projects)

raw/ ──ingest──► media/<id>.mp4 (CFR, SDR mezzanine), <id>.wav (48 kHz voice), <id>_16k.wav
                    │
                 analyze ──► analysis/<id>.json   words, fillers, pauses, utterances, shots,
                    │                             static stretches, faces, language
                    │        analysis/packed.md   the agent's index
                    │        analysis/assets.md   B-roll and image catalogue, contact/<id>.png
                    │
   host agent ◄─────┤  reads packed.md; runs `motion-studio words`, `motion-studio look` when needed
       │
       └─writes──► edl.json ──plan validate──► build/timeline.json (frames, output time)
                                     │
                   music ──► build/music.wav + build/music.json (beat grid, hits) ──► plan validate again
                                     │
              render: assemble (ffmpeg cuts, 30 ms audio fades) ──► build/assembled.mp4
                      compose  (Remotion: reframe, zooms, B-roll, captions) ──► build/composed_<fmt>.mp4
                      mix      (ffmpeg: duck music under voice, gain to target, true-peak limiter, video copied)
                                     │
                                     ▼
                     preview/<fmt>.mp4  or  final/<slug>_<fmt>.mp4
                                     │  (a final also gets final/<slug>_<fmt>_share.mp4, under 30 MiB)
                                     │
                   check ──► check/report.md, report.json, cuts.png
```

## Modules

Python lives in `src/motion_studio/`, the renderer in `renderer/`.

| Module | Responsibility |
|---|---|
| `cli/` | Typer app, one module per command group. `_output.emit` prints the human summary or the `--json` object; the group class maps `MotionStudioError` subclasses to exit codes 1, 2 and 3. |
| `errors.py` | `UserError` (1), `DependencyError` (2), `InternalError` (3), each with a hint. |
| `config.py` | The `Config` model and `load_config`: built-in defaults < `motion-studio.toml` < `project.toml` < the EDL's `policy` (which may override `[edit]` only). |
| `paths.py` | Finds the workspace, resolves a project's directories, and locates the cache (`~/Library/Caches/motion-studio` on macOS). |
| `state.py` | `state.json`: per-stage status, input fingerprints and warnings; the per-project lock; the machine-wide heavy-model lock in the cache; the free-disk guard. |
| `migrate.py` | Recognises what the previous name left behind: `agents sync` migrates old workspaces, `doctor` and `setup` print the `mv` for the old cache, and old environment variables warn. The only module that keeps the previous name. |
| `kind.py` | The project kind (`talk` or `product`, ADR 0004) read from `project.toml`, and the guard that makes a command for the other kind exit 1. |
| `workspace.py` | `init`, `new`, `status`, `clean`, and copying the workspace template. |
| `doctor.py`, `setup.py` | Machine checks, and one-time downloads into the cache. |
| `media/` | ffmpeg and ffprobe as argument lists (never shell strings), probing the installed ffmpeg's filters and options, mezzanine normalisation, frame reading. |
| `audio/` | Voice extraction and denoising: DeepFilterNet, or ffmpeg `arnndn` with a vendored model as the fallback. |
| `ingest.py` | Clip IDs, provisional roles, mezzanines, enhanced audio, image normalisation, `media/manifest.json`; in product projects, screen recordings and their 1 fps contact sheets. |
| `record/` | `record web`: the shipped Node runner and helper library (`record/node/`) run the agent's recording script in headless Chromium and leave CDP screencast frames, markers and the cursor track; Python lays the frames on a 30 fps grid, encodes `raw/<name>.mp4` and writes its markers sidecar. `record terminal` (`record/terminal.py`): wraps the agent's vhs tape in a hidden preamble (clean env and prompt, `Launch` through a wrapper, the Claude Code trust prompt), turns `Mark` lines into screenshots whose frame numbers an `ffmpeg` shim logs, and encodes vhs's frames unscaled. `record/take.py` holds what both share: the checks, the scratch directory and the move into `raw/`. Installs the pinned Playwright for `setup --record`. |
| `asr/` | Silero VAD, the `ASRBackend` protocol with `mlx-whisper` and `faster-whisper`, and the worker subprocess. |
| `vision/` | Shot and motion detection in-process; face detection (MediaPipe, YuNet fallback) in a worker subprocess. |
| `analysis/` | Pure functions over transcripts and spans: filler tagging, utterances, pauses, unaligned voice, retake clusters, role finalisation, and the packers that write `packed.md` and `assets.md`. |
| `lang/` | One TOML file per language; see `docs/adding-a-language.md`. |
| `analyze.py` | The analyze stage: runs the workers, the analysers and the packers per clip. Product projects skip speech, faces and retakes and read each screen recording's markers sidecar. |
| `look/` | Contact sheets for a time range or an asset, and the look budget. |
| `edl/` | EDL and timeline models, reference resolution, the draft, the resolver and the validate summary. All pure. |
| `plan.py` | Reads the analysis and the EDL, calls the resolver, writes `build/timeline.json`. |
| `music/` | The ACE-Step client and worker (run with the isolated environment's Python), the vocal check, the small-speaker shaping of generated beds, the library picker and the bed analysis (tempo, beat and bar grid, sections and hits). |
| `render/` | Assemble (one ffmpeg filter graph), compose (props and public directory, then the Remotion CLI), mix, the share copy beside each final, and locating the installed renderer. |
| `check/` | Re-transcription and diff near cuts, loudness, band energy, black and frozen frames, duration, caption density, the cut stills, and the report. |
| `agents/` | Installs the canonical skills from `templates/skills/` into each agent's skill directory. |
| `templates/` | The workspace template and the five skills. |
| `reference/edl.md` | The EDL reference printed by `motion-studio docs edl` (`docs/edl.md` links to it). |

## The resolver

`motion_studio.edl.resolve(clips, edl, config, beats=None) -> Resolution` is a pure function from the analysis, the EDL and the effective config to a `Timeline`. It expands segment references to word spans, applies drops and keeps, removes fillers per the policy, splits segments into runs at removed words and long pauses, pads and tightens the edges, drops runs shorter than `min_segment_ms` with a warning, aligns every edge to the output frame grid, frames each run on the median face position, alternates punch-in scale across jump cuts, anchors events to the words that survive, and snaps B-roll and image starts to beats within 80 ms. Speech cuts never move to a beat. A product EDL (`ProductEdl`, the other side of the `Edl` union on `kind`) goes to `edl/product.py` instead: its scenes are laid back to back on a `BeatGrid` (`edl/grid.py`: the bed's beats, or 120 bpm without music) at whole output frames, and footage scenes resolve their marker IDs and offsets to source seconds and the playback rate that fills the scene. Each scene type has one resolver function in `product.py`'s `_SCENES` table. Errors and warnings are `Issue` objects with a code, a message and a fix in EDL terms. It is the most heavily tested module: example tests, Hypothesis property tests, and a 95% line-coverage gate in CI (`just edl-coverage`).

## Contracts

| Contract | Model | Schema | Written by | Read by |
|---|---|---|---|---|
| Config | `motion_studio.config.Config` | `schemas/config.schema.json` | the creator | every stage |
| Clip analysis | `motion_studio.analysis.models.ClipAnalysis` | `schemas/analysis.schema.json` | analyze | plan, look, check |
| Markers sidecar | `motion_studio.analysis.models.ScreenMarkers` | `schemas/markers.schema.json` | the recorders (`record web`, `record terminal`), or the creator by hand (`raw/<name>.markers.json`) | analyze, into `analysis/<id>.json` |
| EDL | `motion_studio.edl.models.Edl` | `schemas/edl.schema.json` | the host agent (`plan draft` for the baseline) | plan validate |
| Timeline | `motion_studio.edl.models.Timeline` | `schemas/timeline.schema.json`, `renderer/src/types.gen.ts` | plan validate | render, the renderer, check |
| Music bed | `motion_studio.music.stage.MusicInfo` | `schemas/music.schema.json` | music | plan validate, the host agent |

`just schema` regenerates the schemas and the TypeScript types; `just schema-check` (in CI) fails when the committed copies are stale. Every contract carries `schema_version: 1`. `media/manifest.json` and `analysis/retakes.json` are Pydantic models too, read only by motion-studio, with no published schema.

## Processes and memory

Heavy models never load in the CLI process. `asr.transcribe_clips`, `vision.detect_faces` and the music client each start a worker (`python -m motion_studio.asr.worker`, `python -m motion_studio.vision.worker`, and the ACE-Step environment's Python running `music/acestep_worker.py`), exchange JSON over stdin and stdout, and hold `heavy_model_lock` in the cache directory while it runs. The lock is a file lock, so two projects, or two terminals, never hold a transcriber and a music model in memory at once. On the build machine (18 GB) peak worker memory was about 0.9 GB for mlx-whisper, 2.3 GB for faster-whisper and 1.8 GB for ACE-Step plus its unified-memory use.

ACE-Step runs from its own uv environment in `<cache>/envs/ace-step`, so its PyTorch and other pins never meet motion-studio's.

## Rendering

The renderer is a Remotion 4 project with two compositions: `Reel` for talk timelines and `Product` for product timelines. `render` writes `build/props_<fmt>.json` (the timeline, the format, the assembled video's size and each A-roll clip's region in it, and the brand font and logo paths) and a public directory of hard links, then runs the installed `remotion render` CLI. Assemble centres every A-roll clip unscaled on a canvas as wide as the widest clip and as tall as the tallest, so a landscape take beside portrait ones keeps its full frame. The composition frames each run from its own clip's region: it draws the reframed base video (fit-blur for a portrait clip in a landscape format, chosen per run), zoom and push transforms, B-roll and image overlays, titles, the logo and word-by-word captions inside each format's safe zone. Remotion's output keeps the voice; the mix stage adds the ducked music bed and masters loudness (a fixed gain, then an oversampled true-peak limiter) while copying the video stream, so video is encoded once by Remotion.

A product render skips assemble. `Product.tsx` draws each timeline scene in a `Sequence` with one component per scene type under `renderer/src/scenes/` (title card, footage in a browser frame), all on the brand backdrop; its pure geometry (device frame layout and transform, palette) lives in `renderer/src/lib/` with vitest specs. The public directory links each footage scene's mezzanine, and Remotion is asked for a silent audio track so the mix can add the bed.

## Stage state

Each stage records its inputs' fingerprints (path and SHA-256 of the content), its parameters and its outputs in `state.json`. Content hashes are cached in the project's `.hashes.json` against each file's size and modification time, so only files whose size or time changed are read again and `status` stays fast. Render lists the mezzanines, voice files and overlay assets it reads among its inputs, so replacing one in place re-renders. A stage whose inputs and parameters are unchanged reports `unchanged` and does nothing. Stages list upstream outputs as inputs, so a re-ingest makes analysis stale, a re-validate makes the render stale, and `status` names the next command. Fallbacks are recorded as warnings on the stage.

## Testing seams

- The `motion-studio` CLI on a fixture workspace: integration and e2e tests with the markers `slow`, `mac`, `models`, `renderer`, `music` and `record`, run locally (`just test-all`, `just e2e`). `record web` is tested end to end on a static HTML page and `record terminal` on a tape that launches a stand-in Claude Code (`tests/fixtures/record/`).
- The resolver: example and property tests, in CI.
- The renderer's pure libraries (camera transform, caption paging): vitest, in CI.
- The pure analysers, through `analyse_transcript`, `find_retakes` and `pack_project`, with constructed transcripts, in CI.

CI runs `just lint`, `just schema-check`, `just test` and `just edl-coverage` on Linux for every pushed branch.
