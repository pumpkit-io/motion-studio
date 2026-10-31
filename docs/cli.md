# CLI reference

Every command and option of `motion-studio` 0.1.0. The option lists were generated with `uv run typer motion_studio.cli utils docs --name motion-studio` and then edited by hand: examples and notes added, order changed to follow an edit. `tests/unit/test_docs.py` fails when a command or option is missing here; when you add one, regenerate into a scratch file and copy the new section in.

## Conventions

- Every leaf command takes `--json` and then prints one JSON object with `ok` at the top level. Human output stays around 30 lines and names every path it writes on its own line, as `wrote <path> (detail)`, or `unchanged <path>` when a rerun left the file alone.
- Exit codes: `0` OK, `1` fixable EDL or user error, `2` missing dependency (run `motion-studio doctor`), `3` internal error. With `--json`, an error prints `{"ok": false, "error", "hint", "exit_code"}`.
- Commands other than `init`, `setup`, `doctor` and `docs` look for `motion-studio.toml` in the current directory and its parents, so run them inside a workspace.
- `<slug>` is a project name under `projects/`: lowercase letters, digits and hyphens.
- Clip IDs are `c1` (A-roll), `b1` (B-roll) and `i1` (image); utterance IDs `c1.s4` and word IDs `c1.w52`. See `GLOSSARY.md`.
- Long steps report progress on stderr. In a terminal (stdout and stderr both TTYs, no `--json`) that is a Rich progress line per step: a bar for ingest encodes and the A-roll assembly, a spinner with the elapsed time for Remotion, music and the rest. Elsewhere each step is one `<step> ...` line, and `--json` prints none.
- A fallback (YuNet for faces, `arnndn` for denoising, `colorspace` for HDR, a missing brand font) prints one `warning:` line on stderr and is recorded in the stage's `warnings` in `state.json`.

The usual order for one video:

```console
$ motion-studio new talk --from ~/Desktop/takes/
$ motion-studio ingest talk
$ motion-studio analyze talk
$ motion-studio plan draft talk          # then edit edl.json
$ motion-studio plan validate talk
$ motion-studio music talk
$ motion-studio plan validate talk       # snaps overlays to the music's beats
$ motion-studio render talk --preview
$ motion-studio check talk --preview
$ motion-studio render talk --final
$ motion-studio check talk --final
```

`motion-studio status talk` prints the next command at any point.

## `motion-studio`

```console
$ motion-studio [OPTIONS] COMMAND [ARGS]...
```

* `--version`: Print the version and exit.
* `--help`: Show this message and exit.

## Machine setup

## `motion-studio setup`

Download the speech, voice-activity and denoiser models and the renderer, for offline use.

```console
$ motion-studio setup [OPTIONS]
```

* `--music`: Also create the ACE-Step music environment.
* `--crisper`: CrisperWhisper fillers backend (not in v0.1.0).
* `--json`: Print machine-readable JSON.
* `--help`: Show this message and exit.

Plain `setup` installs, into the cache (`~/Library/Caches/motion-studio` on macOS, `~/.cache/motion-studio` on Linux, or `$MOTION_STUDIO_CACHE_DIR`): the DeepFilterNet binary, the Silero VAD model, both face models, the Whisper model for this platform's backend, and the Remotion renderer with its headless browser (about 570 MB). `--music` adds the ACE-Step 1.5 environment and weights (9.4 GB of weights; the first run took 19 minutes on the build machine) and prints the weights' licence. Items already present are reported, not fetched again. `--crisper` exits 2: CrisperWhisper is on `ROADMAP.md`.

When the cache from before the rename is still there (in the platform cache directory under the previous name, or wherever the previous name's `_CACHE_DIR` variable points) and the new one holds no files apart from empty lock files, `setup` exits 1 before downloading anything and prints the one-line command that adopts it, since the old cache can hold 16 GB. For the platform default that command is an `mv` into the new default location, after it clears the empty folders and lock files that commands lay down there. It stops without moving anything when that location holds anything else by then. For a location the old variable chose, it is `export MOTION_STUDIO_CACHE_DIR=<that path>`, so nothing crosses volumes. Put that `export` in your shell profile so it lasts past the current shell. Run that command, or delete the old directory to download everything again. Nothing is moved for you, and a set `$MOTION_STUDIO_CACHE_DIR` skips the check.

```console
$ motion-studio setup
$ motion-studio setup --music
```

## `motion-studio doctor`

Check ffmpeg and its filters, node, the ASR backend, caches, free disk and RAM.

Exits 2 when something required is missing; warnings alone exit 0.

```console
$ motion-studio doctor [OPTIONS]
```

* `--fix`: Download what `setup` installs when it is missing, then check again.
* `--json`: Print machine-readable JSON.
* `--help`: Show this message and exit.

Each line is `ok`, `warn` or `missing` with a suggested fix. Free disk below 20 GB (`MOTION_STUDIO_MIN_FREE_GB` changes the threshold) is a warning here; ingest, music and render refuse to start below it. The `heic decoder` line warns when neither `sips` nor `heif-convert` is there, since ingest then skips HEIC photos. An `old cache` line warns when the cache from before the rename is still there (the same lookup as `setup`) and the new one holds no files apart from empty lock files; its fix is the command that adopts it, the same `mv` or `export` as `setup` prints (doctor never moves it).

`--fix` runs the installs the build guide calls safe: when the renderer, the speech or face models or DeepFilterNet are missing, it runs the same downloads as plain `setup`, then prints the checks again. It never runs brew, apt or npm for system tools such as ffmpeg and node, and never fetches ACE-Step (`setup --music`); their fixes stay on their lines. With `--json` the result also carries `fixed` (what it installed) and `fix_error`.

## Workspaces and projects

## `motion-studio init`

Create a workspace: AGENTS.md, CLAUDE.md, motion-studio.toml, library/ and projects/.

```console
$ motion-studio init [OPTIONS] {directory}
```

* `directory`: Directory to turn into a workspace.  [required]
* `--json`: Print machine-readable JSON.
* `--help`: Show this message and exit.

Also writes `GEMINI.md` and installs the five editing skills into `.claude/skills/` and `.agents/skills/` (see `docs/agents.md`).

```console
$ motion-studio init ~/Videos/reels
```

## `motion-studio new`

Create a project and hard-link (or copy) the given clips into its raw/ directory.

```console
$ motion-studio new [OPTIONS] {slug} [more]...
```

* `slug`: Project slug: lowercase letters, digits, hyphens.  [required]
* `more...`: More files or directories, as in `--from a.mov b.mov`.
* `--from <path>`: A file or directory to put in raw/. Repeatable.
* `--title <str>`: Human title; defaults to the slug.
* `--json`: Print machine-readable JSON.
* `--help`: Show this message and exit.

```console
$ motion-studio new launch-day --from ~/Desktop/takes/ --title "Launch day"
$ motion-studio new launch-day --from take1.mov take2.mov broll.mp4 logo.png
```

## `motion-studio status`

Show each stage, which are stale, and the next command to run.

```console
$ motion-studio status [OPTIONS] {slug}
```

* `slug`: Project slug: lowercase letters, digits, hyphens.  [required]
* `--json`: Print machine-readable JSON.
* `--help`: Show this message and exit.

Stages are `ingest`, `analyze`, `plan`, `music`, `preview`, `check` and `final`; each is `pending`, `done`, `stale` (an input changed since it ran) or `failed`.

## `motion-studio clean`

Delete caches (media/, build/, preview/) to reclaim disk. raw/ is never touched.

```console
$ motion-studio clean [OPTIONS] {slug}
```

* `slug`: Project slug: lowercase letters, digits, hyphens.  [required]
* `--all`: Also delete analysis, checks, final/, edl.json and notes.md (never raw/).
* `--yes`: Skip the confirmation for --all.
* `--json`: Print machine-readable JSON.
* `--help`: Show this message and exit.

`--all` also deletes `state.json`, which resets the look budget.

## `motion-studio config show`

Print defaults < motion-studio.toml < project.toml < EDL policy, merged.

```console
$ motion-studio config show [OPTIONS] [slug]
```

* `slug`: Project slug; omit for the workspace level only.
* `--json`: Print machine-readable JSON.
* `--help`: Show this message and exit.

## `motion-studio agents sync`

Copy the current skills into the workspace for each agent (run after an upgrade).

Also migrates a workspace from before the rename: the old toml, AGENTS.md and skill folders.

```console
$ motion-studio agents sync [OPTIONS]
```

* `--targets <str>`: Comma-separated agents (claude,codex,gemini,cursor). Default: all.
* `--json`: Print machine-readable JSON.
* `--help`: Show this message and exit.

Replaces only the `motion-studio-*` skill folders and leaves other skills alone. `.agents/skills/` is always written.

### Migrating a workspace made before the rename

A workspace created before the rename to motion-studio has the previous name's `.toml` file, skill folders and commands in its `AGENTS.md`. Every other command run inside it exits 1 with a hint to run `motion-studio agents sync`. Sync migrates it:

1. It renames the old `.toml` to `motion-studio.toml` with its contents unchanged.
2. An `AGENTS.md` that `init` wrote and nobody edited is replaced with the current template (`rewrote <path> from the template`). An edited one keeps your text: only the old name as a command (followed by one of its commands or an option, or alone in backticks), the five shipped skill names, the `.toml` name and the variable prefix change to the new name (`renamed <old> to motion-studio in <path> (N places)`). Anywhere else the previous name stays, as in a path, a URL or another file name, and in prose unless a command or option follows it; so does a skill of your own whose name contains it. An `AGENTS.md` that is not UTF-8 is left alone with a one-line warning naming it.
3. It installs the `motion-studio-*` skills, then removes the five shipped skills' old-name folders (edit, look, music, plan, review) from `.claude/skills/` and `.agents/skills/`. Your own skills stay, whatever their name. If the install fails, the old skills are still there.

It prints a line for each change (`renamed`, `agents_md` and `removed` under `--json`; `agents_md` is `null` when the file was left alone; `warnings` lists the warnings). A second run migrates nothing. When both `.toml` files exist, sync exits 1 naming both and changes nothing: keep your settings in `motion-studio.toml` and delete the other.

```console
$ motion-studio agents sync --targets claude,codex
```

## Ingest and analysis

## `motion-studio ingest`

Give each raw file a clip ID, normalise it to a CFR SDR mezzanine and clean its audio.

```console
$ motion-studio ingest [OPTIONS] {slug}
```

* `slug`: Project slug: lowercase letters, digits, hyphens.  [required]
* `--json`: Print machine-readable JSON.
* `--help`: Show this message and exit.

Writes `media/<id>.mp4` (constant frame rate, rotation applied, HDR tone-mapped to BT.709), `media/<id>.wav` (denoised voice, 48 kHz) and `media/<id>_16k.wav` per video, a normalised `media/<id>.jpg` or `.png` per image (HEIC and HEIF become PNG, decoded with `sips` on macOS or `heif-convert` from libheif elsewhere; with neither installed they are skipped with a warning), and `media/manifest.json`. Clip IDs and roles go in `project.toml`; edit a clip's `role` there to override the classification. Re-running with unchanged inputs does nothing.

## `motion-studio analyze`

Transcribe speech, find shots, static stretches and faces, and write the indexes.

```console
$ motion-studio analyze [OPTIONS] {slug}
```

* `slug`: Project slug: lowercase letters, digits, hyphens.  [required]
* `--clip <str>`: Re-analyse only this clip, e.g. c1.
* `--json`: Print machine-readable JSON.
* `--help`: Show this message and exit.

Writes `analysis/<id>.json` per clip, `analysis/retakes.json`, `analysis/packed.md` (the index the agent reads first), `analysis/assets.md` and a contact sheet `contact/<id>.png` per B-roll clip and image. Descriptions written into `assets.md` survive re-analysis.

## Looking at footage

## `motion-studio words`

Print the words from START to END with their IDs, source times and filler marks.

```console
$ motion-studio words [OPTIONS] {slug} {start} [end]
```

* `slug`: Project slug: lowercase letters, digits, hyphens.  [required]
* `start`: First word or utterance ID, e.g. c1.s4.  [required]
* `end`: Last word or utterance ID; default: same as start.
* `--json`: Print machine-readable JSON.
* `--help`: Show this message and exit.

```console
$ motion-studio words talk c1.s4
$ motion-studio words talk c1.w40 c1.w60
```

## `motion-studio look`

Draw frames, waveform, word labels and face boxes for T0 to T1 of CLIP into one PNG.

```console
$ motion-studio look [OPTIONS] {slug} {clip} {t0} {t1}
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
$ motion-studio look talk c1 12.0 18.5 --frames 6
```

## `motion-studio look-asset`

Redraw the contact sheet of a B-roll clip or image into contact/<id>.png.

```console
$ motion-studio look-asset [OPTIONS] {slug} {asset}
```

* `slug`: Project slug: lowercase letters, digits, hyphens.  [required]
* `asset`: B-roll or image ID, e.g. b1 or i1.  [required]
* `--json`: Print machine-readable JSON.
* `--help`: Show this message and exit.

Does not count against the look budget.

## Planning

## `motion-studio plan draft`

Write a deterministic baseline edl.json: all usable speech in source order.

```console
$ motion-studio plan draft [OPTIONS] {slug}
```

* `slug`: Project slug: lowercase letters, digits, hyphens.  [required]
* `--force`: Replace an existing edl.json.
* `--json`: Print machine-readable JSON.
* `--help`: Show this message and exit.

The draft keeps retake winners, drops hard fillers, tightens pauses and adds a neutral instrumental music prompt. It refuses to overwrite an existing `edl.json` without `--force`.

## `motion-studio plan validate`

Resolve edl.json into build/timeline.json and print a short summary.

```console
$ motion-studio plan validate [OPTIONS] {slug}
```

* `slug`: Project slug: lowercase letters, digits, hyphens.  [required]
* `--json`: Print machine-readable JSON.
* `--help`: Show this message and exit.

Prints the duration, words kept, fillers removed, the hook text, event counts and each warning with a fix. An error (exit 1) names the problem and a fix in EDL terms, for example `anchor to c1.w57` when an event points at a dropped word.

## `motion-studio docs edl`

Print the EDL reference: segments, references, drops, events and music.

```console
$ motion-studio docs edl [OPTIONS]
```

* `--json`: Print machine-readable JSON.
* `--help`: Show this message and exit.

The same text as `docs/edl.md`.

## Music, render and check

## `motion-studio music`

Generate (ACE-Step) or pick (library) the music bed: build/music.wav and music.json.

```console
$ motion-studio music [OPTIONS] {slug}
```

* `slug`: Project slug: lowercase letters, digits, hyphens.  [required]
* `--json`: Print machine-readable JSON.
* `--help`: Show this message and exit.

The mode, prompt, BPM and seed come from the EDL's `music` block, falling back to `[music]` in the config. `generate` needs `motion-studio setup --music` and retries up to three seeds when the bed has vocals. `library` picks a licensed track from `library/music/tags.json` and refuses one without a licence. `none` removes the bed. Every generated bed is shaped for laptop and phone speakers (a high-pass at 35 Hz, a 4 dB low-shelf cut at 120 Hz, 3 dB of presence at 3 kHz and of air above 7 kHz, gentle compression); a library track is left as licensed. `build/music.json` records the prompt, seed, model, licence, BPM and beats. Run `plan validate` again afterwards so overlays snap to the beats.

## `motion-studio render`

Cut the A-roll, compose each format with Remotion, then duck music and master loudness.

```console
$ motion-studio render [OPTIONS] {slug}
```

* `slug`: Project slug: lowercase letters, digits, hyphens.  [required]
* `--preview`: The half-resolution preview in preview/ (the default).
* `--final`: The full-resolution final in final/.
* `--format <str>`: Render only this format (repeatable); default all.
* `--concurrency <int>`: Frames Remotion renders in parallel.  [default: 4]
* `--json`: Print machine-readable JSON.
* `--help`: Show this message and exit.

Previews go to `preview/<format>.mp4`, finals to `final/<slug>_<format>.mp4`, mastered to −14 LUFS integrated and −1.5 dBTP true peak by default (`[master]`): mastering measures the integrated loudness, applies one fixed gain to the target and then a 4x-oversampled true-peak limiter, so a mix with loud peaks reaches the target loudness without clipping. Render validates the EDL first when the plan stage is not done.

```console
$ motion-studio render talk --preview
$ motion-studio render talk --final --format 9x16 --format 16x9
```

## `motion-studio check`

Re-transcribe, measure and look at a render; exit 1 when anything blocks delivery.

```console
$ motion-studio check [OPTIONS] {slug}
```

* `slug`: Project slug: lowercase letters, digits, hyphens.  [required]
* `--preview`: The half-resolution preview in preview/ (the default).
* `--final`: The full-resolution final in final/.
* `--json`: Print machine-readable JSON.
* `--help`: Show this message and exit.

Writes `check/report.md`, `check/report.json` and `check/cuts.png` (the frames either side of every cut). Blocking issues: `clipped_cut` (a word missing near a cut), `over_duration`, `black_frames`, `overlay_overlap`, and on `--final` also `loudness` (integrated loudness more than 1 LU off `[master] integrated_lufs`) and `true_peak` (above `[master] true_peak_db`). Warnings: `loudness` and `true_peak` on a preview (true peak only from 0.5 dB over), `small_speaker` (energy above 1 kHz more than 10 dB below the energy under 150 Hz, so the mix sounds faint on laptop and phone speakers), `frozen_frames`, `caption_density`, `title_over_broll`, `event_past_end`. The metrics give each format's energy in four bands: below 150 Hz, 150 Hz to 1 kHz, 1 to 5 kHz and above 5 kHz (`bands` in `--json`, in dB full scale). Each issue carries a fix in EDL terms. Run it right after the render it checks: re-validating the EDL makes the render stale and check refuses.

## Environment variables

| Variable | Effect |
|---|---|
| `MOTION_STUDIO_CACHE_DIR` | Cache directory for models, the renderer and the ACE-Step environment. |
| `MOTION_STUDIO_MIN_FREE_GB` | Free-disk threshold for doctor's warning and the long-writing stages (default 20). |
| `MOTION_STUDIO_DEBUG` | `1` prints the traceback of an internal error. |
| `MOTION_STUDIO_TONEMAP` | Force the HDR tone-map method: `scale_vt`, `zscale` or `colorspace`. |
| `MOTION_STUDIO_DEEP_FILTER` | Path of a `deep-filter` binary to use instead of the cached one. |
| `MOTION_STUDIO_RENDERER_DIR` | Use this Remotion project instead of the installed renderer. |
| `MOTION_STUDIO_MUSIC_TIMEOUT_S` | Timeout for one ACE-Step generation. |

Variables with the previous name's prefix are no longer read: when one is set, every command prints a one-line warning naming its `MOTION_STUDIO_` replacement with the same value (`set MOTION_STUDIO_CACHE_DIR=<path> instead`). When the previous name's `_CACHE_DIR` holds the previous default location, the warning says to unset it instead, and `doctor` prints the `mv` that adopts that cache.

Tests also use `MOTION_STUDIO_ASR_WORKER`, `MOTION_STUDIO_FACE_WORKER` and `MOTION_STUDIO_MUSIC_WORKER` to replace the model workers with stand-ins.
