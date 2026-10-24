# CLI reference

Every command and option of `reelcut` 0.1.0. The option lists were generated with `uv run typer reelcut.cli utils docs --name reelcut` and then edited by hand: examples and notes added, order changed to follow an edit. `tests/unit/test_docs.py` fails when a command or option is missing here; when you add one, regenerate into a scratch file and copy the new section in.

## Conventions

- Every leaf command takes `--json` and then prints one JSON object with `ok` at the top level. Human output stays around 30 lines and prints every path it writes.
- Exit codes: `0` OK, `1` fixable EDL or user error, `2` missing dependency (run `reelcut doctor`), `3` internal error. With `--json`, an error prints `{"ok": false, "error", "hint", "exit_code"}`.
- Commands other than `init`, `setup`, `doctor` and `docs` look for `reelcut.toml` in the current directory and its parents, so run them inside a workspace.
- `<slug>` is a project name under `projects/`: lowercase letters, digits and hyphens.
- Clip IDs are `c1` (A-roll), `b1` (B-roll) and `i1` (image); utterance IDs `c1.s4` and word IDs `c1.w52`. See `GLOSSARY.md`.
- A fallback (YuNet for faces, `arnndn` for denoising, `colorspace` for HDR, a missing brand font) prints one `warning:` line on stderr and is recorded in the stage's `warnings` in `state.json`.

The usual order for one video:

```console
$ reelcut new talk --from ~/Desktop/takes/
$ reelcut ingest talk
$ reelcut analyze talk
$ reelcut plan draft talk          # then edit edl.json
$ reelcut plan validate talk
$ reelcut music talk
$ reelcut plan validate talk       # snaps overlays to the music's beats
$ reelcut render talk --preview
$ reelcut check talk --preview
$ reelcut render talk --final
$ reelcut check talk --final
```

`reelcut status talk` prints the next command at any point.

## `reelcut`

```console
$ reelcut [OPTIONS] COMMAND [ARGS]...
```

* `--version`: Print the version and exit.
* `--help`: Show this message and exit.

## Machine setup

## `reelcut setup`

Download the speech, voice-activity and denoiser models and the renderer, for offline use.

```console
$ reelcut setup [OPTIONS]
```

* `--music`: Also create the ACE-Step music environment.
* `--crisper`: CrisperWhisper fillers backend (not in v0.1.0).
* `--json`: Print machine-readable JSON.
* `--help`: Show this message and exit.

Plain `setup` installs, into the cache (`~/Library/Caches/reelcut` on macOS, `~/.cache/reelcut` on Linux, or `$REELCUT_CACHE_DIR`): the DeepFilterNet binary, the Silero VAD model, both face models, the Whisper model for this platform's backend, and the Remotion renderer with its headless browser (about 570 MB). `--music` adds the ACE-Step 1.5 environment and weights (9.4 GB of weights; the first run took 19 minutes on the build machine) and prints the weights' licence. Items already present are reported, not fetched again. `--crisper` exits 2: CrisperWhisper is on `ROADMAP.md`.

```console
$ reelcut setup
$ reelcut setup --music
```

## `reelcut doctor`

Check ffmpeg and its filters, node, the ASR backend, caches, free disk and RAM.

Exits 2 when something required is missing; warnings alone exit 0.

```console
$ reelcut doctor [OPTIONS]
```

* `--json`: Print machine-readable JSON.
* `--help`: Show this message and exit.

Each line is `ok`, `warn` or `missing` with a suggested fix. Free disk below 20 GB (`REELCUT_MIN_FREE_GB` changes the threshold) is a warning here; ingest, music and render refuse to start below it.

## Workspaces and projects

## `reelcut init`

Create a workspace: AGENTS.md, CLAUDE.md, reelcut.toml, library/ and projects/.

```console
$ reelcut init [OPTIONS] {directory}
```

* `directory`: Directory to turn into a workspace.  [required]
* `--json`: Print machine-readable JSON.
* `--help`: Show this message and exit.

Also writes `GEMINI.md` and installs the five editing skills into `.claude/skills/` and `.agents/skills/` (see `docs/agents.md`).

```console
$ reelcut init ~/Videos/reels
```

## `reelcut new`

Create a project and hard-link (or copy) the given clips into its raw/ directory.

```console
$ reelcut new [OPTIONS] {slug} [more]...
```

* `slug`: Project slug: lowercase letters, digits, hyphens.  [required]
* `more...`: More files or directories, as in `--from a.mov b.mov`.
* `--from <path>`: A file or directory to put in raw/. Repeatable.
* `--title <str>`: Human title; defaults to the slug.
* `--json`: Print machine-readable JSON.
* `--help`: Show this message and exit.

```console
$ reelcut new launch-day --from ~/Desktop/takes/ --title "Launch day"
$ reelcut new launch-day --from take1.mov take2.mov broll.mp4 logo.png
```

## `reelcut status`

Show each stage, which are stale, and the next command to run.

```console
$ reelcut status [OPTIONS] {slug}
```

* `slug`: Project slug: lowercase letters, digits, hyphens.  [required]
* `--json`: Print machine-readable JSON.
* `--help`: Show this message and exit.

Stages are `ingest`, `analyze`, `plan`, `music`, `preview`, `check` and `final`; each is `pending`, `done`, `stale` (an input changed since it ran) or `failed`.

## `reelcut clean`

Delete caches (media/, build/, preview/) to reclaim disk. raw/ is never touched.

```console
$ reelcut clean [OPTIONS] {slug}
```

* `slug`: Project slug: lowercase letters, digits, hyphens.  [required]
* `--all`: Also delete analysis, checks, final/, edl.json and notes.md (never raw/).
* `--yes`: Skip the confirmation for --all.
* `--json`: Print machine-readable JSON.
* `--help`: Show this message and exit.

`--all` also deletes `state.json`, which resets the look budget.

## `reelcut config show`

Print defaults < reelcut.toml < project.toml < EDL policy, merged.

```console
$ reelcut config show [OPTIONS] [slug]
```

* `slug`: Project slug; omit for the workspace level only.
* `--json`: Print machine-readable JSON.
* `--help`: Show this message and exit.

## `reelcut agents sync`

Copy the current skills into the workspace for each agent (run after an upgrade).

```console
$ reelcut agents sync [OPTIONS]
```

* `--targets <str>`: Comma-separated agents (claude,codex,gemini,cursor). Default: all.
* `--json`: Print machine-readable JSON.
* `--help`: Show this message and exit.

Replaces only the `reelcut-*` skill folders and leaves other skills alone. `.agents/skills/` is always written.

```console
$ reelcut agents sync --targets claude,codex
```

## Ingest and analysis

## `reelcut ingest`

Give each raw file a clip ID, normalise it to a CFR SDR mezzanine and clean its audio.

```console
$ reelcut ingest [OPTIONS] {slug}
```

* `slug`: Project slug: lowercase letters, digits, hyphens.  [required]
* `--json`: Print machine-readable JSON.
* `--help`: Show this message and exit.

Writes `media/<id>.mp4` (constant frame rate, rotation applied, HDR tone-mapped to BT.709), `media/<id>.wav` (denoised voice, 48 kHz) and `media/<id>_16k.wav` per video, a normalised `media/<id>.jpg` or `.png` per image, and `media/manifest.json`. Clip IDs and roles go in `project.toml`; edit a clip's `role` there to override the classification. Re-running with unchanged inputs does nothing.

## `reelcut analyze`

Transcribe speech, find shots, static stretches and faces, and write the indexes.

```console
$ reelcut analyze [OPTIONS] {slug}
```

* `slug`: Project slug: lowercase letters, digits, hyphens.  [required]
* `--clip <str>`: Re-analyse only this clip, e.g. c1.
* `--json`: Print machine-readable JSON.
* `--help`: Show this message and exit.

Writes `analysis/<id>.json` per clip, `analysis/retakes.json`, `analysis/packed.md` (the index the agent reads first), `analysis/assets.md` and a contact sheet `contact/<id>.png` per B-roll clip and image. Descriptions written into `assets.md` survive re-analysis.

## Looking at footage

## `reelcut words`

Print the words from START to END with their IDs, source times and filler marks.

```console
$ reelcut words [OPTIONS] {slug} {start} [end]
```

* `slug`: Project slug: lowercase letters, digits, hyphens.  [required]
* `start`: First word or utterance ID, e.g. c1.s4.  [required]
* `end`: Last word or utterance ID; default: same as start.
* `--json`: Print machine-readable JSON.
* `--help`: Show this message and exit.

```console
$ reelcut words talk c1.s4
$ reelcut words talk c1.w40 c1.w60
```

## `reelcut look`

Draw frames, waveform, word labels and face boxes for T0 to T1 of CLIP into one PNG.

```console
$ reelcut look [OPTIONS] {slug} {clip} {t0} {t1}
```

* `slug`: Project slug: lowercase letters, digits, hyphens.  [required]
* `clip`: Clip ID, e.g. c1.  [required]
* `t0`: Start, in source seconds.  [required]
* `t1`: End, in source seconds.  [required]
* `--frames <int>`: Frames across the range.  [default: 8]
* `--out <path>`: Write the PNG here instead of contact/.
* `--json`: Print machine-readable JSON.
* `--help`: Show this message and exit.

Each sheet counts against the look budget (`[edit] look_budget`, default 8). Past it, `look` still writes the sheet and prints a warning.

```console
$ reelcut look talk c1 12.0 18.5 --frames 6
```

## `reelcut look-asset`

Redraw the contact sheet of a B-roll clip or image into contact/<id>.png.

```console
$ reelcut look-asset [OPTIONS] {slug} {asset}
```

* `slug`: Project slug: lowercase letters, digits, hyphens.  [required]
* `asset`: B-roll or image ID, e.g. b1 or i1.  [required]
* `--json`: Print machine-readable JSON.
* `--help`: Show this message and exit.

Does not count against the look budget.

## Planning

## `reelcut plan draft`

Write a deterministic baseline edl.json: all usable speech in source order.

```console
$ reelcut plan draft [OPTIONS] {slug}
```

* `slug`: Project slug: lowercase letters, digits, hyphens.  [required]
* `--force`: Replace an existing edl.json.
* `--json`: Print machine-readable JSON.
* `--help`: Show this message and exit.

The draft keeps retake winners, drops hard fillers, tightens pauses and adds a neutral instrumental music prompt. It refuses to overwrite an existing `edl.json` without `--force`.

## `reelcut plan validate`

Resolve edl.json into build/timeline.json and print a short summary.

```console
$ reelcut plan validate [OPTIONS] {slug}
```

* `slug`: Project slug: lowercase letters, digits, hyphens.  [required]
* `--json`: Print machine-readable JSON.
* `--help`: Show this message and exit.

Prints the duration, words kept, fillers removed, the hook text, event counts and each warning with a fix. An error (exit 1) names the problem and a fix in EDL terms, for example `anchor to c1.w57` when an event points at a dropped word.

## `reelcut docs edl`

Print the EDL reference: segments, references, drops, events and music.

```console
$ reelcut docs edl [OPTIONS]
```

* `--json`: Print machine-readable JSON.
* `--help`: Show this message and exit.

The same text as `docs/edl.md`.

## Music, render and check

## `reelcut music`

Generate (ACE-Step) or pick (library) the music bed: build/music.wav and music.json.

```console
$ reelcut music [OPTIONS] {slug}
```

* `slug`: Project slug: lowercase letters, digits, hyphens.  [required]
* `--json`: Print machine-readable JSON.
* `--help`: Show this message and exit.

The mode, prompt, BPM and seed come from the EDL's `music` block, falling back to `[music]` in the config. `generate` needs `reelcut setup --music` and retries up to three seeds when the bed has vocals. `library` picks a licensed track from `library/music/tags.json` and refuses one without a licence. `none` removes the bed. `build/music.json` records the prompt, seed, model, licence, BPM and beats. Run `plan validate` again afterwards so overlays snap to the beats.

## `reelcut render`

Cut the A-roll, compose each format with Remotion, then duck music and master loudness.

```console
$ reelcut render [OPTIONS] {slug}
```

* `slug`: Project slug: lowercase letters, digits, hyphens.  [required]
* `--preview`: Half resolution into preview/ (the default).
* `--final`: Full resolution into final/.
* `--format <str>`: Render only this format (repeatable); default all.
* `--concurrency <int>`: Frames Remotion renders in parallel.  [default: 4]
* `--json`: Print machine-readable JSON.
* `--help`: Show this message and exit.

Previews go to `preview/<format>.mp4`, finals to `final/<slug>_<format>.mp4`, mastered to −14 LUFS integrated and −1.5 dBTP true peak by default (`[master]`). Render validates the EDL first when the plan stage is not done.

```console
$ reelcut render talk --preview
$ reelcut render talk --final --format 9x16 --format 16x9
```

## `reelcut check`

Re-transcribe, measure and look at a render; exit 1 when anything blocks delivery.

```console
$ reelcut check [OPTIONS] {slug}
```

* `slug`: Project slug: lowercase letters, digits, hyphens.  [required]
* `--preview`: Check the preview render (the default).
* `--final`: Check the final render.
* `--json`: Print machine-readable JSON.
* `--help`: Show this message and exit.

Writes `check/report.md`, `check/report.json` and `check/cuts.png` (the frames either side of every cut). Blocking issues: `clipped_cut` (a word missing near a cut), `over_duration`, `black_frames`, `overlay_overlap`. Warnings: `loudness`, `true_peak`, `frozen_frames`, `caption_density`, `title_over_broll`, `event_past_end`. Each issue carries a fix in EDL terms. Run it right after the render it checks: re-validating the EDL makes the render stale and check refuses.

## Environment variables

| Variable | Effect |
|---|---|
| `REELCUT_CACHE_DIR` | Cache directory for models, the renderer and the ACE-Step environment. |
| `REELCUT_MIN_FREE_GB` | Free-disk threshold for doctor's warning and the long-writing stages (default 20). |
| `REELCUT_DEBUG` | `1` prints the traceback of an internal error. |
| `REELCUT_TONEMAP` | Force the HDR tone-map method: `scale_vt`, `zscale` or `colorspace`. |
| `REELCUT_DEEP_FILTER` | Path of a `deep-filter` binary to use instead of the cached one. |
| `REELCUT_RENDERER_DIR` | Use this Remotion project instead of the installed renderer. |
| `REELCUT_MUSIC_TIMEOUT_S` | Timeout for one ACE-Step generation. |

Tests also use `REELCUT_ASR_WORKER`, `REELCUT_FACE_WORKER` and `REELCUT_MUSIC_WORKER` to replace the model workers with stand-ins.
