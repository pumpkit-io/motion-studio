# reelcut

reelcut lets the coding agent you already use (Claude Code, Codex, Gemini CLI, Cursor) edit raw talking-head footage into finished short videos for Instagram Reels and X. You drop your takes into a project, open the agent and say "Edit this into a 45-second Reel and an X version". The agent reads a compact text index of the footage and writes an edit decision list (EDL) that names words and utterances by ID. reelcut validates the EDL into a frame-accurate timeline and renders it: cuts, filler and dead-air removal, retake selection, the hook moved to the front, face-centred reframing for 9:16, 16:9 and 4:5, word-by-word captions, punch-in zooms, B-roll, locally generated music, ducking and loudness mastering. Everything runs on your machine. reelcut never calls a language model and never uploads anything.

## How it works

```
raw/ ──ingest──► media/ (constant frame rate, SDR, cleaned voice)
                    │
                 analyze ──► analysis/packed.md    transcript with word IDs, fillers, pauses,
                    │                              retakes, shots, faces: a few thousand tokens
                    │
   your agent ◄─────┘  reads packed.md, looks at contact sheets when it needs eyes
       │
       └─writes──► edl.json ──plan validate──► build/timeline.json
                                     │
                   music ──► build/music.wav (ACE-Step, generated locally)
                                     │
                   render ──► preview/ or final/   (ffmpeg cuts, Remotion composition, mastering)
                                     │
                   check ──► check/report.md       (re-transcribes the render, flags clipped
                                                    words, loudness, black or frozen frames)
```

The agent makes the editorial choices and fixes what `check` flags; reelcut does the timing arithmetic and the rendering. See [docs/architecture.md](docs/architecture.md).

## Requirements

- macOS on Apple Silicon is the main platform and the one tested end to end. Linux uses the portable fallbacks (faster-whisper for speech, ffmpeg filters instead of VideoToolbox for HDR); CI runs the test suite there, but the full pipeline has only been run on a Mac.
- 16 GB of RAM. Heavy models run one at a time, in separate processes.
- [uv](https://docs.astral.sh/uv/), ffmpeg 7 or later, and Node 22.13+ or 24+. On macOS: `brew install uv ffmpeg node`. reelcut uses the system ffmpeg; Homebrew's build without `zscale` is fine, because HDR iPhone footage is tone-mapped with VideoToolbox instead.
- Disk: about 3 GB for the models and the renderer, 11 GB more for music generation, and room for your projects. Ingest, music and render refuse to start with less than 20 GB free.
- A coding agent that can run shell commands and read files.

## Quickstart

```sh
git clone https://github.com/pumpkit-io/reelcut.git
cd reelcut
uv tool install --python 3.12 '.[mac]'    # Apple Silicon; use '.[cpu]' on Linux or Intel
reelcut setup                             # models and renderer into the cache, once (~3 GB)
reelcut setup --music                     # optional: ACE-Step music generation (~11 GB)
reelcut doctor                            # everything should say ok
reelcut init ~/Videos/reels               # create a workspace
cd ~/Videos/reels
reelcut new my-video --from ~/Desktop/takes/
```

Then open your agent in `~/Videos/reels` (for example `claude`, `codex` or `gemini`) and ask:

> Edit my-video into a 45-second Reel and an X version.

The agent follows the workspace `AGENTS.md` and skills: it ingests and analyses the footage, drafts and refines the EDL, generates music, renders a preview, checks it, fixes what the check flags and renders the finals into `projects/my-video/final/`. After the first `setup`, editing works offline.

If you skip `setup --music`, set `mode = "none"` (voice only) or `mode = "library"` (your own licensed tracks in `library/music/`) under `[music]` in `reelcut.toml`.

Every command is in [docs/cli.md](docs/cli.md); the EDL format is in [docs/edl.md](docs/edl.md).

## Supported agents

`reelcut init` writes `AGENTS.md`, `CLAUDE.md` and `GEMINI.md`, and installs five skills (`reelcut-edit`, `reelcut-plan`, `reelcut-look`, `reelcut-music`, `reelcut-review`) where each agent looks for them:

| Agent | Skills | Instructions |
|---|---|---|
| Claude Code | `.claude/skills/` | `CLAUDE.md` (imports `AGENTS.md`) |
| Codex | `.agents/skills/` | `AGENTS.md` |
| Gemini CLI | `.agents/skills/` | `GEMINI.md` (imports `AGENTS.md`) |
| Cursor | `.agents/skills/` | `AGENTS.md` |

An agent without skills support reads `AGENTS.md`, which links each skill file by path. After upgrading reelcut, run `reelcut agents sync` in the workspace. Sources and caveats are in [docs/agents.md](docs/agents.md).

## Configuration

`reelcut.toml` in the workspace holds your defaults: output formats, frame rate, maximum duration, language (`auto`, `en` or `it`), review gates, trimming policy, caption style, music mode and level, loudness targets, and brand colours, font and logo. Each project's `project.toml` can override any key, and the EDL's `policy` block can override the trimming keys for one video. `reelcut config show <slug>` prints the merged result.

To approve the edit before the agent renders, set `plan = true` or `preview = true` under `[review]`, or ask the agent to stop for review.

English and Italian ship with v0.1.0. Another language is one data file: see [docs/adding-a-language.md](docs/adding-a-language.md).

## Licences

reelcut is MIT-licensed. Before using it in a business, note three things:

- **Remotion**, which renders the composition, is source-available under the Remotion License, not an OSI open-source licence. It is free, commercial use included, for individuals, for-profit organisations with up to 3 employees, non-profits, and for evaluation. A larger for-profit organisation needs a Company License from [remotion.pro](https://www.remotion.pro/license). The terms at [remotion.dev/license](https://www.remotion.dev/license) were checked on 2026-10-24 and match the `LICENSE.md` of the pinned Remotion 4.0.538; they say the licence changes slightly in Remotion 5.0.
- **ACE-Step 1.5 weights**, used for music generation, are MIT according to their model card at the pinned revision, and the card says generated music may be used commercially. `reelcut setup --music` prints the licence of the weights it downloads, and every `build/music.json` records it.
- **CrisperWhisper**, a verbatim speech-to-text model, is not shipped in v0.1.0. Its model card licence is CC BY-NC 4.0, which forbids commercial use; if it is added later (see [ROADMAP.md](ROADMAP.md)) it will stay off by default.

Music from your own library is yours to license: reelcut refuses library tracks without a licence entry and writes attributions to `final/<slug>_credits.txt`. [THIRD_PARTY.md](THIRD_PARTY.md) lists every dependency and model with its licence and a link.

## Security and privacy

- reelcut never uploads your media and has no telemetry. Network access happens only in `reelcut setup` (models from Hugging Face and GitHub, npm packages, Remotion's headless browser) and when you install reelcut itself.
- reelcut never modifies `raw/`.
- The skills tell your agent to run shell commands (`reelcut ...`) in the workspace. Review what your agent is allowed to run, as you would for any project.

## Troubleshooting

- Start with `reelcut doctor`. It names every missing tool, filter, model or setting with a fix, and exits 2 when something required is missing. `reelcut doctor --fix` downloads the missing models and renderer the way `reelcut setup` does and checks again; system tools such as ffmpeg and node stay yours to install.
- Exit codes: 1 means a fixable EDL or input problem (the message says what to change), 2 a missing dependency (run `reelcut setup` or follow the hint), 3 an internal error (rerun with `REELCUT_DEBUG=1` for the traceback and report it).
- `reelcut status <slug>` shows which stages are done or stale and the next command, if an edit was interrupted.
- "not enough free disk": free space or set `REELCUT_MIN_FREE_GB` lower, at your own risk.
- The first music generation spends most of its time loading ACE-Step's weights (about 4 minutes on an M3 Pro); re-running `reelcut music` with unchanged settings does nothing.
- A one-line `warning:` means reelcut used a fallback (YuNet instead of MediaPipe, `arnndn` instead of DeepFilterNet, `colorspace` instead of VideoToolbox for HDR, Inter instead of a missing brand font). It is also recorded in the project's `state.json`.
- HEIC and HEIF photos are decoded with `sips` on macOS, or with libheif's `heif-convert` on Linux. Without either, ingest skips them with a warning and goes on with the other files.
- Codex outside a Git repository only reads `AGENTS.md` and skills in the directory it starts in, so open it in the workspace root.

## Roadmap and development

Ideas beyond v0.1.0 are in [ROADMAP.md](ROADMAP.md). To work on reelcut itself, see [CONTRIBUTING.md](CONTRIBUTING.md) and [AGENTS.md](AGENTS.md).
