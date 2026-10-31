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
* `--record`: Also install Playwright and Chromium for `record web`.
* `--crisper`: CrisperWhisper fillers backend (not in v0.1.0).
* `--json`: Print machine-readable JSON.
* `--help`: Show this message and exit.

Plain `setup` installs, into the cache (`~/Library/Caches/motion-studio` on macOS, `~/.cache/motion-studio` on Linux, or `$MOTION_STUDIO_CACHE_DIR`): the DeepFilterNet binary, the Silero VAD model, both face models, the Whisper model for this platform's backend, and the Remotion renderer with its headless browser (about 570 MB). `--record` adds Playwright 1.64.1 and its headless Chromium (about 210 MB) under `recorder/` in the cache, for `record web`. `--music` adds the ACE-Step 1.5 environment and weights (9.4 GB of weights; the first run took 19 minutes on the build machine) and prints the weights' licence. Items already present are reported, not fetched again. `--crisper` exits 2: CrisperWhisper is on `ROADMAP.md`.

When the cache from before the rename is still there (in the platform cache directory under the previous name, or wherever the previous name's `_CACHE_DIR` variable points) and the new one holds no files apart from empty lock files, `setup` exits 1 before downloading anything and prints the one-line command that adopts it, since the old cache can hold 16 GB. For the platform default that command is an `mv` into the new default location, after it clears the empty folders and lock files that commands lay down there. It stops without moving anything when that location holds anything else by then. For a location the old variable chose, it is `export MOTION_STUDIO_CACHE_DIR=<that path>`, so nothing crosses volumes. Put that `export` in your shell profile so it lasts past the current shell. Run that command, or delete the old directory to download everything again. Nothing is moved for you, and a set `$MOTION_STUDIO_CACHE_DIR` skips the check.

```console
$ motion-studio setup
$ motion-studio setup --music
$ motion-studio setup --record
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

Each line is `ok`, `warn` or `missing` with a suggested fix. Free disk below 20 GB (`MOTION_STUDIO_MIN_FREE_GB` changes the threshold) is a warning here; ingest, music and render refuse to start below it. The `heic decoder` line warns when neither `sips` nor `heif-convert` is there, since ingest then skips HEIC photos. An `old cache` line warns when the cache from before the rename is still there (the same lookup as `setup`) and the new one holds no files apart from empty lock files; its fix is the command that adopts it, the same `mv` or `export` as `setup` prints (doctor never moves it). The `vhs` and `ttyd` lines warn when either is missing, since only `record terminal` needs them; the fix is `brew install vhs` (which brings ttyd) with a warning that Homebrew may upgrade ffmpeg too, and doctor never runs it, not even with `--fix`.

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
* `--kind [talk|product]`: talk (a talking-head video) or product (from screen recordings).  [default: talk]
* `--json`: Print machine-readable JSON.
* `--help`: Show this message and exit.

```console
$ motion-studio new launch-day --from ~/Desktop/takes/ --title "Launch day"
$ motion-studio new launch-day --from take1.mov take2.mov broll.mp4 logo.png
$ motion-studio new launch --kind product --from demo.mp4 demo.markers.json post.png
```

The kind is written to `project.toml` as `[project] kind` and never changes or gets guessed from the footage (ADR 0004). A `project.toml` without one is a talk project. In a product project every video is a screen recording and ingest, analyze and the packed index follow the product layout; `words` exits 1 there.

## `motion-studio status`

Show each stage, which are stale, and the next command to run.

```console
$ motion-studio status [OPTIONS] {slug}
```

* `slug`: Project slug: lowercase letters, digits, hyphens.  [required]
* `--json`: Print machine-readable JSON.
* `--help`: Show this message and exit.

The first line names the project's kind, as in `launch (product): 2 clip(s) in raw/`. Stages are `ingest`, `analyze`, `plan`, `music`, `preview`, `check` and `final`; each is `pending`, `done`, `stale` (an input changed since it ran) or `failed`.

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

## Recording

## `motion-studio record web`

Run a recording script in headless Chromium; write raw/<name>.mp4 and its markers.

```console
$ motion-studio record web [OPTIONS] {slug} {script}
```

* `slug`: Project slug: lowercase letters, digits, hyphens.  [required]
* `script`: Recording script: an ES module (.mjs).  [required]
* `--name <str>`: Clip name in raw/; defaults to the script's file name.
* `--viewport <str>`: Browser viewport, WIDTHxHEIGHT.  [default: 1600x900]
* `--json`: Print machine-readable JSON.
* `--help`: Show this message and exit.

For product projects only; a talk project exits 1. The script drives the creator's product, not motion-studio's rendering, so writing it does not break the rule that the agent edits data. The recorder runs it in Node against headless Chromium at the viewport size (1600x900 fills a browser frame on a 1920-wide canvas at 1:1, with room to zoom), captures the page through the Chrome DevTools screencast as JPEG frames at quality 95 with their timestamps, and encodes `raw/<name>.mp4` at a constant 30 fps (H.264, CRF 12) together with its markers sidecar `raw/<name>.markers.json` (see [the markers sidecar](#the-markers-sidecar)). The screencast only sends a frame when the page changes, so a page waiting on slow work holds its last frame for as long as the wait lasts and the edit can cut it at the markers. Nothing needs macOS screen-recording permission. Run `ingest` next.

A script that throws, or ends without opening a page, exits 1 with its error and the script's lines from the stack, and adds nothing to `raw/`. An existing `raw/<name>.mp4` or sidecar exits 1; pass `--name` for another take. Missing Node, Playwright or its Chromium exits 2 with the `setup --record` hint. Recording refuses to start (exit 1) while another command holds a heavy model (speech-to-text, faces or music), since a busy machine drops frames; it does not take that lock itself.

The script's default export receives the helper library, `r`:

```js
// takes/brief.mjs
export const contextOptions = { storageState: 'demo-kit/state.json' }; // optional, for newContext

export default async function take(r) {
  await r.goto('http://localhost:5173/new');          // the first page starts the capture once loaded
  await r.mark('new_page');
  await r.type('textarea', 'Write a post about ADRs', { delay: 30 });
  await r.click('button:has-text("Write the post")', { park: 'main' });
  await r.mark('brief_sent');
  await r.page.getByText('V1').waitFor({ timeout: 60_000 });   // slow work keeps recording
  await r.mark('v1_shown', { post: '[data-testid=post]', hook: r.page.getByText('Most developers').first() });
  await r.park('[data-testid=post]');
  await r.wait(2000);
}
```

| Helper | What it does |
|---|---|
| `r.goto(url, options?)` | Open a page (`page.goto` with `waitUntil: 'load'`). The first one starts the capture. |
| `r.startCapture()` | Start the capture on the page as it is, for a script that loads it another way. |
| `r.moveTo(target, {offset, ms, park}?)` | Glide the fake cursor to an element's centre (plus `offset: {x, y}`) or to a point `{x, y}`, eased in and out over `ms` (default from the distance, 300 to 1100 ms). |
| `r.click(target, {offset, ms, park}?)` | Glide there and click; the cursor shrinks and a ripple spreads under it. |
| `r.type(target, text, {delay, park}?)` | Click `target` (or skip with `null`) and type key by key, `delay` ms apart (default 45). |
| `r.press(key, {park}?)` | Press one key, such as `Enter`. |
| `r.park(region, {margin}?)` | Move the cursor just outside `region` plus `margin` pixels (default 60), along the shortest way that stays on screen. A cursor already clear stays put. |
| `r.mark(name, elements?)` | Record marker `name` now, on the clip's clock, and the on-screen box of each element in `{name: target}`. Await it. The take fails when an element is not visible or a name repeats. |
| `r.wait(ms)` | Wait while the capture runs. |
| `r.page`, `r.context` | The Playwright page and browser context, for waits and anything the helpers do not cover. |
| `r.viewport`, `r.cursor` | The viewport size, and where the cursor is now. |

A target is a CSS or Playwright selector string, a Playwright `Locator`, or a box `{x, y, w, h}` in viewport pixels (a point `{x, y}` for `moveTo` and `click`). A selector must match one element. `park` on `moveTo`, `click`, `type` and `press` parks off that region after the action, so the cursor never rests on the text the shot is about. Marker and element names use letters, digits, `_` and `-` and become IDs: `c2.m.v1_shown`, `c2.e.post`. The fake cursor is part of the page, so it shows in the frames, and every move and press goes into the sidecar's cursor track.

```console
$ motion-studio record web launch takes/brief.mjs
$ motion-studio record web launch takes/brief.mjs --name brief-take2
```

## `motion-studio record terminal`

Run a vhs tape in a clean shell; write raw/<name>.mp4 and its markers.

```console
$ motion-studio record terminal [OPTIONS] {slug} {tape}
```

* `slug`: Project slug: lowercase letters, digits, hyphens.  [required]
* `tape`: vhs tape (.tape), with Launch and Mark lines.  [required]
* `--name <str>`: Clip name in raw/; defaults to the tape's file name.
* `--size <str>`: Terminal frame, WIDTHxHEIGHT, both even.  [default: 1600x900]
* `--cwd <path>`: Folder the shell starts in; defaults to the tape's folder.
* `--json`: Print machine-readable JSON.
* `--help`: Show this message and exit.

For product projects only; a talk project exits 1. It records a real CLI session, such as Claude Code using an MCP server, from a [vhs](https://github.com/charmbracelet/vhs) tape. Like a recording script, the tape drives the creator's product, so writing it does not break the rule that the agent edits data. The recorder wraps the tape in one it generates:

1. Its own `Output`, `Set Shell bash`, `Set Width`/`Height` from `--size` and `Set Framerate 30`, then the tape's leading `Set` and `Require` lines.
2. A hidden preamble. The shell starts in `--cwd` with every inherited `CLAUDE*` variable, `VIRTUAL_ENV` and `PROMPT_COMMAND` removed (and unset again in the shell), a plain `❯ ` prompt and a cleared screen.
3. The `Launch` command, also hidden: the recorder puts a wrapper named after the command first on `PATH`, so the screen shows only `❯ claude`, never the arguments, paths or keys. For `claude` it waits 7 s, accepts the folder-trust prompt (which focuses "No, exit") with Down and Enter, and waits 5 s more; in an already trusted folder those keys do nothing. Any other command gets 2 s.
4. The rest of the tape, on camera.

vhs writes the terminal's frames and the recorder encodes them unscaled into `raw/<name>.mp4`: 30 fps constant frame rate, H.264 CRF 12, the terminal centred on a `--size` frame filled with the theme's background. vhs's own video settings (`WindowBar`, `Margin`, `BorderRadius`) do not apply; the renderer's terminal device frame draws the window. The markers sidecar `raw/<name>.markers.json` (see [the markers sidecar](#the-markers-sidecar)) has the frame size and one marker per `Mark` line, timed to the frame on screen when vhs reached it, with no element boxes and no cursor track. Run `ingest` next.

The tape is ordinary vhs, plus two lines the recorder consumes:

| Line | What it does |
|---|---|
| `Launch <command> [args...]` | Start the command in the hidden preamble through a short wrapper. At most one, before every command but `Set` and `Require`. A command with a `/` and any argument naming an existing file are relative to the tape's folder and passed as absolute paths; a bare command is looked up on `PATH`. |
| `Mark <name>` | Record marker `name` at this point of the tape. Names are unique and use letters, digits, `_` and `-`, so `Mark v1_shown` becomes `c2.m.v1_shown`. A `Mark` between `Hide` and `Show` exits 1. |

```
# takes/terminal.tape
Set FontSize 24
Set Theme "Catppuccin Mocha"
Set TypingSpeed 28ms
Launch claude --strict-mcp-config --mcp-config demo-kit/own-mcp.json --allowedTools 'mcp__pumpkit__*'
Mark ready
Type "Write a post with pumpkit: ship it in a week"
Enter
Mark brief_sent
Sleep 50s
Mark v1_shown
Type "Make the hook punchier"
Enter
Sleep 50s
Mark v2_shown
```

Keep keys in files passed by path, such as an MCP config for `--mcp-config`; the path stays inside the wrapper. Claude Code shows the folder it runs in, so pass a `--cwd` with a clean name (not a scratchpad). Use fixed `Sleep`s for model calls rather than `Wait`, whose screen regexes break as the output scrolls; the edit cuts the waits at the markers. `Mark` and `Launch` only work in the tape itself, not in a `Source`d one.

The tape's own `Output`, or a `Set` of `Shell`, `Framerate`, `Width` or `Height`, exits 1 naming the line, as do a bad `Mark` or `Launch` and anything `vhs validate` rejects (with its message, on the tape's line numbers). A tape that fails while running exits 1 with vhs's output, and an existing clip exits 1 as for `record web`; nothing is added to `raw/`. Missing `vhs` or `ttyd` exits 2 naming them with the install line; `doctor` lists both and never installs them, since Homebrew's `brew install vhs` can upgrade ffmpeg as a side effect. Recording refuses to start while another command holds a heavy model, as `record web` does.

```console
$ motion-studio record terminal launch takes/terminal.tape --cwd ~/pumpkit-demo
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

In a product project every video is a screen recording (role `screen`, IDs `c1`, `c2`, ...). It gets a mezzanine but no voice files, and ingest draws it once at one frame per second into `contact/<id>.png`; that sheet does not count against the look budget. A recording longer than 180 s is drawn in 180 evenly spaced frames, with a warning. A `<name>.markers.json` file in `raw/` is the markers sidecar of the clip `<name>.<ext>` beside it, not a clip of its own.

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

In a product project analyze loads no speech-to-text or face model and writes no `retakes.json`. For each screen recording it finds shots and static stretches and reads its markers sidecar, if there is one. `packed.md` then lists each recording's length, frame size, markers (`c1.m.<name>`), the element boxes captured at each marker (`c1.e.<name> x,y wxh`, in mezzanine pixels) and static stretches. A recording without a sidecar says so; it can only be addressed in source seconds.

### The markers sidecar

The recorders write it, and you can write one by hand for footage you bring. `schemas/markers.schema.json` is its contract. Times are seconds from the clip's first frame; boxes and the cursor are pixels of a `width` x `height` frame, the size the clip was recorded at, and analyze scales them to the mezzanine. Marker names are unique, element names are unique within a marker, and both use letters, digits, `_` and `-`. A sidecar that does not validate makes analyze exit 1 naming the file and the problem.

```json
{
  "schema_version": 1,
  "width": 1600,
  "height": 900,
  "markers": [
    {"name": "brief_sent", "t": 2.4},
    {"name": "v1_shown", "t": 9.8, "elements": [{"name": "post", "x": 420, "y": 180, "w": 760, "h": 300}]}
  ],
  "cursor": [{"t": 0.0, "x": 800, "y": 450}, {"t": 2.3, "x": 1210, "y": 640, "down": true}]
}
```

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

`words` is for talk projects; on a product project it exits 1 and points to the markers in `packed.md`.

## `motion-studio look`

Draw T0 to T1 of CLIP (frames, waveform, words, faces), or stills of the render with --at.

```console
$ motion-studio look [OPTIONS] {slug} [clip] [t0] [t1]
```

* `slug`: Project slug: lowercase letters, digits, hyphens.  [required]
* `clip`: Clip ID, e.g. c1.
* `t0`: Start, in source seconds.
* `t1`: End, in source seconds.
* `--at <str>`: A scene ID, marker or output time of the latest render; repeat for more stills.
* `--frames <int>`: Frames across the range.  [default: 8]
* `--out <path>`: Write the PNG here instead of contact/.
* `--json`: Print machine-readable JSON.
* `--help`: Show this message and exit.

Pass either a source range (`clip`, `t0` and `t1`) or `--at`, not both. `--frames` and `--out` apply to the range.

`--at` writes one still of the latest render per value, to `contact/at_<value>.png`, at the render's resolution up to 1600 px wide. The latest render is whichever of the preview and the final was rendered last; its first format is used. Each value is one of:

* a scene ID (product projects), such as `step1`: the scene's middle frame;
* a marker of a screen recording, such as `c2.m.v1_shown`: the frame where a footage scene shows that moment of the recording, at the scene's rate (the first such scene when several play it);
* output seconds, such as `12.5` or `12.5s`: the frame on screen then.

The stills print with their frame number, output time and scene. With no render, or one older than `build/timeline.json`, `--at` exits 1 and points to `render`; a marker no footage scene shows exits 1 and names the scenes that play its recording.

Each `look` call counts once against the look budget (`[edit] look_budget`, default 8), whatever the number of `--at` values. Past it, `look` still writes the sheet or the stills and prints a warning.

```console
$ motion-studio look talk c1 12.0 18.5 --frames 6
$ motion-studio look launch --at step1 --at c2.m.v1_shown --at 21.5
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

On a product project the EDL holds `scenes` (`"kind": "product"`, see `docs/edl.md`), and the summary prints the scene count, the duration, the beat grid the scenes sit on (120 bpm until `music` has written a bed, then the bed's beats) and the count of each scene type:

```console
$ motion-studio plan validate launch
✓ edl.json valid · product · 3 scenes · 16x9
Duration 7.0s (limit 60s) · grid 120 bpm, steady (no music yet)
Scenes: 2 title_card · 1 footage
→ projects/launch/build/timeline.json
```

`--json` adds `grid` (`bpm`, `beats_per_bar`, `from_music`) and `scene_types`. Run it again after `music` so the scenes move onto the bed's beats.

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

The mode, prompt, BPM and seed come from the EDL's `music` block, falling back to `[music]` in the config. `generate` needs `motion-studio setup --music` and retries up to three seeds when the bed has vocals. `library` picks a licensed track from `library/music/tags.json` and refuses one without a licence. `none` removes the bed. Every generated bed is shaped for laptop and phone speakers (a high-pass at 35 Hz, a 4 dB low-shelf cut at 120 Hz, 3 dB of presence at 3 kHz and of air above 7 kHz, gentle compression); a library track is left as licensed. `build/music.json` records the prompt, seed, model, licence and BPM, and the bed's analysis (schema: `schemas/music.schema.json`). Times are seconds from the start of the bed, which is output time zero. Run `plan validate` again afterwards so overlays snap to the beats.

* `detected_bpm`: the measured tempo. librosa's estimate (`tracker_bpm`) comes from coarse bins, so motion-studio refines it within 4% against the onsets, then cross-checks it against the period of the section changes: when the changes put the bars more than 1.5% apart from the onset tempo, they win. `tempo_from` says which (`onsets` or `sections`), and the command prints the correction.
* `beats` and `bars`: the beat grid on the corrected tempo, every beat and every downbeat up to the end of the timeline (`beats_per_bar` is 4). The downbeat is the beat most section changes fall on.
* `sections`: the whole bed cut where its band levels change for at least a bar, in order, each with `start_s`, `end_s` and `energy_db` (its level against the loudest section, which is 0). Changes are snapped to the nearest bar line within a beat, else to the nearest beat. Trailing silence is left out.
* `hits`: named section hits, each with `name` and `time_s`, listed only when the bed has them. `intro_end` is the end of the first section, `drop` the start of the loudest section, `build` the start of the section before the drop when an intro precedes it, and `ending` the start of the last section when it comes after the drop and is at least 3 dB quieter, else the point where the music falls silent.

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

A product project renders in 16x9 only, with no A-roll to cut: Remotion's `Product` composition draws each scene on the brand's backdrop (`[brand] primary` and `accent`, the caption font), title cards with their step number, headline and subline, and footage in a browser frame. The render has no voice, so the mix carries the music bed alone, and `cuts_s` lists the scene starts.

Every final also gets a share copy, `final/<slug>_<format>_share.mp4`, for both project kinds: the final at its own resolution, under 30 MiB and with `+faststart`, so it can be sent through chat tools and opened on a phone. A final already under 30 MiB is copied as it is, so the name is always there; a larger one has its video re-encoded at the bitrate that fits (two-pass x264) and its mastered audio copied. Render prints each share copy's path and size. A change to the share copy alone redoes the share copies without rendering the finals again. A final too long to fit (more than about seven minutes, with the default 320 kb/s audio) fails with exit 1 after the final itself is written; send the final or shorten the edit.

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
