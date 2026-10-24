# Hand-off: reelcut v0.1.0

Written 2026-10-24 at the end of the unattended build (spec: issue #1; per-ticket record: [BUILD_LOG.md](BUILD_LOG.md)). No real footage was available during the build, so every timing below comes from the synthetic fixtures. Your first edit tomorrow morning is the first run on real takes.

## What was built

reelcut is a command-line toolchain that lets a coding agent (Claude Code, Codex, Gemini CLI, Cursor) edit talking-head footage into short vertical videos. The agent never writes code and never sees the video directly. It reads a text index of what was said, writes its creative decisions into `edl.json`, and reelcut does the rest:

- ingest: constant-frame-rate mezzanines, HDR tone-mapping, voice cleaned with DeepFilterNet.
- analyze: transcription with mlx-whisper, fillers, pauses, retakes, shots, static stretches and faces, packed into `analysis/packed.md`.
- plan: a deterministic first draft of the EDL, then validation with a short summary (duration, words kept, hook line).
- music: an instrumental bed generated locally with ACE-Step 1.5, beat-detected, or a licensed track from your library.
- render: the cut assembled with ffmpeg, captions, zooms, B-roll, titles and logo drawn with Remotion, music ducked under the voice, mastered to -14 LUFS.
- check: the voice re-transcribed and compared with the plan to catch clipped words, plus loudness, black and frozen frames, length and caption density.

English and Italian are supported; another language is one data file ([docs/adding-a-language.md](docs/adding-a-language.md)). How it works in detail: [README.md](README.md) and [docs/architecture.md](docs/architecture.md).

## Your workspace

Everything is installed and `reelcut doctor` reports all items ok on this Mac. The workspace is at `~/Videos/reels`, with one empty project:

```
~/Videos/reels/
  AGENTS.md, CLAUDE.md, GEMINI.md   what the agent reads first
  reelcut.toml                      workspace defaults (formats, captions, music, brand)
  library/music, library/brand      your own tracks, font and logo (each has a README)
  projects/first-test/raw/          empty: your takes go here
```

The global `reelcut` command is v0.1.0, installed from the integration branch.

## Tomorrow morning

1. Copy 2 to 5 talking-head takes into `~/Videos/reels/projects/first-test/raw/`, optionally with an image or a B-roll clip. Copy rather than move: reelcut never modifies `raw/`, but your originals are safer where they are. Convert iPhone HEIC photos to JPEG or PNG first (see the limitations).
2. Open a terminal, `cd ~/Videos/reels`, and start your agent there (`claude` for Claude Code).
3. Ask: "Edit first-test into a 45-second Reel and an X version."
4. Wait. The agent ingests, analyses, plans, generates music, renders a preview, checks it, fixes what the check flags and renders the finals. Expect a few minutes for ingest and analysis, about 4 minutes for music (mostly the model loading), and render time that grows with the length of the Reel.
5. The finals land in `projects/first-test/final/`: `first-test_9x16.mp4` and `first-test_16x9.mp4`. The agent reports the hook line, duration and the music it used.

To approve the plan or the preview before the agent goes on, say so in your request, or set `plan = true` or `preview = true` under `[review]` in `reelcut.toml`. Feedback such as "start stronger", "too choppy" or "music too loud" goes straight to the agent, which turns it into EDL changes (the `reelcut-review` skill has the table). Decisions and your feedback are kept in `projects/first-test/notes.md` for the next video.

For later videos: `reelcut new <slug> --from <files or a folder>`, then ask the agent the same way. Each project's state is in `reelcut status <slug>`.

## Timings from fixture runs

These come from the end-to-end test (`just e2e`, ticket #17) on this Mac (Apple M3 Pro, 18 GB, nothing else running): one synthetic talking clip of about 23 s, a 6 s B-roll clip and one image, edited into an 11 s Reel, music generated, previews in 9x16 and 16x9. They are not measurements on real footage, and they say little about a 5-minute shoot: analysis and rendering grow with length, music mostly does not.

| Stage | English (s) | Italian (s) |
|---|---|---|
| ingest | 5.5 | 5.3 |
| analyze (mlx-whisper and faces) | 10.5 | 8.9 |
| music (ACE-Step, a 14 s bed) | 248.0 | 218.8 |
| render preview (2 formats) | 40.4 | 36.9 |
| check | 5.4 | 5.5 |
| whole pipeline, all stages | 312.5 | 278.0 |

Other fixture runs:

- Claude Code, headless, in a fresh workspace with the English fixture, a B-roll clip and an image, asked "Edit my-video into a 45-second Reel and an X version.": 7 min 4 s from the request to both checked finals (ticket #18). It said 45 s was impossible, since the footage holds about 13 s of speech, and delivered 7 s videos.
- Music generation for a 60 s bed: 290 to 364 s, of which model loading was 227 s on a machine deep in swap (ticket #14).
- First-time `reelcut setup` downloads: renderer 14.5 min (mostly Chrome Headless Shell), `setup --music` 19 min (9.4 GB of ACE-Step weights). Both are done on this Mac.
- With all outbound network blocked (`sandbox-exec`, localhost allowed), a fresh workspace with the English fixture and a B-roll clip went from `ingest` to a passing `check --final` of a 9x16 final in about 4.8 minutes: ingest 5 s, analyze 9 s, music 248 s, final render 20 s, check 7 s (ticket #19). Editing works offline once `setup --music` has run.

## Known limitations

From the open issues in BUILD_LOG.md that still apply:

- `reelcut doctor --fix` (user story 6) was not built. `doctor` prints the fix for each failing item instead.
- HEIC/HEIF photos are not read; ingest fails with a hint to convert them.
- Clips are classified as A-roll only when they show a face. A screen recording with a voice-over becomes B-roll and needs `role = "aroll"` under its clip in `project.toml`.
- The static-stretch threshold was tuned on synthetic footage; real phone noise on a locked-off shot may hide static stretches. Worth looking at in the first run.
- A-roll clips of different aspect ratios are letterboxed to the first clip's size, and their reframing is off.
- Captions stay on screen during full-frame B-roll; there is no setting to hide them yet.
- Glyphs outside Inter's Latin sets (for example "→" in a title) fall back to a system font.
- Ingest rewrites `project.toml` when it adds clips, which drops comments you wrote in it (values are kept).
- Freshness checks compare file size and modification time, not content. An edited file with the same size and time is not noticed; `reelcut clean <slug> --all` starts the project over without touching `raw/`.
- On long takes Whisper occasionally attaches the first word of the next take to an abandoned one. The check stage re-transcribes the render and flags it.
- The check can report ASR noise right next to a cut as a clipped word. Its fix (more padding) is harmless.
- The two talking fixtures are about 23 s long, so nothing in the build measured a multi-minute shoot end to end. The 5-minute concatenation was checked only for the size of `packed.md` (about 2,040 tokens).
- Agents other than Claude Code were not run against a workspace. Gemini CLI has been succeeded by Antigravity CLI, and its use of `.agents/skills/` comes from third-party guides. Cursor sees each skill twice.
- Upgrading: `uv tool install` reuses its cached wheel when the version number is unchanged. To install a newer checkout with the same version, add `--reinstall-package reelcut`, then run `reelcut agents sync` in the workspace.

Blocked items: none. No ticket recorded an acceptance criterion as blocked in BUILD_LOG.md. The one adapted item is the guide's Phase 13 dogfood on real footage, which spec #1 replaces with this hand-off and your morning run.

## Licence caveats

- Remotion, which draws the composition, is source-available, not open source. It is free, commercial use included, for individuals, companies of up to 3 employees, non-profits and evaluation; a larger for-profit company needs a Company License from remotion.pro.
- ACE-Step 1.5 weights are MIT according to their model card at the pinned revision, and the card says generated music may be used commercially. This settles the open question in #1: local generation stays the default music mode. Every `build/music.json` records the licence, prompt and seed.
- CrisperWhisper is CC BY-NC 4.0 (non-commercial) and is not shipped. Setting `fillers_backend = "crisper"` fails with "not implemented in v0.1.0".
- Library music is yours to license: reelcut refuses tracks without a licence entry in `library/music/tags.json` and writes attributions to `final/<slug>_credits.txt`.

Every dependency and model, with its licence and a link: [THIRD_PARTY.md](THIRD_PARTY.md).

## Top five roadmap items

My pick from [ROADMAP.md](ROADMAP.md), ordered by how much they would change daily use:

1. FCPXML or OpenTimelineIO export, to finish an edit in DaVinci Resolve or Final Cut.
2. Auto-chaptering a long recording into several shorts.
3. Smoothed face tracking within long single-shot segments.
4. Claude Code plugin packaging for the skills.
5. `parakeet-mlx` as an optional Apple Silicon speech-to-text backend.

## Release state

Version 0.1.0 is set in `pyproject.toml` and CHANGELOG.md. The `v0.1.0` tag goes on the integration branch after the final code review, and PR #20 takes it to `main`.
