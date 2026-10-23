# Build Guide: `reelcut` — an agent-driven video editing harness

> **Who this is for:** an autonomous coding agent (Claude Code, Codex, Gemini CLI, Cursor, …) that will build this project from an empty directory.
> **What you will build:** an open-source, agent-agnostic harness that lets *any* coding agent turn raw talking-head footage (plus images and B-roll) into finished short-form videos for Instagram Reels and X. It handles trimming, filler and dead-air removal, retake selection, hook selection, punch-in zooms, face-centred vertical reframing, animated captions, B-roll and image overlays, locally generated music, ducking and loudness mastering.
> **Working name:** `reelcut` (a placeholder; see §2.7 for how to keep it renameable).

---

## 0. How to use this guide (read first)

1. **Work in phases.** §8 lists phases 0–13. Do them in order. Each phase ends with **acceptance criteria**; do not start the next phase until they pass. Commit at the end of every phase (`git commit -m "phase N: <summary>"`).
2. **Keep a build log.** Create `BUILD_LOG.md` at the repo root in Phase 0. After each phase, append: what you built, versions you pinned, deviations from this guide and why, and open issues. This is how the human follows your work.
3. **Use a task list** (your agent's todo or task tool) with one item per phase, and tick them off.
4. **Never guess third-party APIs or CLI flags.** Libraries in this space change fast. Before using any external tool or library, check its installed `--help`, its README or its official docs, and record the verified version in `docs/dependencies.md`. Where this guide says **VERIFY**, you must check before writing code. If reality differs from this guide, follow reality and log the deviation.
5. **Don't ask the human unless truly blocked.** The preference decisions are already made (§2). If something is ambiguous, pick the option most consistent with §3 ("Principles"), log it in `BUILD_LOG.md`, and continue. Stop and ask only for things you cannot do yourself (e.g. a licence you cannot verify, or hardware you don't have).
6. **Prefer boring, testable code.** The intelligence lives in the host agent. The harness is deterministic plumbing with clean data contracts.

---

## 1. Goal and scope

### 1.1 The user experience we are building

A creator drops files into `projects/<slug>/raw/`, opens their coding agent in the workspace and says: *"Edit this into a 45-second Reel and an X version."* The agent then:

1. ingests and normalises the footage (constant frame rate, SDR, cleaned audio);
2. analyses it into a compact text index: word-level transcript, fillers, pauses, retakes, shots, static stretches, face positions and an asset catalogue;
3. reads that index (and looks at a few contact-sheet images only when needed) and writes an **edit decision list** (`edl.json`) that references transcript IDs, not raw timestamps;
4. validates and resolves the EDL into a frame-accurate timeline;
5. generates mood-matched instrumental music locally;
6. renders a preview, self-checks it (re-transcribe and diff, cut-boundary stills, loudness, black and frozen frames) and fixes problems;
7. renders the final files per platform.

By default this runs end to end. Optional review gates (§2.3) pause after the plan and/or after the preview.

### 1.2 In scope for v0.1.0

- Talking-head A-roll (one speaker), any number of takes and clips per project.
- Images and B-roll video as overlays (full-frame cutaway or picture-in-picture).
- Languages: **English and Italian**, auto-detected per video. The architecture must be extensible to more languages via data files.
- Output formats: `9x16` (1080×1920, Reels/X vertical), `16x9` (1920×1080, X horizontal), `4x5` (1080×1350, X/feed).
- Captions: word-by-word animated captions in the spoken language.
- Zooms: punch-in on emphasis, alternating punch on jump cuts, slow push-ins.
- Music: local generation with ACE-Step 1.5, or a curated local library; beat detection; ducking; loudness mastering.
- Self-QA loop.
- Agent layer: `AGENTS.md`, skills in the open Agent Skills (`SKILL.md`) format, and a workspace template.

### 1.3 Non-goals for v0.1.0 (put these in `ROADMAP.md`)

- An MCP server (deliberately excluded; the CLI plus skills is the interface).
- Multi-speaker podcasts and diarization-driven edits.
- Sound effects (whooshes and so on) and their licensing.
- NLE export (FCPXML/OTIO). Leave a hook in the architecture and list it on the roadmap.
- Any paid API by default. The harness must work fully offline after setup.
- The harness calling an LLM itself. **All editorial judgement is done by the host agent** reading files the harness produces.

---

## 2. Fixed decisions (do not re-ask)

### 2.1 Target platform
- **Primary:** macOS on Apple Silicon (M-series) with 16 GB+ unified memory. Optimise for this.
- **Secondary:** Linux and Intel macOS (CPU-only, optionally CUDA), so others can use the open-source project. Every Apple-only component (MLX) must have a portable fallback backend. CI runs on Linux; Apple-only tests are marked and skipped there.

### 2.2 Languages
- Videos may be in English or Italian. Detect the language **per clip**; project language = majority of A-roll speech unless overridden in `project.toml`.
- Filler lexicons, transcription prompts and caption typography rules live in per-language data files (`reelcut/lang/en.toml`, `reelcut/lang/it.toml`), so a contributor can add a language without touching code.

### 2.3 Autonomy
- **Default: fully autonomous end to end.**
- **Optional gates**, configured in `reelcut.toml` under `[review]` (`plan = false`, `preview = false`) or requested in natural language by the user ("let me review the plan first"). When a gate is on, the agent stops at that point, presents a concise summary and waits.

### 2.4 Interface
- **No MCP server.** The interface is a **CLI** (`reelcut …`) with stable, documented commands and `--json` output, plus **skills** and an **`AGENTS.md`** that teach any agent how to drive it.

### 2.5 Music
- **Local AI generation with ACE-Step 1.5** is the default. A curated local library (`library/music/` + `tags.json`) is the fallback. The harness never downloads music from the web at edit time.

### 2.6 Licence and dependencies
- Project licence: **MIT**.
- Must clearly document third-party licences in `THIRD_PARTY.md`, especially:
  - **Remotion** is *not* OSI open source. Its licence is free for individuals and companies of up to 3 people; larger companies need a company licence. The README must state this prominently. **VERIFY** the current terms at remotion.dev/license.
  - **ACE-Step 1.5 weights**: sources disagree on the licence. **VERIFY** the licence file of the exact weights `reelcut setup` downloads, record it in `THIRD_PARTY.md`, and write it into every generated `music.json`.
  - **CrisperWhisper** (verbatim filler-aware ASR): the model card has, as far as is known, a **non-commercial** licence (CC BY-NC 4.0). **VERIFY.** If it is non-commercial, it must be an **optional, off-by-default** backend with a warning, because the primary user is a business. The default filler pipeline must not depend on it (see §6.2).
  - Avoid AGPL dependencies in the core (e.g. Ultralytics YOLO). Use MediaPipe (Apache-2.0) and OpenCV.

### 2.7 Name and repo
- Use `reelcut` everywhere, but keep the name in as few places as possible: the Python package name, the CLI entry point, one constant `APP_NAME` in `reelcut/__init__.py`, the npm package name in `renderer/package.json`, and docs. Add `docs/renaming.md` listing every place the name appears (generate it with `git grep -n reelcut`, then check it by hand).
- No remote is configured yet. Do not create a GitHub repo; work locally with git.

---

## 3. Architecture

### 3.1 Principles (use these to settle any ambiguity)

1. **The agent reads; it never watches.** The harness turns video into compact text (`packed.md`) plus on-demand images (`look` contact sheets). The agent must never be asked to process every frame.
2. **The agent edits data, not code.** All creative decisions go into `edl.json`. Rendering code is fixed and tested. Routine edits never require writing Python or TSX.
3. **Reference IDs, not floats.** The EDL references transcript utterance and word IDs (`c1.s004`, `c1.w127`). The resolver turns them into frame-accurate times with consistent padding and snapping rules. LLMs are good at choosing sentences and bad at choosing millisecond values.
4. **Deterministic baseline, agent refinement.** `reelcut plan draft` produces a sensible EDL automatically (all speech, latest complete take per retake cluster, hard fillers removed, pauses tightened). The agent improves on it (hook, order, cuts, emphasis, B-roll, music).
5. **Every stage is idempotent, cached and resumable.** Stage outputs are keyed by input hashes; `state.json` records progress. Re-running a command with unchanged inputs is a no-op.
6. **Concise stdout, detail in files.** Commands print a short summary (and `--json` for machines); full detail goes to files the agent can read when needed. This protects agent context windows.
7. **One heavy model in memory at a time.** On 16 GB machines, ASR, face detection and music generation run sequentially in separate processes and release memory when done.
8. **Single source of truth for contracts.** Pydantic models define the analysis, EDL and timeline schemas. JSON Schema files are generated from them, and TypeScript types for the renderer are generated from the JSON Schema. A CI check fails if the generated files are stale.

### 3.2 Pipeline

```
raw/ ──ingest──► media/ (CFR, SDR mezzanine + enhanced 48k audio)
                    │
                 analyze ──► analysis/<clip>.json   (words, fillers, pauses, utterances, shots,
                    │                                static ranges, face track, language)
                    │        analysis/packed.md      (compact transcript for the agent)
                    │        analysis/assets.md      (catalogue of images / B-roll)
                    │
     agent ◄────────┤  reads packed.md, optionally `reelcut look …` PNGs, `reelcut words …`
       │            │
       └─writes──► edl.json ──plan validate──► build/timeline.json (frame-accurate, output time)
                                     │
                   music ──► build/music.wav + build/music.json (+ beats)
                                     │
              render: assemble (ffmpeg cuts + 30 ms audio fades) ──► build/assembled.mp4
                      compose  (Remotion: reframe, zooms, B-roll, captions) ──► build/composed_<fmt>.mp4
                      mix      (ffmpeg: duck music under voice, two-pass loudnorm, video copy)
                                     │
                                     ▼
                     preview/<fmt>.mp4  or  final/<slug>_<fmt>.mp4
                                     │
                   check ──► check/report.md + check/cuts.png (re-transcribe & diff, loudness,
                                                              black/freeze, duration, overlaps)
```

### 3.3 Technology choices

| Concern | Choice | Notes |
|---|---|---|
| Orchestrator and CLI | Python 3.12, `uv`, Typer, Pydantic v2, Rich | Install as a tool: `uv tool install …` |
| Media I/O | FFmpeg ≥ 7 (Homebrew) + ffprobe | **VERIFY** filters: `zscale`, `tonemap`, `loudnorm`, `sidechaincompress`, `ebur128`, `blackdetect`, `freezedetect`, `arnndn` |
| Speech activity | Silero VAD (ONNX via onnxruntime) | Keep torch out of the core if packaging allows. **VERIFY** current packaging. |
| ASR (Apple) | `mlx-whisper` with a large-v3-turbo MLX model, word timestamps, language detection | Default on arm64 macOS |
| ASR (portable) | `faster-whisper`, word timestamps | Default elsewhere |
| ASR (optional) | `parakeet-mlx` (Parakeet TDT 0.6B v3: EN + IT supported) | Optional backend; **VERIFY** model support and timestamp API |
| Verbatim fillers (optional) | CrisperWhisper via `transformers` | Off by default (licence, §2.6) |
| Audio cleanup | DeepFilterNet 3 (`deep-filter` binary or `deepfilternet` pip); fallback FFmpeg `arnndn` | **VERIFY** an arm64 macOS binary is available |
| Shots | PySceneDetect | |
| Static/motion | OpenCV frame differencing at low fps | |
| Faces | MediaPipe Tasks `FaceDetector` (BlazeFace); fallback OpenCV YuNet | Models cached in `~/.cache/reelcut/models` |
| Retake similarity | `rapidfuzz` (token-set ratio) | Optional embeddings later |
| Beats | `librosa` | |
| Composition | Remotion v4 (React/TypeScript) + `@remotion/captions` | Rendered via its CLI with `--props` and `--public-dir`. **VERIFY** flags. |
| Music generation | ACE-Step 1.5 in an **isolated** env under `~/.cache/reelcut/envs/ace-step` | Called through a worker subprocess |
| Contact sheets | Pillow + numpy | |
| Tests | pytest (+ vitest for the renderer), ruff, pyright, biome or eslint+prettier, tsc | |

---

## 4. Repository layout (the open-source project)

```
reelcut/                               # repo root
├── README.md                          # what/why, 60-second quickstart, demo GIF placeholder, licences
├── LICENSE                            # MIT
├── THIRD_PARTY.md                     # Remotion, ACE-Step, Whisper models, MediaPipe, CrisperWhisper…
├── CONTRIBUTING.md
├── CHANGELOG.md
├── ROADMAP.md
├── BUILD_LOG.md                       # created by the building agent
├── AGENTS.md                          # for agents *developing* reelcut (not editing videos)
├── CLAUDE.md                          # one line: @AGENTS.md
├── pyproject.toml                     # uv project; extras: mac, cpu, crisper; console script `reelcut`
├── uv.lock
├── justfile                           # dev tasks: lint, test, schema, fixtures, e2e
├── .github/workflows/ci.yml           # Linux: lint, type-check, unit tests, schema freshness, renderer tsc/vitest
├── .pre-commit-config.yaml
├── docs/
│   ├── architecture.md
│   ├── cli.md                         # generated + hand-edited reference
│   ├── edl.md                         # EDL authoring reference (human + agent)
│   ├── dependencies.md                # verified versions & install notes
│   ├── agents.md                      # how to use with Claude Code, Codex, Gemini CLI, Cursor
│   ├── adding-a-language.md
│   └── renaming.md
├── schemas/                           # GENERATED from Pydantic — do not edit by hand
│   ├── analysis.schema.json
│   ├── edl.schema.json
│   ├── timeline.schema.json
│   └── config.schema.json
├── src/reelcut/
│   ├── __init__.py                    # APP_NAME, __version__
│   ├── cli/                           # Typer app, one module per command group
│   ├── config.py                      # reelcut.toml + project.toml loading, defaults, validation
│   ├── paths.py                       # workspace/project path helpers, cache dirs
│   ├── state.py                       # state.json, stage hashing/caching, locking
│   ├── media/                         # ffprobe wrapper, normalise, audio extract, ffmpeg runner
│   ├── audio/                         # enhance (DeepFilterNet / arnndn), loudness, ducking, mix
│   ├── asr/                           # backend protocol + mlx_whisper, faster_whisper, parakeet, crisper
│   ├── analysis/                      # vad, fillers, pauses, utterances, retakes, shots, motion, faces, assets, pack
│   ├── look/                          # contact sheets (filmstrip + waveform + word labels)
│   ├── edl/                           # models.py (Pydantic), refs.py, draft.py, resolve.py, validate.py, summary.py
│   ├── music/                         # acestep worker client, library picker, beats
│   ├── render/                        # assemble.py (ffmpeg), compose.py (Remotion runner), mix.py, presets.py
│   ├── check/                         # retranscribe diff, stills, loudness, black/freeze, report
│   ├── agents/                        # `reelcut agents sync`: install skills into agent-specific dirs
│   ├── lang/                          # en.toml, it.toml (fillers, prompts, caption rules)
│   └── templates/
│       ├── workspace/                 # files copied by `reelcut init`
│       └── skills/                    # canonical SKILL.md sources (see §9)
├── renderer/                          # Remotion project (TypeScript)
│   ├── package.json                   # name: reelcut-renderer; pinned remotion versions
│   ├── tsconfig.json
│   ├── remotion.config.ts
│   └── src/
│       ├── index.ts                   # registerRoot
│       ├── Root.tsx                   # <Composition id="Reel" calculateMetadata=…>
│       ├── Reel.tsx
│       ├── types.gen.ts               # GENERATED from schemas/timeline.schema.json
│       ├── layers/{BaseVideo,Broll,Titles,Captions}.tsx
│       └── lib/{easing,camera,safezones,fonts}.ts
├── scripts/
│   ├── gen_schemas.py                 # Pydantic → JSON Schema → TS types
│   └── make_fixtures.sh               # synthetic EN/IT test clips via macOS `say` + ffmpeg
└── tests/
    ├── unit/                          # refs, resolver, remap, fillers, utterances, retakes, summary, config
    ├── integration/                   # ingest/analyze/render on fixtures (marked: slow, mac)
    └── fixtures/                      # tiny generated media (gitignored if large) + golden JSON
```

---

## 5. Workspace and project layout (the user's side)

Raw footage never lives in the tool repo. `reelcut init ~/Videos/reels` creates a **workspace**:

```
reels/                                 # workspace (the agent is opened here)
├── AGENTS.md                          # how to edit videos with reelcut (template, §9.1)
├── CLAUDE.md                          # @AGENTS.md
├── reelcut.toml                       # workspace config (brand, captions, formats, review gates, models)
├── .claude/skills/…  .agents/skills/… # synced by `reelcut agents sync` (VERIFY each agent's skill path)
├── library/
│   ├── music/                         # optional licensed tracks + tags.json
│   └── brand/                         # logo.png, fonts/, (colors live in reelcut.toml)
└── projects/
    └── <slug>/
        ├── project.toml               # title, language override, formats, target duration, clip roles
        ├── raw/                       # user's files: takes, images, b-roll (never modified)
        ├── media/                     # normalised mezzanines + enhanced audio (cache)
        ├── analysis/                  # <clip>.json, packed.md, assets.md, retakes.json
        ├── contact/                   # `look` PNGs
        ├── edl.json                   # THE creative artefact (agent-written)
        ├── build/                     # timeline.json, assembled.mp4, composed_*.mp4, music.*, public/
        ├── preview/                   # low-res renders
        ├── check/                     # report.md, cuts.png
        ├── final/                     # deliverables
        ├── notes.md                   # agent's session memory: decisions, user feedback, lessons
        └── state.json                 # stage status + input hashes (machine-managed)
```

Clip IDs: every file in `raw/` gets a stable short ID at ingest (`c1, c2…` for A-roll candidates, `b1, b2…` for B-roll video, `i1, i2…` for images), recorded in `project.toml` under `[clips]` with its role. Roles are auto-classified (speech ratio + face presence ⇒ `aroll`; video without significant speech ⇒ `broll`; image ⇒ `image`). The agent or user may override roles in `project.toml`; ingest must respect overrides.

### 5.1 `reelcut.toml` (workspace defaults; every key overridable in `project.toml`)

```toml
[defaults]
formats = ["9x16"]            # any of 9x16, 16x9, 4x5
fps = 30
max_duration_s = 60
language = "auto"             # auto | en | it

[review]                       # optional gates; default fully autonomous
plan = false
preview = false

[asr]
backend = "auto"              # auto → mlx-whisper on Apple Silicon, faster-whisper elsewhere
model = "auto"
fillers_backend = "prompted"  # prompted (default) | crisper (optional, non-commercial licence)

[edit]
pad_in_ms = 80
pad_out_ms = 120
max_pause_ms = 350
min_segment_ms = 400
drop_fillers = "hard"          # none | hard | hard+soft
jumpcut_punch = true
jumpcut_punch_scale = 1.08
look_budget = 8                # max contact sheets per project unless the user asks for more

[captions]
enabled = true
style = "pop"                  # pop | clean | karaoke
font = "Inter"                 # or path in library/brand/fonts
max_words_per_page = 3
uppercase = false
highlight_color = "#FFD400"
text_color = "#FFFFFF"
stroke_color = "#000000"

[music]
mode = "generate"              # generate | library | none
gain_db = -20                  # bed level before ducking
duck_threshold = 0.03
duck_ratio = 8

[master]
integrated_lufs = -14
true_peak_db = -1.5
lra = 11

[brand]
primary = "#111111"
accent = "#FFD400"
logo = "library/brand/logo.png"
```

`config.schema.json` is generated from the Pydantic config model; `reelcut config show <slug>` prints the effective merged config.

---

## 6. Data contracts

Define all of these as Pydantic models in `src/reelcut/…/models.py`, generate JSON Schemas into `schemas/`, and generate `renderer/src/types.gen.ts` from `timeline.schema.json` (use `json-schema-to-typescript` or `datamodel-code-generator`; **VERIFY**). Add a CI check that regenerates and fails on diff.

### 6.1 `analysis/<clip>.json`

```jsonc
{
  "schema_version": 1,
  "clip": { "id": "c1", "role": "aroll", "source": "raw/IMG_0412.MOV",
            "mezzanine": "media/c1.mp4", "audio": "media/c1.wav",
            "duration_s": 312.4, "fps": 30, "width": 1080, "height": 1920,
            "input_hash": "…" },
  "language": { "code": "it", "confidence": 0.97 },
  "words": [
    { "id": "c1.w0", "text": "Allora", "start": 1.02, "end": 1.38, "conf": 0.91,
      "filler": "soft", "utt": "c1.s0" },
    { "id": "c1.w1", "text": "ehm", "start": 1.52, "end": 1.81, "conf": 0.66,
      "filler": "hard", "utt": "c1.s0" }
  ],
  "utterances": [
    { "id": "c1.s0", "start": 1.02, "end": 6.40, "first_word": "c1.w0", "last_word": "c1.w14",
      "text": "Allora ehm oggi vi faccio vedere…", "complete": true }
  ],
  "pauses": [ { "start": 6.40, "end": 8.10, "dur": 1.70, "after_word": "c1.w14" } ],
  "unaligned_voice": [ { "start": 22.3, "end": 22.7 } ],
  "vad": [ { "start": 1.0, "end": 6.42 } ],
  "shots": [ { "start": 0.0, "end": 312.4 } ],
  "static": [ { "start": 300.1, "end": 312.4 } ],
  "faces": { "sample_fps": 2, "samples": [ { "t": 1.0, "cx": 0.51, "cy": 0.38, "w": 0.31, "h": 0.22, "score": 0.97 } ] }
}
```

Rules:
- Word IDs are `<clip>.w<index>`, zero-based, stable for a given transcript.
- **Utterances** are split at pauses ≥ `utterance_gap_ms` (default 500) or sentence-final punctuation. `complete` is false if the utterance ends mid-sentence (no final punctuation and followed by a long pause or the clip end), which hints at an abandoned take.
- `filler`: `null | "hard" | "soft"`, from the language lexicon (§6.2).
- `unaligned_voice`: VAD speech regions ≥ 150 ms that overlap no transcribed word. These are likely fillers, breaths or mumbles Whisper skipped.
- Coordinates in `faces` are normalised 0–1 relative to the mezzanine frame.

### 6.2 Filler detection (default pipeline, language-aware)

Whisper tends to omit disfluencies. The default `prompted` pipeline works around this without CrisperWhisper:

1. Detect the clip language with the ASR backend's language ID (first 30 s of detected speech).
2. Transcribe with word timestamps and an **initial prompt** from the language file that contains fillers, which biases the model towards verbatim output:
   - `en`: `"Umm, so, uh, I was like, hmm, thinking... you know, um, yeah."`
   - `it`: `"Ehm, allora, cioè, eh, stavo tipo pensando... mmm, diciamo, ehm, sì."`
   Use the backend's hallucination guards (e.g. `hallucination_silence_threshold`, `condition_on_previous_text=False`; **VERIFY** what each backend supports). Transcribe only VAD speech regions if a backend hallucinates in silence.
3. Tag words using the lexicon:
   - `en.toml` hard: `um, umm, uh, uhm, er, erm, hmm, mm, mhm`; soft: `like, you know, I mean, basically, actually, so` (soft only at utterance start), `right, okay` (utterance start).
   - `it.toml` hard: `ehm, ehmm, eh, mmm, mh, uhm, ah` (isolated); soft: `cioè, tipo, diciamo, praticamente, insomma, boh, vabbè, niente`, and `allora, comunque, ok, okay` (soft only at utterance start).
   Match case-insensitively after stripping punctuation; support multi-word soft fillers.
4. Record `unaligned_voice` (above) as acoustic filler candidates.
5. Optional `crisper` backend (off by default; licence warning on first use): when enabled and the language is supported (**VERIFY** CrisperWhisper's language coverage), use its verbatim output for filler words and timing and merge it with the main transcript by time overlap.

**Hard** fillers are dropped by the deterministic draft when `drop_fillers` includes `hard`. **Soft** fillers are only *marked*; the agent decides from context.

### 6.3 `analysis/packed.md` (the agent's primary view)

Goal: an entire project fits in a few thousand tokens. Example:

```markdown
# Project: launch-teaser · language: it (c1, c2) · A-roll 2 clips, 6m12s speech · B-roll 3 · images 2
Legend: {ehm#c1.w1}=hard filler (id) · ~tipo~=soft filler · ‖1.7s‖=pause ≥0.7s · ⟂0.4s=unaligned voice · ✗=incomplete utterance

## c1 · IMG_0412.MOV · 5m12s · 1080x1920 · face centred
c1.s0  [00:01.0–00:06.4] ~Allora~ {ehm#c1.w1} oggi vi faccio vedere come ho costruito Pumpkit in due settimane. ‖1.7s‖
c1.s1  [00:08.1–00:10.9] ✗ Il motivo per cui… ‖3.2s‖
c1.s2  [00:14.1–00:21.0] Il motivo per cui l'ho fatto è semplice: scrivere post mi prendeva tre ore al giorno.
…
## c2 · IMG_0415.MOV · 1m00s · retake of the ending
…
## Retake clusters (similarity ≥ 0.75; newest first)
- R1: c1.s2 (0.91) ≈ c1.s1 ✗  → draft keeps c1.s2
- R2: c2.s3 (0.84) ≈ c1.s18   → draft keeps c2.s3
## Static / no-speech stretches ≥ 2s
- c1 [05:00.1–05:12.4] static, no speech
```

Rules: one line per utterance; show IDs only on utterances and fillers (words are fetched on demand with `reelcut words`); timestamps `MM:SS.s`; mark `✗` incomplete; list retake clusters, with the draft's choice, at the end.

`analysis/assets.md` lists each B-roll clip and image: ID, file, duration and resolution, shot count, a one-line description **left blank for the agent to fill in** after viewing its contact sheet, and the path of an auto-generated thumbnail sheet in `contact/`.

### 6.4 `edl.json` (written by the agent)

```jsonc
{
  "schema_version": 1,
  "title": "Come ho costruito Pumpkit in 2 settimane",
  "language": "it",
  "formats": ["9x16", "16x9"],
  "max_duration_s": 60,
  "policy": { "pad_in_ms": 80, "pad_out_ms": 120, "max_pause_ms": 350,
              "drop_fillers": "hard", "jumpcut_punch": true },
  "segments": [
    { "id": "hook", "from": "c1.s2", "to": "c1.s2", "note": "pain-point hook" },
    { "id": "body1", "from": "c1.s0", "to": "c1.w9", "note": "skip 'Allora ehm'" },
    { "id": "body2", "from": "c1.s5", "to": "c1.s12" },
    { "id": "cta", "from": "c2.s3", "to": "c2.s3" }
  ],
  "drop_words": ["c1.w233"],
  "drop_ranges": [ { "clip": "c1", "start": 22.3, "end": 22.7 } ],
  "keep_words": [],
  "events": [
    { "type": "zoom", "at": "c1.w52", "scale": 1.18, "hold_until": "c1.w58", "ease": "snap" },
    { "type": "push", "from": "body2", "scale": 1.06 },
    { "type": "broll", "asset": "b1", "start": "c1.w70", "end": "c1.w84",
      "asset_in_s": 2.0, "mode": "full" },
    { "type": "image", "asset": "i1", "start": "c1.w90", "end": "c1.w97", "mode": "pip",
      "motion": "kenburns" },
    { "type": "title", "text": "3 ore → 10 minuti", "start": "c1.w101", "end": "c1.w110" },
    { "type": "emphasis", "words": ["c1.w103", "c1.w106"] }
  ],
  "captions": { "enabled": true, "style": "pop" },
  "music": { "mode": "generate",
             "prompt": "upbeat minimal electronic, warm synths, confident, instrumental",
             "bpm": 104, "seed": 7, "gain_db": -20 },
  "rationale": "Hook = strongest pain point; removed the abandoned first take and the tangent about pricing; CTA from the cleaner c2 retake."
}
```

**Reference semantics** (implement in `edl/refs.py`, with exhaustive tests):
- `c1.s4` used as `from` means the first word of utterance s4; used as `to` it means the last word of s4.
- `c1.w52` means that exact word. In `from` it includes that word; in `to` it includes that word.
- `from` and `to` must be in the same clip and `from` ≤ `to`.
- Segment order in the array **is** output order, so moving the hook to the front is just a reordering.
- Event anchors (`at`, `start`, `end`, `hold_until`) may be word IDs, utterance IDs or segment IDs (`from: "body2"` = start of that segment). They resolve to **output time**. Anchoring to a dropped word is a validation error with a helpful message that suggests the nearest kept word.
- `drop_words` splits segments around those words; `keep_words` overrides automatic filler dropping.
- `drop_ranges` uses explicit source times (for `unaligned_voice` and similar).

### 6.5 Resolver rules (`edl/resolve.py`)

For each segment:
1. Collect the kept words in `[from, to]`, minus dropped words and words inside `drop_ranges`, minus hard fillers if the policy says so (unless they are in `keep_words`).
2. Split into **runs** wherever a word was removed **or** the source gap between consecutive kept words exceeds `max_pause_ms`. (A long internal pause is tightened by cutting it down to `max_pause_ms`, split evenly around the cut.)
3. Run boundaries: `start = first.start − pad_in`, `end = last.end + pad_out`, clamped so a run never extends past the midpoint between its edge word and the adjacent *removed* word (this prevents clipping neighbours) and never beyond the clip.
4. Merge runs whose source gap is < 150 ms. Drop runs shorter than `min_segment_ms` **with a warning** (never silently).
5. Snap all times to the frame grid (`fps`).
6. Build the output timeline: run k starts at `O_k = Σ len(runs < k)`. Remap every kept word to output time `O_k + (t − run.src_start)`.
7. **Jump-cut punch:** when `jumpcut_punch` is on, consecutive runs from the same clip with a source discontinuity alternate scale between 1.0 and `jumpcut_punch_scale` (hides jump cuts). Explicit zoom events override.
8. **Reframing:** for each run, compute the median face centre of face samples within the run (or within each shot inside the run). No face means centre. This gives a static crop per run. Do not smooth across cuts.
9. Resolve events to output frames; check overlaps (two full-frame B-rolls overlapping = error; title over B-roll = warning).
10. Beats: if music exists, snap B-roll and image *start* times to the nearest beat within ±80 ms. **Never move speech cuts to match beats.**

Output: `build/timeline.json` (the Remotion props): `fps`, per-format `width/height`, `duration_frames`, `runs[]` (source clip, src in/out, out in/out frames, crop centre, base scale), `words[]` in output time (text, start/end ms, emphasis flag), `events[]` in frames, caption settings, brand, music path, and per-format safe zones.

### 6.6 `validate` summary (what the agent sees)

`reelcut plan validate <slug>` prints something like:

```
✓ edl.json valid · language it · 4 segments → 11 runs
Duration 52.4s (limit 60s) · words kept 141/318 · hard fillers removed 9 · pauses tightened 14
Hook (first 3s): "Il motivo per cui l'ho fatto è semplice: scrivere post mi prendeva tre ore…"
Events: 2 zoom · 1 push · 1 broll · 1 image · 1 title · emphasis 2
⚠ run 7 is 0.38s (< min 0.40s) — dropped. Extend body2 or remove c1.w233 from drop_words.
⚠ title overlaps broll b1 by 0.4s.
→ build/timeline.json
```

`--json` returns the same as structured data.

---

## 7. CLI specification

All commands: `--json` for machine output; exit codes `0` OK, `1` user/EDL error (fixable by the agent), `2` environment error (missing dependency), `3` internal error. Long operations show a Rich progress bar on TTY and stay quiet otherwise. Every command that writes files prints the paths it wrote.

| Command | Purpose |
|---|---|
| `reelcut doctor [--fix]` | Check ffmpeg (+ required filters), node/npm, renderer installed, Python extras, models cached, ACE-Step env, free disk and RAM. `--fix` runs safe installs (renderer `npm ci`, model downloads). |
| `reelcut setup [--music] [--crisper]` | One-time: install the renderer into `~/.cache/reelcut/renderer/<version>/`, download ASR, VAD and face models, and optionally create the ACE-Step env and download weights (prints the licence). |
| `reelcut init <dir>` | Create a workspace from the template; runs `agents sync`. |
| `reelcut agents sync [--targets claude,codex,gemini,cursor]` | Copy (or symlink) the canonical skills into each agent's expected directory in the workspace. **VERIFY** current paths in each agent's docs and record them in `docs/agents.md`. |
| `reelcut new <slug> [--from <files/dirs>…] [--title …]` | Create a project; copy or hard-link files into `raw/`. |
| `reelcut ingest <slug>` | Probe, assign IDs and roles, normalise to a mezzanine, extract and enhance audio. |
| `reelcut analyze <slug> [--clip c1]` | Run all analysers and write `analysis/*`, `packed.md`, `assets.md` and asset contact sheets. |
| `reelcut words <slug> <ref-from> [<ref-to>]` | Print words with IDs and times for a range (e.g. `c1.s4 c1.s6`). |
| `reelcut look <slug> <clip> <t0> <t1> [--frames 8] [--out …]` | Contact sheet: filmstrip + waveform + word labels + face boxes. Prints the PNG path. Counts against `look_budget` (counter in `state.json`; warn but don't block when exceeded). |
| `reelcut look-asset <slug> <asset-id>` | Contact sheet for a B-roll clip or image. |
| `reelcut plan draft <slug> [--force]` | Write a deterministic baseline `edl.json` (refuses to overwrite an existing one without `--force`). |
| `reelcut plan validate <slug>` | Validate and resolve → `build/timeline.json` + summary (§6.6). |
| `reelcut music <slug>` | Generate or pick music per the EDL → `build/music.wav`, `music.json` (prompt, seed, model, licence, bpm, beats). |
| `reelcut render <slug> [--preview\|--final] [--format 9x16]` | assemble → compose → mix. Preview = half resolution, fast encode, into `preview/`. Final = full resolution, into `final/`. |
| `reelcut check <slug> [--preview\|--final]` | QA → `check/report.md`, `check/cuts.png`; non-zero exit if blocking issues. |
| `reelcut status <slug>` | Stage table, stale stages, next suggested command. |
| `reelcut config show <slug>` | Effective config. |
| `reelcut clean <slug> [--all]` | Delete caches (`media/`, `build/`, `preview/`); never touch `raw/`, `edl.json`, `notes.md`, `final/` unless `--all` and confirmed. |

---

## 8. Build phases

### Phase 0 — Environment and ground rules
Tasks:
- Check the machine: `uname -m`, macOS version, RAM (`sysctl hw.memsize`), free disk. Log them.
- Ensure Homebrew packages: `ffmpeg`, `node` (LTS ≥ 20), `uv`, `just`, `git`. Install missing ones with `brew install …` (ask the human only if `brew` itself is missing).
- **VERIFY** that ffmpeg has the filters in §3.3 (`ffmpeg -hide_banner -filters | grep …`). If `zscale` is missing, plan the HDR tonemap fallback (§8 Phase 3).
- `git init`, create `BUILD_LOG.md`, and create the task list.

Acceptance: the tool versions are logged; all required filters are present or a fallback is noted.

### Phase 1 — Repository scaffold and tooling
Tasks:
- Create the layout in §4 (empty modules with docstrings are fine).
- `pyproject.toml`: Python `>=3.12,<3.14`; console script `reelcut = "reelcut.cli:app"`; extras:
  - `mac`: `mlx-whisper` (marker `sys_platform == 'darwin' and platform_machine == 'arm64'`), optionally `parakeet-mlx`
  - `cpu`: `faster-whisper`
  - `crisper`: `transformers`, `torch` (optional)
  - core: `typer`, `rich`, `pydantic>=2`, `tomli-w`, `numpy`, `opencv-python-headless`, `scenedetect`, `mediapipe`, `onnxruntime`, `rapidfuzz`, `librosa`, `soundfile`, `pillow`, `platformdirs`
  - **VERIFY** wheel availability for macOS arm64 + Python 3.12 for every dependency before pinning.
- Dev tooling: ruff (lint + format), pyright (strict on `edl/` and `analysis/`), pytest with markers `slow`, `mac`, `models`, `renderer`, `music`; pre-commit.
- `renderer/`: initialise a minimal Remotion v4 project with TypeScript (**VERIFY** the current scaffold command and versions; pin exact versions; keep all `remotion` and `@remotion/*` packages on the same version).
- CI workflow (Linux): `uv sync --extra cpu`, ruff, pyright, `pytest -m "not slow and not mac and not models and not music"`, schema freshness check, `npm ci && tsc --noEmit && vitest run` in `renderer/`.
- LICENSE (MIT), README skeleton, CONTRIBUTING, CHANGELOG, ROADMAP, THIRD_PARTY skeleton, repo `AGENTS.md` (for developers: how to run tests and the coding rules in §3.1) and `CLAUDE.md` containing `@AGENTS.md`.

Acceptance: `just lint` and `just test` pass on the empty scaffold; `reelcut --help` works after `uv tool install --editable .`.

### Phase 2 — Core: config, paths, state, CLI skeleton
Tasks:
- `config.py`: Pydantic models for `reelcut.toml` and `project.toml` with the defaults in §5.1; merging order: built-in defaults < workspace < project < EDL policy.
- `paths.py`: find the workspace root by walking up to `reelcut.toml`; project paths; cache dirs via `platformdirs` (`~/.cache/reelcut` on macOS should be acceptable; log the choice).
- `state.py`: `state.json` with per-stage `{status, input_hash, outputs, finished_at}`; helpers `stage_is_fresh(stage, inputs)` and `mark_done`; a file lock to prevent concurrent runs.
- A `ffmpeg.py` runner: builds argument lists (never shell strings), captures stderr, raises typed errors with the last 20 stderr lines, and supports progress parsing.
- Commands: `doctor`, `init` (copy `templates/workspace`), `new`, `status`, `config show`, `clean`.
- `scripts/gen_schemas.py` + `just schema`.

Acceptance: unit tests for config merging, workspace discovery and state freshness; `reelcut init /tmp/ws && reelcut new demo` creates the expected tree.

### Phase 3 — Ingest
Tasks:
- Probe each file in `raw/` with `ffprobe -show_streams -show_format -of json`. Classify: image (by extension or codec), video (with or without audio).
- Assign IDs (`c*`, `b*`, `i*`) and record them in `project.toml` (preserve user overrides and existing IDs; never renumber existing clips).
- Normalise each video to a mezzanine `media/<id>.mp4`:
  - apply rotation metadata;
  - **constant frame rate** at project fps (phones record VFR) — use `fps=` filter + `-fps_mode cfr` (**VERIFY** flag name for the installed ffmpeg);
  - **HDR → SDR**: if `color_transfer` is `arib-std-b67` (HLG) or `smpte2084` (PQ), tonemap to BT.709 (zscale+tonemap chain; if `zscale` is unavailable, use a documented fallback and warn);
  - cap the long side at 3840 px; H.264 High, CRF 14–16, `-preset fast`, short GOP (`-g` = 1 s) for fast seeking, `yuv420p`, `+faststart`;
  - audio: copy to the side; the mezzanine keeps the original audio only for reference.
- Audio: extract 48 kHz mono WAV → enhance with DeepFilterNet (or `arnndn` fallback) → high-pass ~80 Hz → `media/<id>.wav`. Also write a 16 kHz mono copy for ASR and VAD.
- Images: copy to `media/` normalised (EXIF orientation applied, max 4096 px, sRGB PNG/JPEG).
- Role classification needs speech and face data, so assign a provisional role at ingest and finalise it after the VAD and face passes in Phase 4.

Acceptance: integration test on the fixtures (Phase 11 makes them; create a minimal one now with ffmpeg `testsrc2` + `sine`): mezzanines are CFR, SDR, right fps and duration within one frame; re-running ingest is a no-op.

### Phase 4 — Analysis
Implement each analyser as a pure function `(inputs) -> model` with a thin CLI wrapper, so each can be tested in isolation.

1. **VAD** (Silero ONNX): speech regions with min speech 250 ms and min silence 100 ms (configurable).
2. **ASR backends** behind a `Protocol`:
   ```python
   class ASRBackend(Protocol):
       name: str
       def detect_language(self, wav16k: Path, regions: list[Span]) -> LangGuess: ...
       def transcribe(self, wav16k: Path, language: str, initial_prompt: str | None,
                      regions: list[Span] | None) -> list[Word]: ...
   ```
   - `mlx_whisper` (default on Apple Silicon): **VERIFY** the API for `word_timestamps`, `initial_prompt`, language detection and hallucination guards, and the best available turbo or large-v3 MLX model id.
   - `faster_whisper` (portable default): `word_timestamps=True`, `vad_filter` off (we provide regions) — **VERIFY**.
   - `parakeet_mlx` (optional): **VERIFY** EN/IT support, timestamp granularity and language handling.
   - `crisper` (optional, off by default, licence warning).
   Run ASR in a **subprocess** so memory is released afterwards.
3. **Fillers** per §6.2, using `lang/<code>.toml`.
4. **Utterances, pauses, unaligned voice, completeness** per §6.1.
5. **Retakes**: compare utterances within and across A-roll clips with `rapidfuzz.fuzz.token_set_ratio` on normalised text (lowercased, punctuation and fillers removed). Cluster with threshold 0.75 using union-find. Within a cluster, prefer `complete` utterances, then the newest (later in the clip, then later clip index), then fewest fillers. Write `retakes.json`.
6. **Shots**: PySceneDetect `ContentDetector` on a downscaled stream.
7. **Static**: OpenCV mean absolute frame difference at 2 fps on 320 px frames; stretches ≥ 2 s below threshold that also have no VAD speech → `static`.
8. **Faces**: MediaPipe Tasks FaceDetector at 2 fps (largest face per frame), normalised boxes; fallback YuNet. Download models into the cache in `setup` (**VERIFY** model URLs and the current MediaPipe Tasks Python API).
9. **Role finalisation**: speech ratio > 0.3 and face present in > 50% of samples ⇒ `aroll`.
10. **Packers**: `packed.md` (§6.3) and `assets.md`, plus one thumbnail sheet per asset in `contact/`.

Acceptance:
- Unit tests: filler tagging (EN and IT, including start-only soft fillers and multi-word ones), utterance splitting, completeness, pause extraction, retake clustering choice order, packed formatting (golden file).
- Integration (marked `mac`, `models`) on the EN and IT fixtures: language detected correctly; ≥ 90% of known inserted silences found within ±150 ms; known retake pair clustered; `packed.md` under 2,500 tokens for a 5-minute fixture (estimate tokens as chars/4).

### Phase 5 — Visual inspection (`look`, `look-asset`)
Tasks:
- Extract N frames evenly in `[t0, t1]` (ffmpeg `-ss` before `-i` for speed, per frame) at 320 px tall.
- Compose a sheet with Pillow: a filmstrip row with a timestamp under each frame; below it a waveform of the range (numpy from the 16 kHz WAV) with VAD regions shaded, pause regions hatched, and word labels positioned by time (fillers in red, soft fillers in orange); draw face boxes on frames.
- Output ≤ 1600 px wide PNG; print the path and a one-line description.
- Budget counter as in §7.

Acceptance: golden-image smoke test (dimensions and non-empty); manual look at one sheet by you, the building agent (open the PNG and confirm the labels are legible). Log that you did this.

### Phase 6 — EDL: models, refs, draft, resolver, validate (the heart; test heavily)
Tasks:
- Pydantic models for the EDL (§6.4) and timeline (§6.5) with clear field docs (they become schema descriptions the agent reads).
- `refs.py`: parse and resolve references; helpful errors ("`c1.s40` does not exist; c1 has s0–s37").
- `draft.py`: baseline EDL. Include all A-roll utterances in source order, skipping non-chosen members of retake clusters and incomplete utterances that have a complete retake; hard fillers dropped via policy; no events except jump-cut punch (policy); music `generate` with a neutral prompt derived from language and pace (words per second → bpm band: < 2.3 → 85–95, 2.3–3 → 96–110, > 3 → 112–124); `rationale: "deterministic draft"`.
- `resolve.py`: §6.5 exactly. Pure functions, no I/O except the final write.
- `validate.py` + `summary.py`: §6.6 output; warnings vs errors; `--json`.
- Property-based tests (Hypothesis) for the resolver: output runs never overlap; total duration = sum of runs; every kept word's output interval lies within its run; no run crosses a removed word; times are frame-aligned; reordering segments reorders output.

Acceptance: ≥ 95% line coverage on `edl/`; all property tests pass; validating the draft for each fixture succeeds; deliberately broken EDLs (dangling refs, cross-clip ranges, anchors on dropped words, overlapping full-frame B-roll) produce the expected errors.

### Phase 7 — Rendering: assemble, compose, mix
**7a. Assemble (ffmpeg)** — `render/assemble.py`
- Inputs: mezzanines and enhanced WAVs of the A-roll clips used.
- Build one filter graph: for each run, `trim`/`atrim` + `setpts`/`asetpts`, a 30 ms `afade` in and out on audio, then `concat` (video + audio). Write the graph to a file and pass it with the file-based filter-graph option the installed ffmpeg supports (**VERIFY**: newer ffmpeg uses `-/filter_complex <file>`; older uses `-filter_complex_script`).
- Output `build/assembled.mp4` at mezzanine resolution, H.264 CRF 14, audio PCM or AAC 320k at 48 kHz.
- Assert the output duration equals the timeline duration within one frame.

**7b. Compose (Remotion)** — `renderer/` + `render/compose.py`
- `Root.tsx` registers composition `Reel`; `calculateMetadata` sets `width`, `height`, `fps` and `durationInFrames` from props (format chosen via a prop).
- `compose.py` writes `build/props_<fmt>.json` (timeline + format), places or hard-links `assembled.mp4`, B-roll mezzanines, images, fonts and the logo into `build/public/`, and runs the Remotion CLI render with `--props`, `--public-dir build/public`, `--scale 0.5` for previews, a sensible `--concurrency` (default 4 on 16 GB), CRF ~16 for finals (**VERIFY** all flag names for the pinned version). It finds the renderer in `~/.cache/reelcut/renderer/<version>/` (installed by `setup`) or uses the repo's `renderer/` in dev mode.
- Layers:
  - **BaseVideo**: `<OffthreadVideo src={staticFile("assembled.mp4")}>`. The camera transform per frame comes from `lib/camera.ts`: cover-fit to the target aspect ratio, translate so the run's face centre sits at x = 0.5 and y ≈ 0.4 (clamped so no empty edges), then multiply by the scale from jump-cut punch, zoom events (`snap` = 4-frame spring, `smooth` = ease over 10 frames) and push-ins (linear 1.0 → `scale` across the segment). For `16x9` output from vertical sources, use **fit-blur**: a blurred, scaled-up copy as background with the sharp video centred.
  - **Broll**: `full` (cover-fit cutaway, video muted by default, 6-frame crossfade) or `pip` (rounded card in the upper third with a drop shadow); images support `kenburns` (slow 1.0 → 1.08 scale + slight pan).
  - **Titles**: bold text card in the brand style, spring in and out.
  - **Captions**: build `Caption[]` from the timeline words (`text`, `startMs`, `endMs`, `timestampMs`, `confidence`) and page them with `createTikTokStyleCaptions` from `@remotion/captions` (**VERIFY** the API). Paging respects `max_words_per_page` and a max characters per line (Italian words run longer, so also cap by width measured with `@remotion/layout-utils` if available). The active word gets `highlight_color` + slight scale; `emphasis` words also get the accent colour. Put captions inside format-specific **safe zones** (`lib/safezones.ts`; Reels: keep clear of the bottom ~20% and right ~12% UI areas — approximate values, configurable). Hide captions during `full` B-roll only if configured (default: keep them).
- Fonts: load from `library/brand/fonts` if present, else `@remotion/google-fonts` (Inter by default).
- vitest unit tests for `camera.ts` (clamping, scale composition) and caption paging.

**7c. Mix and master (ffmpeg)** — `render/mix.py` (**VERIFY** each filter option)
- Inputs: `composed_<fmt>.mp4` (voice audio) and `build/music.wav` (trimmed or looped to duration with a 1.5 s fade-out).
- Graph: music `volume=<gain_db>dB` → `sidechaincompress` keyed by the voice (`asplit` the voice for the sidechain) using `duck_threshold` and `duck_ratio`, attack ~10 ms, release ~400 ms → `amix=inputs=2:normalize=0` with the voice.
- Two-pass `loudnorm` at `I=-14:TP=-1.5:LRA=11`: pass 1 with `print_format=json`, pass 2 with the measured values and `linear=true`. Force `-ar 48000`.
- Video stream `-c:v copy`; audio AAC 320k; `+faststart`.
- Music mode `none`: run loudnorm on the voice only.

Acceptance:
- `render --preview` on each fixture produces a playable file per requested format with the expected dimensions and duration (± 1 frame).
- Open three stills from the preview (start, a cut, a zoom) as images and confirm the reframing and captions look right. Log what you saw.
- Integrated loudness of finals is −14 ± 1 LUFS and true peak ≤ −1 dBTP (measured with `ebur128`).

### Phase 8 — Music
Tasks:
- `setup --music`: create an isolated env for ACE-Step 1.5 under `~/.cache/reelcut/envs/ace-step` following the **official repo README** for Apple Silicon (MLX/MPS; **VERIFY**). Download weights and **print and record their licence**. Never install ACE-Step's dependencies into reelcut's own env.
- `music/acestep_worker.py`: a small script run with the ACE-Step env's Python. It reads a JSON job (prompt, duration, bpm, seed, instrumental=true) and writes a WAV + JSON. **VERIFY** how ACE-Step requests instrumental-only output (e.g. an instrumental lyrics tag) and how duration and BPM are specified. Make sure no vocals are generated: if the model has no hard switch, add a check (run the VAD on the result; if a lot of "speech" is detected, regenerate with a new seed, up to 3 tries).
- `music/client.py`: runs the worker as a subprocess with a timeout, then frees memory. Generates `duration = timeline + 3 s`.
- **Library mode**: `library/music/tags.json` entries `{file, title, mood[], bpm, energy 1–5, licence, source_url, attribution}`; pick by mood-tag overlap + bpm distance; refuse entries without `licence`; write attribution into `final/<slug>_credits.txt` when required.
- **Beats**: `librosa.beat.beat_track(..., units="time", trim=False)` → `music.json.beats`; the resolver uses them for snapping (§6.5 step 10).
- Prompt guidance for agents goes in the music skill (§9.5), not in code.

Acceptance: on this Mac, `reelcut music` generates a 60 s instrumental in reasonable time (log the measured time); the vocal check works (unit test with a speech WAV); library mode picks deterministically; `music.json` contains the licence.

### Phase 9 — QA (`check`)
Tasks:
- **Re-transcribe and diff**: transcribe the rendered audio (before music is mixed; keep `build/voice_<fmt>.wav` for this) with the same backend. Align the expected word sequence (timeline words) with the recognised words using `difflib.SequenceMatcher` on normalised tokens. Report missing or garbled words, flag those within 300 ms of a cut as **clipped cut** (blocking), and others as ASR noise (info).
- **Cut stills**: for every cut, extract frames at −0.2 s and +0.2 s and tile them into `check/cuts.png` with cut indices (the agent looks at this single image).
- **Loudness**: `ebur128=peak=true` → integrated LUFS, true peak, LRA vs targets.
- **Black and frozen frames**: `blackdetect`, `freezedetect` (ignore intentional image segments).
- **Duration** vs `max_duration_s`; **caption density** (words per second on screen > 4.5 ⇒ warning); event overlaps (re-run from the timeline).
- `check/report.md`: a short verdict line, then blocking issues with exact fix suggestions in EDL terms (e.g. "clipped 'semplice' at cut 4 → increase pad_out for body1 or include c1.w58"), then warnings and metrics. Exit 1 if blocking.

Acceptance: deliberately bad renders (zero padding, which clips words; an EDL longer than the limit) produce the right blocking issues; a good render passes.

### Phase 10 — Agent layer
Tasks:
- Write the canonical skills in `src/reelcut/templates/skills/` using the texts in §9 (refine wording, keep the structure). Each skill is a folder with `SKILL.md` (YAML frontmatter `name`, `description`) and optional `reference/*.md`.
- Workspace template `AGENTS.md` (§9.1) + `CLAUDE.md` = `@AGENTS.md` + default `reelcut.toml` + `library/` skeleton with a README explaining music licensing.
- `reelcut agents sync`: copy skills into the workspace for each target agent. **VERIFY** current skill-discovery paths for Claude Code (project `.claude/skills/`), Codex, Gemini CLI and Cursor from their official docs; where an agent has no skills support, `AGENTS.md` alone must be enough (it links to the skill files by path so any agent can read them). Record findings in `docs/agents.md`.
- Optional: Claude Code plugin packaging (`.claude-plugin/plugin.json` + marketplace manifest) exposing the skills. **VERIFY** the current plugin format; if uncertain, put this in `ROADMAP.md` instead.

Acceptance: `reelcut init` produces a workspace in which a fresh agent session, given only "edit projects/demo into a Reel", can find and follow the workflow (tested in Phase 13).

### Phase 11 — Fixtures and end-to-end tests
Tasks:
- `scripts/make_fixtures.sh` (macOS) generates, from scratch and without copyrighted media:
  - **EN talking clip**: speech with macOS `say` (an English voice) containing known silences (embedded `[[slnc 1500]]` commands; **VERIFY** the syntax), a spoken "um", and a repeated sentence (retake) where the first attempt is cut off. Video: a synthetic "presenter" (e.g. ffmpeg `testsrc2` or a coloured background with a moving circle) at 1080×1920, 30 fps, **variable frame rate** remux to exercise CFR normalisation.
  - **IT talking clip**: same with an Italian voice (check available voices with `say -v '?'`) and "ehm".
  - **B-roll**: 6 s of `mandelbrot` or `testsrc2` at 1920×1080. **Image**: a generated PNG.
  - **Ground-truth JSON** for each: silence spans, filler positions, retake pair, language.
- Face fixtures: faces can't be synthesised reliably. Unit-test the face pipeline on a public-domain face photo (record its source and licence in `tests/fixtures/README.md`) or skip with a clear marker.
- `just e2e`: init workspace → new → ingest → analyze → plan draft → validate → music (if available) → render preview (9x16 + 16x9) → check. Assert the ground truth is met within tolerances and `check` passes.

Acceptance: `just e2e` passes on this Mac for EN and IT; the run time is logged.

### Phase 12 — Documentation and open-source readiness
Tasks:
- README: one-paragraph pitch; how it works (the pipeline diagram); requirements; quickstart (`uv tool install …`, `reelcut setup --music`, `reelcut init`, open your agent and ask); supported agents; configuration; **licences (Remotion terms, ACE-Step weights, optional CrisperWhisper non-commercial)**; troubleshooting; roadmap link.
- `docs/edl.md`: full EDL reference with examples, generated in part from schema descriptions.
- `docs/cli.md`: every command with examples (generate the base from Typer, then edit).
- `docs/architecture.md`, `docs/adding-a-language.md` (walk through adding `es.toml`), `docs/dependencies.md`, `docs/renaming.md`.
- `THIRD_PARTY.md`: every dependency and model with licence and link.
- Security note in README: skills run shell commands; the harness never uploads media anywhere; there is no telemetry.
- Version `0.1.0`, CHANGELOG entry, git tag `v0.1.0`.

Acceptance: a fresh clone + README quickstart works on this Mac (you, the building agent, do this in a temporary directory and log the result); CI is green on Linux in a local `act` run or by careful review if `act` isn't available (log which).

### Phase 13 — Dogfood with the user's real footage and hand off
Tasks:
- Create a workspace at `~/Videos/reels` (or ask the human for the location if that fails) and a project `first-test`. If `raw/` is empty, stop and ask the human to drop in 2–5 real talking-head takes, optionally with an image and a B-roll clip.
- Run the whole workflow **as an editing agent would**, following only the workspace `AGENTS.md` and skills (start a fresh mental context: re-read them, don't rely on build knowledge). Produce `final/first-test_9x16.mp4` and `final/first-test_16x9.mp4`.
- Fix any friction you hit in the skills, CLI output or docs (that is the point of this phase), then re-run.
- Write `HANDOFF.md`: what was built, how to use it day to day, measured timings (ingest, analysis, music, render per minute of footage), known limitations, licence caveats, and the top 5 roadmap items.

Acceptance: both finals exist and pass `check`; `HANDOFF.md` is written; all tasks are ticked.

---

## 9. Agent-facing content (templates)

These are the texts for the workspace template and skills. Keep them concise; agents read them every session. Use them as written, refining only where the implementation forces a change.

### 9.1 Workspace `AGENTS.md`

```markdown
# Video editing workspace (reelcut)

You are the editor. `reelcut` is your toolchain: it turns footage into text you can read, and renders the edit you describe in `edl.json`. You never need to write rendering code.

## Golden rules
1. Never modify `projects/*/raw/`. Never delete `final/` or `notes.md`.
2. All creative decisions go in `projects/<slug>/edl.json`. Re-render after editing it.
3. Read `analysis/packed.md` first. Use `reelcut words` for exact word IDs, and `reelcut look` only for decisions that need eyes (budget: `look_budget` sheets per project).
4. Prefer utterance refs (`c1.s4`) for cuts; use word refs (`c1.w52`) for fine trims.
5. Run `reelcut plan validate` after every EDL change and fix all errors before rendering.
6. Always run `reelcut check` after rendering; fix blocking issues before delivering.
7. Review gates: if `[review] plan` or `preview` is true in the config, or the user asked to review, stop at that gate with a short summary and wait.
8. Keep `projects/<slug>/notes.md` updated: decisions, the user's feedback, and lessons for next time.

## Workflow
Follow the skill `reelcut-edit` (in `.claude/skills/` or `.agents/skills/`, or read `skills/reelcut-edit/SKILL.md` directly). The editorial rules are in `reelcut-plan`; visual inspection in `reelcut-look`; music in `reelcut-music`; QA and feedback in `reelcut-review`.

## Quick reference
reelcut status <slug> · ingest · analyze · words · look · look-asset · plan draft · plan validate · music · render --preview|--final [--format] · check · config show
```

### 9.2 Skill `reelcut-edit` (orchestrator)

```markdown
---
name: reelcut-edit
description: End-to-end workflow for editing raw talking-head footage into short social videos (Instagram Reels, X) with reelcut. Use whenever the user asks to edit, cut, trim or produce a video/reel/short from files in a reelcut workspace.
---

# Editing a video with reelcut

## 0. Orient
- `reelcut status <slug>` (create the project with `reelcut new <slug> --from <paths>` if needed).
- Read `projects/<slug>/notes.md` if it exists, and the effective config (`reelcut config show <slug>`).
- Note the user's requests: target length, formats, tone, must-keep lines, CTA.

## 1. Prepare (skip stages that `status` reports as fresh)
- `reelcut ingest <slug>` then `reelcut analyze <slug>`.

## 2. Understand
- Read `analysis/packed.md` in full and `analysis/assets.md`.
- For each B-roll/image asset, view its contact sheet (`reelcut look-asset`) and write a one-line description into `assets.md`.
- Identify: the core message, the strongest hook candidates, retake winners, tangents, the CTA.

## 3. Plan
- `reelcut plan draft <slug>` (unless an `edl.json` already exists from earlier work; then build on it).
- Edit `edl.json` following the `reelcut-plan` skill: choose the hook, order the segments, trim, drop soft fillers where they hurt, add emphasis/zooms/B-roll/titles, set the music prompt, and write a short `rationale`.
- `reelcut plan validate <slug>`; fix errors; resolve warnings unless deliberate.
- GATE (plan): if enabled, present the hook line, duration, structure (one line per segment) and what was cut, then wait.

## 4. Music
- `reelcut music <slug>` (follow `reelcut-music` for the prompt).

## 5. Preview and self-check
- `reelcut render <slug> --preview` (all formats in the EDL).
- `reelcut check <slug> --preview`; view `check/cuts.png`; fix blocking issues by editing the EDL; repeat (max 3 loops, then report what remains).
- GATE (preview): if enabled, give the preview paths plus a 3-line summary and wait for feedback (apply it via `reelcut-review`).

## 6. Final
- `reelcut render <slug> --final` then `reelcut check <slug> --final`.
- Deliver: list the final file paths, duration, hook line, music (generated prompt/seed or track + licence) and anything the user should know.
- Update `notes.md`.
```

### 9.3 Skill `reelcut-plan` (editorial judgement and EDL authoring)

```markdown
---
name: reelcut-plan
description: Editorial rules and EDL authoring reference for reelcut — how to pick hooks, retakes and cuts, pace a talking-head short, and place zooms, B-roll, titles and emphasis. Use when writing or revising edl.json.
---

# Planning the edit

## Priorities (in order)
1. **Hook in the first 2–3 seconds.** Open with the most specific, surprising or painful claim that makes sense on its own (a number, a bold statement, a result, a question). Moving a later line to the front is normal. Never open with greetings, "so", "allora", "today I want to…".
2. **One idea per video.** Cut tangents, repeated explanations and caveats that don't change the message.
3. **Best take wins.** In a retake cluster prefer: complete > fluent (fewer fillers, no restarts) > later take. If two takes are equally clean but differ in energy, view both with one `look` sheet and choose the more expressive delivery.
4. **Pace.** Remove dead air (`max_pause_ms` handles most of it). Keep a natural breath before punchlines. Target 2.5–3.5 words/s overall.
5. **End with a payoff or CTA**, then stop. No outro waffle.
6. **Length.** Respect `max_duration_s`. If over, cut the weakest supporting point, not the hook or payoff.

## Fillers
- Hard fillers (`{ehm#…}`, `{um#…}`) are removed by policy. Keep one only if removing it breaks a natural rhythm (`keep_words`).
- Soft fillers (`~tipo~`, `~like~`, `~cioè~`, `~allora~`) are judgement calls: drop them when they're verbal tics; keep them when they carry meaning ("tipo 3 ore" = "about 3 hours"). Use `reelcut words` to get their IDs.
- `⟂` unaligned voice inside a kept segment is usually a mumble or breath: drop it with `drop_ranges` if it sits inside a sentence.

## Visual rhythm
- Something should change on screen every 2–4 seconds: a cut, a punch-in, B-roll, a title or an image.
- `zoom` (snap, 1.12–1.2) on the key word of a punchline or a number. Use them sparingly: about 1 per 8–10 s.
- `push` (1.04–1.08) on a calm explanatory segment.
- Jump-cut punch is automatic; don't add manual zooms on every cut.
- B-roll/images: cover what is being *described* (product, screen, result). `full` for strong visuals, `pip` when the face matters. 2–5 s each. Anchor start/end to words.
- `title`: short (≤ 5 words), for the core claim or a number transformation ("3h → 10 min").
- `emphasis`: 1–3 words per sentence at most: numbers, contrasts, the key noun.

## Language
- Keep the speaker's language. Titles go in the same language as the speech.
- Italian: watch for soft fillers at utterance starts (allora, cioè, praticamente) and false starts like "il… il motivo".

## Formats
- `9x16` is the main deliverable. `16x9` for X reuses the same EDL (fit-blur for vertical sources). Don't make separate edits unless asked.

## EDL reference
See `docs/edl.md` (installed with reelcut; `reelcut docs edl` prints it). Essentials:
- `segments[]` in output order; `from`/`to` are utterance or word refs in the same clip.
- `drop_words[]`, `keep_words[]`, `drop_ranges[]`.
- `events[]`: zoom, push, broll, image, title, emphasis; anchors are word/utterance/segment refs.
- `music`: mode + prompt + bpm + seed.
- Always fill `rationale` (1–3 sentences).
```

(Implement `reelcut docs edl` so agents can print the reference without knowing where the package is installed.)

### 9.4 Skill `reelcut-look` (visual inspection)

```markdown
---
name: reelcut-look
description: When and how to look at footage with reelcut contact sheets without wasting tokens. Use when a decision depends on what is visible — choosing between takes by delivery, checking framing, describing B-roll, or verifying a cut.
---

# Looking at footage

You cannot watch video. `reelcut look <slug> <clip> <t0> <t1>` gives you one PNG: frames across the range, the waveform, the words with timing, and face boxes. Open the PNG and inspect it.

Use it for:
- comparing two equally clean retakes (one sheet per candidate, 6 frames each);
- checking a `static` stretch ("is anything happening?") before cutting it;
- describing B-roll/images (`look-asset`) — once per asset;
- verifying a suspicious cut flagged by `check` (or view `check/cuts.png`).

Don't use it for: routine cuts (the transcript is enough), every segment, or long ranges (> 20 s; split into the moments that matter).

Budget: `look_budget` sheets per project (default 8). Beyond that, continue only if the decision really needs it, and say so in notes.md.
```

### 9.5 Skill `reelcut-music`

```markdown
---
name: reelcut-music
description: How to choose or generate background music for a reelcut edit — mood prompts for local ACE-Step generation, library picks, BPM and levels. Use when setting the `music` block of edl.json or when the user asks to change the music.
---

# Music

Default: local generation (`mode: "generate"`). It is free, offline and licence-safe per the recorded model licence.

## Writing the prompt
Describe genre, instrumentation, mood and energy; always include "instrumental". Match the *content*, not the topic:
- confident tech/build-in-public: "minimal electronic, warm analog synths, soft punchy drums, confident, optimistic, instrumental"
- storytelling/reflective: "lo-fi piano, gentle vinyl texture, soft brushes, warm, reflective, instrumental"
- high-energy tips/lists: "upbeat indie electronic, plucky synths, driving four-on-the-floor, energetic, instrumental"
- serious/explainer: "ambient cinematic pads, subtle pulse, focused, calm, instrumental"
Avoid busy melodies and vocals: the music sits under speech.

## BPM
Pick from the speech pace (validate's summary shows words/s): < 2.3 w/s → 85–95; 2.3–3 → 96–110; > 3 → 112–124.

## Levels
`gain_db` −20 (calm) to −16 (energetic). Ducking and loudness are automatic.

## Changing music
Change `seed` for a variation of the same vibe; change `prompt` for a different vibe. `mode: "library"` picks from `library/music/tags.json` (only licensed tracks). `mode: "none"` for no music.
Always tell the user what was used (prompt + seed, or track + licence/attribution).
```

### 9.6 Skill `reelcut-review` (QA and feedback)

```markdown
---
name: reelcut-review
description: How to read reelcut check reports and turn user feedback on a preview into precise EDL changes. Use after rendering, when `reelcut check` reports issues, or when the user comments on a preview ("cut the intro", "more zooms", "music too loud").
---

# Review and feedback

## Reading check/report.md
- **Clipped cut** → widen padding locally: extend `to` by one word or set a larger pad via the segment's `pad_out_ms`; or remove the offending ID from `drop_words`.
- **Over length** → remove the weakest supporting segment; keep the hook and payoff.
- **Loudness off target** → report it as a bug if it persists after re-render (mastering is automatic).
- **Black/frozen frames** → check B-roll `asset_in_s` and durations.
- View `check/cuts.png` once per loop; look for faces cut off, captions colliding with titles, awkward mouth-open frames at cuts (shift the cut by one word).

## Translating feedback into the EDL
| User says | Change |
|---|---|
| "start stronger" / "hook is weak" | Pick a different hook utterance; move it first |
| "too slow" | Lower `max_pause_ms` (min 200), drop soft fillers, cut a supporting point |
| "too choppy" | Raise `max_pause_ms` to 450–550, disable `jumpcut_punch`, fewer zooms |
| "more dynamic" | Add zooms on numbers/punchlines, add B-roll or titles every 3–4 s |
| "music too loud" | Lower `gain_db` by 3–4 dB |
| "different music" | New `seed` (same vibe) or new `prompt` |
| "remove X" | Find the utterance in packed.md, then split or exclude it |
Record the feedback and how you applied it in notes.md so it carries over to the next video.
```

---

## 10. Implementation notes and pitfalls

- **Phone footage is VFR and often HDR.** Normalising at ingest (CFR + SDR) prevents audio drift and washed-out colours later. Never cut directly from `raw/`.
- **Whisper word timings drift slightly late or early.** The padding defaults (80/120 ms) and the re-transcribe check exist for this; don't trust single-word cuts without padding.
- **Whisper hallucinates in silence.** Transcribe VAD regions, use hallucination guards, and drop words that fall outside any VAD region.
- **The filler prompt can over-produce fillers.** Only accept filler words that overlap VAD speech and last ≥ 80 ms.
- **Remotion and local files:** the browser renderer can't read arbitrary paths; everything goes through `--public-dir` and `staticFile()`. Hard-link rather than copy big files when on the same volume.
- **Double encoding:** Remotion encodes once (high quality); the mix stage copies video. Never re-encode video in the mix.
- **Memory on 16 GB:** never run ASR, face detection and ACE-Step concurrently; use subprocesses; Remotion concurrency of 4 by default (configurable).
- **Determinism:** the same inputs + EDL + seed must give the same output (pin versions, seed music, sort file listings).
- **Paths with spaces and unicode:** build argument lists, never shell strings; test with a fixture named `prova clip è.mov`.
- **Agent context hygiene:** keep CLI stdout short (≤ 30 lines by default); details go to files; `--verbose` for debugging.
- **Never silently degrade.** If a fallback is used (e.g. `arnndn` instead of DeepFilterNet, centre crop because no face), print a one-line warning and record it in `state.json`.

---

## 11. Testing summary

| Layer | What | Where it runs |
|---|---|---|
| Unit | config, refs, resolver (+ Hypothesis), fillers EN/IT, utterances, retakes, packing (golden), summary, camera.ts, caption paging | CI (Linux) + local |
| Schema | generated schemas/types are fresh | CI |
| Integration | ingest, analyze, look, assemble, compose, mix on fixtures | local Mac (`slow`, `mac`, `models`, `renderer`) |
| Music | ACE-Step worker, vocal check, library pick | local Mac (`music`) |
| E2E | full pipeline EN + IT + `check` passes | local Mac (`just e2e`) |
| Dogfood | real footage, following only the agent docs | Phase 13 |

---

## 12. Definition of done (v0.1.0)

- [ ] All phases' acceptance criteria are met and logged in `BUILD_LOG.md`.
- [ ] `just lint`, `just test` and `just e2e` pass on this Mac; CI config passes for Linux.
- [ ] A fresh workspace + any agent + "edit this into a Reel" produces a checked 9x16 final without the agent writing code.
- [ ] Works fully offline after `reelcut setup --music`.
- [ ] English and Italian are both verified end to end.
- [ ] README, docs, THIRD_PARTY (incl. Remotion, ACE-Step weights and CrisperWhisper licence notes), CHANGELOG, ROADMAP and HANDOFF are complete.
- [ ] The name is centralised and `docs/renaming.md` is accurate.
- [ ] Tagged `v0.1.0` locally.

## 13. Roadmap seeds (for `ROADMAP.md`)

- FCPXML / OpenTimelineIO export for finishing in DaVinci Resolve or Final Cut.
- Optional Gemini video pass for "visually interesting moment" detection (opt-in, paid).
- Multi-speaker (diarization) and podcast clipping.
- Licensed SFX library support (whooshes, pops) with the same licence-tracking as music.
- Smoothed face tracking within long single-shot segments.
- Auto-chaptering a long recording into several shorts.
- More languages via `lang/*.toml` contributions.
- Optional MCP server wrapping the CLI.
