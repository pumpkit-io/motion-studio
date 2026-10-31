# Recording the product

Both recorders write `raw/<name>.mp4` (30 fps constant frame rate) and its markers sidecar `raw/<name>.markers.json`, and work only in product projects. Neither needs macOS screen-recording permission. Both refuse to start while another command holds a heavy model (speech-to-text, faces or music), since a busy machine drops frames; wait for it to finish.

## Web: recording scripts

A recording script is an ES module (`.mjs`) whose default export receives the helper library `r`. `motion-studio record web <slug> <script.mjs>` runs it in headless Chromium at a 1600x900 viewport (`--viewport` changes it; 1600x900 fills the browser frame 1:1 and leaves room to zoom 2x). A script that throws exits 1 with its error and line, and adds nothing to `raw/`.

```js
// projects/launch/takes/brief.mjs
export const contextOptions = { storageState: 'demo-kit/state.json' }; // optional: a signed-in session, by path

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
| `r.goto(url, options?)` | Open a page and wait for `load`. The first one starts the capture. |
| `r.startCapture()` | Start the capture on the page as it is, for a script that loads it another way. |
| `r.moveTo(target, {offset, ms, park}?)` | Glide the fake cursor to an element's centre (plus `offset: {x, y}`) or a point `{x, y}`, eased over `ms`. |
| `r.click(target, {offset, ms, park}?)` | Glide there and click, with a ripple under the cursor. |
| `r.type(target, text, {delay, park}?)` | Click `target` (`null` to skip the click) and type key by key, `delay` ms apart (default 45). |
| `r.press(key, {park}?)` | Press one key, such as `Enter`. |
| `r.park(region, {margin}?)` | Move the cursor just outside `region` (plus `margin`, default 60 px). |
| `r.mark(name, elements?)` | Record marker `name` now, and the on-screen box of each element in `{name: target}`. Always `await` it. |
| `r.wait(ms)` | Wait while the capture runs. |
| `r.page`, `r.context` | The Playwright page and browser context, for waits and anything else. |
| `r.viewport`, `r.cursor` | The viewport size and the cursor's position. |

A target is a selector string (CSS or Playwright, matching one element), a Playwright `Locator`, or a box `{x, y, w, h}` in viewport pixels. `park` on an action parks the cursor off that region afterwards. Marker and element names use letters, digits, `_` and `-`, are unique, and become IDs: `c2.m.v1_shown`, `c2.e.hook`. A take fails when a marked element is not visible or a name repeats.

## Terminal: tapes

`motion-studio record terminal <slug> <file.tape> --cwd <folder>` runs a [vhs](https://github.com/charmbracelet/vhs) tape in a clean bash shell (needs `vhs` and `ttyd`; `motion-studio doctor` gives the install line, which can upgrade ffmpeg, so let the creator run it). The recorder adds a hidden preamble that clears inherited `CLAUDE*` variables, sets a plain `❯ ` prompt and, for `claude`, accepts the folder-trust prompt off camera. The tape is ordinary vhs plus two lines:

| Line | What it does |
|---|---|
| `Launch <command> [args...]` | Start the command off camera through a wrapper, so the screen shows only `❯ claude`, never its arguments, paths or keys. At most one, before every command but `Set` and `Require`. |
| `Mark <name>` | Record marker `name` here (not between `Hide` and `Show`). |

```
# projects/launch/takes/terminal.tape
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
```

- Leave out `Output` and `Set Shell`, `Framerate`, `Width` and `Height`; the recorder sets them (`--size`, default 1600x900).
- Pass keys inside files named by path, such as the MCP config above.
- Claude Code shows the folder it runs in: pass a `--cwd` with a clean name, such as `~/pumpkit-demo`, never a scratchpad.
- Wait for model calls with a fixed `Sleep`; the edit cuts the wait at the markers.
- Terminal markers carry no element boxes and no cursor, so camera targets, highlights and masks on terminal footage are boxes in footage pixels. Mask any line the product prints that is off-message.

## Footage that edits well

- Place a marker at every state change the edit might cut to or zoom on: before and after each action, and when a result appears.
- Capture the element the camera or a highlight will target at the marker where it matters (`r.mark('v2_shown', {hook: ...})`), so the EDL never needs coordinates.
- Park the cursor off the text the shot is about after each action; `check` warns when the cursor sits on a highlight's target. To highlight the button you just clicked, park off the button itself (`r.click(btn, {park: btn})`): parking off another region leaves a cursor that is already clear of it where it is, on the button.
- Read the product's components for its selectors (aria labels, test IDs) before the first take; it saves retries.
- Keep recording through slow work. A long wait costs nothing: the edit starts the next span at the marker after it.
- One recording per step of the story keeps each take short and each retake cheap.
