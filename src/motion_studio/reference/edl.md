# EDL reference

`projects/<slug>/edl.json` is the edit. You write it; `motion-studio plan validate <slug>` checks it, resolves it to `build/timeline.json` and prints a short summary. You never write times for cuts: you name words and utterances by ID and motion-studio does the arithmetic.

`motion-studio plan draft <slug>` writes a baseline to start from. The JSON Schema is `schemas/edl.schema.json` in the motion-studio repository.

There are two kinds of EDL, one per project kind. A talk EDL (`kind` left out, or `"talk"`) keeps words in `segments`; it is described first. A product EDL (`"kind": "product"`) lays out `scenes` and has its own section, [Product EDLs](#product-edls), below. The shared top-level fields mean the same in both.

## IDs

| ID | Means | Where to find it |
|---|---|---|
| `c1.s4` | Utterance 4 of clip c1 | `analysis/packed.md` |
| `c1.w52` | Word 52 of clip c1 (numbered across the whole clip) | `motion-studio words <slug> c1.s4` |
| `hook` | A segment you named | your own `segments[].id` |
| `b1`, `i1` | A B-roll clip, an image | `analysis/packed.md` header, `project.toml` |

## Example

```json
{
  "schema_version": 1,
  "title": "How I built it in two weeks",
  "language": "en",
  "formats": ["9x16", "16x9"],
  "max_duration_s": 60,
  "policy": { "max_pause_ms": 350, "drop_fillers": "hard", "jumpcut_punch": true },
  "segments": [
    { "id": "hook", "from": "c1.s2", "to": "c1.s2", "note": "pain-point hook" },
    { "id": "body1", "from": "c1.s0", "to": "c1.w9" },
    { "id": "cta", "from": "c2.s3", "to": "c2.s3" }
  ],
  "drop_words": ["c1.w5"],
  "drop_ranges": [{ "clip": "c1", "start": 22.3, "end": 22.7 }],
  "keep_words": [],
  "events": [
    { "type": "zoom", "at": "c1.w52", "scale": 1.18, "hold_until": "c1.w58", "ease": "snap" },
    { "type": "push", "from": "body1", "scale": 1.06 },
    { "type": "broll", "asset": "b1", "start": "c1.w70", "end": "c1.w84", "asset_in_s": 2.0, "mode": "full" },
    { "type": "image", "asset": "i1", "start": "c1.w90", "end": "c1.w97", "mode": "pip", "motion": "kenburns" },
    { "type": "title", "text": "3 hours → 10 minutes", "start": "c1.w101", "end": "c1.w110" },
    { "type": "emphasis", "words": ["c1.w103", "c1.w106"] }
  ],
  "captions": { "enabled": true, "style": "pop" },
  "music": { "mode": "generate", "prompt": "minimal electronic, warm synths, confident, instrumental", "bpm": 104, "seed": 7, "gain_db": -20 },
  "rationale": "Hook = the strongest pain point; dropped the abandoned first take; CTA from the cleaner c2 retake."
}
```

## Top-level fields

| Field | Default | Meaning |
|---|---|---|
| `schema_version` | `1` | Always 1. |
| `kind` | `talk` | `talk` or `product`, the project's kind. |
| `title` | `""` | The video's title. |
| `language` | project language | Caption language: `en` or `it`. |
| `formats` | config `formats` | Any of `9x16`, `16x9`, `4x5`. One EDL serves every format. |
| `max_duration_s` | config | Over the limit is a warning, not an error. |
| `policy` | config `[edit]` | Trimming rules, below. |
| `segments` | required, at least one | What to keep, in output order. |
| `drop_words` | `[]` | Word IDs cut out of their segments. Utterance IDs are refused: list the words, or leave the utterance out of the segments. |
| `drop_ranges` | `[]` | `{clip, start, end}` in source seconds, for audio no word points at (the `⟂` unaligned voice in packed.md). |
| `keep_words` | `[]` | Word IDs kept although the policy drops them as fillers. `drop_words` wins over `keep_words`. |
| `events` | `[]` | Zooms, pushes, B-roll, images, titles and emphasis, below. |
| `captions` | config `[captions]` | `enabled`, `style` (`pop`, `clean`, `karaoke`), `max_words_per_page`, `uppercase`, `hide_during_broll` (true hides captions while a full-frame B-roll clip or image is on screen; default false). |
| `music` | config `[music]` | The music bed, below. |
| `rationale` | `""` | One to three sentences on why the edit is shaped this way. Always fill it. |

## Segments

`{ "id": "hook", "from": "c1.s2", "to": "c1.s2", "note": "..." }`

- `id` is any unique name that does not look like a word or utterance ID. Events can anchor to it.
- `from` is the first word kept: a word ID, or an utterance ID meaning its first word.
- `to` is the last word kept: a word ID, or an utterance ID meaning its last word.
- `from` and `to` must be in the same clip, and `from` must not come after `to`.
- The array order is the output order: moving the hook to the front is moving one entry.
- Two segments cannot keep the same word.
- `note` is free text for you.

## Policy

Every key is optional and overrides the config's `[edit]` section.

| Key | Default | Meaning |
|---|---|---|
| `pad_in_ms` | 80 | Kept before a run's first word. |
| `pad_out_ms` | 120 | Kept after a run's last word. |
| `max_pause_ms` | 350 | Longer pauses between kept words are cut down to this. |
| `min_segment_ms` | 400 | Shorter runs are dropped, with a warning. |
| `drop_fillers` | `hard` | `none`, `hard` (the `{ehm#…}` words) or `hard+soft` (also `~tipo~`, `~like~`). |
| `jumpcut_punch` | true | Alternate the base zoom at jump cuts so they read as deliberate. |
| `jumpcut_punch_scale` | 1.08 | Scale of the punched-in runs. |

## How a segment becomes runs

1. Keep the words from `from` to `to`, minus `drop_words`, words inside `drop_ranges`, and fillers the policy drops (unless in `keep_words`).
2. Split into runs wherever a word was removed or a pause is longer than `max_pause_ms` (the pause is cut down to `max_pause_ms`).
3. Pad each run by `pad_in_ms` and `pad_out_ms`, never past the midpoint to a removed neighbour and never past the clip.
4. Merge runs less than 150 ms apart; drop runs shorter than `min_segment_ms`, with a warning.
5. Snap to the frame grid and lay the runs end to end in segment order.

Speech cuts never move to match the music.

## Events

Each event names its kind in `type`. Anchors (`at`, `start`, `end`, `hold_until`, `from`) are word IDs, utterance IDs or segment IDs, and resolve to output time, so events follow the speech when cuts change. A start anchor means the start of that word, utterance or segment; an end anchor means its end. Anchoring to a word that is cut from the edit is an error that names the nearest kept word.

| Type | Fields | Meaning |
|---|---|---|
| `zoom` | `at`, `scale` (1.15), `hold_until` (end of `at`), `ease` (`snap` or `smooth`) | Punch in from the start of `at` to the end of `hold_until`. Replaces the jump-cut punch while active. |
| `push` | `from` (a segment ID), `scale` (1.06) | Slow push-in across the whole segment, from 1.0 to `scale`. |
| `broll` | `asset` (`b1`), `start`, `end`, `asset_in_s` (0), `mode` (`full` or `pip`) | B-roll from `asset_in_s` into the clip. `full` is a cutaway, `pip` a card over the speaker. Cut short, with a warning, when the clip runs out. |
| `image` | `asset` (`i1`), `start`, `end`, `mode` (`full`), `motion` (`kenburns` or `none`) | A still, with a slow Ken Burns move by default. |
| `title` | `text`, `start`, `end` | On-screen text. Keep it to five words or fewer. |
| `emphasis` | `words` (word IDs) | Those words are drawn in the accent colour in the captions. |

Two full-frame overlays (`broll` or `image` with `mode: full`) cannot overlap: that is an error. A title over an overlay is a warning. Once music exists, B-roll and image starts snap to the nearest beat within 80 ms.

## Music

| Key | Meaning |
|---|---|
| `mode` | `generate` (local, from `prompt`, `bpm` and `seed`), `library` (a licensed track from `library/music/tags.json`) or `none`. |
| `prompt` | Genre, instrumentation, mood and energy. Always include "instrumental". |
| `bpm` | From the pace in the validate summary: under 2.3 words/s 85–95, 2.3–3 words/s 96–110, over 3 words/s 112–124. |
| `seed` | Change it for a variation of the same mood. |
| `gain_db` | −20 (calm) to −16 (energetic). Ducking under the voice and loudness are automatic. |
| `track` | The library track, for `mode: library`. |

Unset keys fall back to the config's `[music]`.

## Errors and warnings

Validate lists every problem at once, each with a fix, and exits 1 when any is an error. `--json` gives each as `{code, message, hint}`.

Errors: `invalid_edl` (a field fails the schema), `bad_ref`, `unknown_ref`, `cross_clip`, `reversed_range`, `duplicate_segment`, `bad_segment_id`, `overlapping_segments`, `bad_drop_range`, `unknown_language`, `dropped_anchor`, `event_range`, `bad_asset`, `overlay_overlap`.

Warnings: `short_run`, `empty_segment`, `drop_and_keep`, `too_long`, `asset_short`, `title_over_broll`.

## Product EDLs

A product video is scenes back to back, in output order: kinetic text, title cards, footage of screen recordings in a device frame, proof shots and a logo outro. Screen recordings have no words, so you point into them by marker (ADR 0005), and scene lengths are in beats or bars so cuts land on the music.

### IDs

| ID | Means | Where to find it |
|---|---|---|
| `c2` | Screen recording c2 | `analysis/packed.md` |
| `c2.m.v1_shown` | Marker `v1_shown` of c2, written by the recording script's `mark()` | under each screen recording in `analysis/packed.md` |
| `c2.e.hook` | Element `hook` of c2: an on-screen box the recording script captured at a marker | after its marker in `analysis/packed.md`, with its box |
| `intro` | A scene you named | your own `scenes[].id` |

### Example

```json
{
  "schema_version": 1,
  "kind": "product",
  "title": "Pumpkit launch",
  "scenes": [
    { "id": "intro", "type": "kinetic_text", "bars": 3, "lines": ["Got an idea?", "Turning it into a post…", "…is the hard part."], "accent": ["idea?", "hard"] },
    { "id": "step1", "type": "title_card", "beats": 2, "step": "01", "headline": "Pick who inspires you.", "accent": ["inspires"] },
    { "id": "pick", "type": "footage", "clip": "c1", "from": "c1.m.open", "to": { "marker": "c1.m.picked", "offset_s": 0.4 }, "rate": 1.8, "address": "pumpkit.io" },
    { "id": "brief", "type": "footage", "clip": "c2", "from": "c2.m.typing", "to": "c2.m.sent", "bars": 2,
      "camera": [
        { "at": "c2.m.typing", "target": "c2.e.brief" },
        { "at": "c2.m.sent", "target": "full", "ease": "snap" }
      ],
      "events": [
        { "type": "caption_pill", "text": "Write a brief. As long as you like." },
        { "type": "highlight", "target": "c2.e.brief", "start": "c2.m.typing", "end": "c2.m.sent", "label": "Your idea" },
        { "type": "mask", "target": { "x": 0, "y": 0, "w": 1600, "h": 60 } },
        { "type": "flash" }
      ] },
    { "id": "posted", "type": "proof", "bars": 2, "image": "i1", "headline": "Live on X.", "subline": "One click.", "badge": "Posted" },
    { "id": "mcp", "type": "footage", "clip": "c3", "from": "c3.m.start", "to": "c3.m.scheduled", "rate": 2.6, "device_frame": "terminal", "address": "claude: ~/pumpkit-demo" },
    { "id": "outro", "type": "logo_outro", "bars": 4, "tagline": "Write like the people you admire.", "url": "pumpkit.io" }
  ],
  "music": { "mode": "generate", "prompt": "bright electronic launch, instrumental", "bpm": 120, "seed": 7 },
  "rationale": "Hook lines, one numbered step per recording, the published post, then the brand."
}
```

### Top-level fields

`schema_version`, `title`, `language`, `max_duration_s`, `captions`, `music` and `rationale` mean what they mean in a talk EDL. `kind` is `product`, and `scenes` (at least one) is the video in output order. `formats` may only be `["16x9"]`, the default: product videos render in 16x9 only.

### The beat grid

Scene lengths are `beats`, `bars` or `seconds`. Before music exists the grid is a steady 120 bpm with four beats to a bar; once `motion-studio music` has written the bed, its beats and bars are the grid, so run `plan validate` again after music. A scene in beats or bars ends on the nearest beat, even after a scene in seconds. Scene starts are whole output frames, with no gap between scenes.

### Scenes

Every scene has an `id` (unique), a `type`, a length (exactly one of `beats`, `bars` or `seconds`, except for footage, below), `events` (`[]`, below) and an optional `note`.

| Type | Fields | Meaning |
|---|---|---|
| `title_card` | `headline`, `accent` (`[]`), `step`, `subline` | A full-frame card that introduces a step: the `step` number (such as `"01"`) above, the `headline` springing in word by word with the `accent` words in the brand accent colour, and the `subline` smaller underneath. |
| `kinetic_text` | `lines`, `accent` (`[]`) | Lines that spring in word by word, one after another, each getting an equal share of the scene; `accent` words of any line are in the brand accent colour. Suits an intro with no footage. |
| `footage` | `clip`, `from`, `to`, `rate`, `device_frame` (`browser` or `terminal`), `address`, `camera` (`[]`) | A stretch of a screen recording in a browser window or a terminal window; `address` is the text in the browser's address bar or the terminal's title bar, and `camera` its camera moves (below). |
| `proof` | `image`, `headline`, `accent` (`[]`), `subline`, `badge` | An image clip (`i1`), such as a screenshot of the published post, that swings in in 3D. With a `headline` (and its `subline`) the text sits on the left and the image on the right; without one the image is centred. `badge` is a short stamp, such as `"Posted"`, that pops onto the image's corner. |
| `logo_outro` | `tagline`, `accent` (`[]`), `url`, `mascot` (`true`) | The brand's mascot and wordmark, the `tagline` under them and the `url` in a pill, fading to black at the end. It needs `[brand] wordmark`, and `[brand] mascot` unless `mascot` is `false`. |

A footage scene's `from` and `to` are each one of:

- a marker ID: `"c1.m.open"`;
- a marker with an offset: `{ "marker": "c1.m.open", "offset_s": 0.4 }` or `{ "marker": "c1.m.open", "offset_beats": -1 }`. `marker` is the marker ID, `offset_s` is seconds after it and `offset_beats` beats of the grid after it (negative is before; both add up);
- source seconds, such as `12.5`, only for a recording that has no markers (footage you brought in). Each such scene gets a warning.

A footage scene's length comes one of two ways. With `rate` (default 1) and no length, it plays from `from` to `to` at that speed and lasts that long, rounded to whole beats (at least one); the speed is adjusted slightly so the footage fills the scene. With a length, `from` to `to` is played at whatever speed fills it, and `rate` must be left out. Typing reads well at a `rate` of 2.6 to 3.2.

A logo outro draws two `[brand]` files from `motion-studio.toml` or `project.toml`: `wordmark`, an image path, and `mascot`, a sprite sheet and its frame-timing JSON (`mascot = { sheet = "library/brand/mascot.png", timings = "library/brand/mascot.json" }`). The timing JSON gives `frame_width` and `frame_height`, `frames` in playing order (each with its `x` and `y` in the sheet and `ms`, how long it shows) and `loops` (times the frames play before the last one holds; `0`, the default, loops forever). Sprites play at their own timings and are drawn without smoothing, so pixel art stays crisp. Paths are relative to the workspace; see `library/brand/README.md`.

### Camera moves

A footage scene's `camera` lists moves that direct attention. Until the first move the camera shows the whole frame. Each move has:

| Field | Default | Meaning |
|---|---|---|
| `at` | | When the move starts: a marker ID or a marker with an offset, as in `from` and `to` (source seconds on a recording without markers). It must fall between the scene's `from` and `to`. |
| `target` | | What to frame: an element ID (`"c2.e.hook"`), `"full"` for the whole footage, or a box `{ "x": 120, "y": 80, "w": 640, "h": 200 }` in the footage pixels `analysis/packed.md` lists (`x` and `y` the top-left corner, `w` and `h` the size). An element is boxed where it was captured at the marker nearest `at`. |
| `zoom` | fills 70% | 1 shows the whole frame. Left out, the target is framed to fill about 70% of the footage's width or height, never below 1 or past the limit. |
| `ease` | `smooth` | `smooth` eases to the target over about 0.7 s (cut short by the next move); `snap` cuts to it. |

The camera holds each move until the next one. The zoom limit is 2 on footage the frame shows 1:1 (1600x900, the `record web` and `record terminal` default, in a browser or terminal frame alike): past it, recorded text goes soft. Larger recordings can zoom further (4 at 3200x1800), smaller ones less (none at 800x450).

### Events on scenes

A scene's `events` lists overlays. `caption_pill` and `flash` go on any scene, at most one of each; `highlight` and `mask` only on footage, where they point into the scene's recording.

| Type | Fields | Meaning |
|---|---|---|
| `caption_pill` | `text` | A short line in a pill at the bottom of the frame, springing in after the cut and leaving with the scene. Say what is happening in a few words. |
| `flash` | `strength` | A white flash on the cut into the scene, fading out over 5 frames. `strength` (above 0, at most 1) is the opacity of its first frame: by default 0.35, or 0.12 on terminal footage, which a bright flash washes out. |
| `highlight` | `target`, `start`, `end`, `label` | An animated box in the brand accent colour around `target`, with an optional `label` tag of a few words. It is drawn on the footage, so it stays on its target while the camera moves. |
| `mask` | `target`, `start`, `end`, `color` | Fills `target` with `color` (default: the device frame's background, the browser page's grey or the terminal's) from `start` to exactly `end`, to hide a leaked path, a key or an off-message line. |

`target` is what a camera move takes: an element ID, `"full"` or a box in footage pixels; on a terminal recording, which has no elements, use a box. An element is boxed where it was captured at the marker nearest `start`. `start` and `end` are points on the recording's clock, as in `from` and `to`; they default to the scene's `from` and `to` and must fall between them.

### Product errors and warnings

Errors: `product_format` (a format other than 16x9), `duplicate_scene`, `scene_length` (no length, or more than one), `length_and_rate` (a footage scene with both), `unknown_accent` (an accent word that is not in the headline, tagline or any line), `unknown_image` (a proof scene's `image` is not an image clip), `missing_brand_asset` (a logo outro's `[brand] wordmark` or `mascot` is not set, names a file that does not exist, or has timings that do not parse; the message names the config key), `unknown_clip` (not a screen recording), `bad_marker` (not a marker ID), `unknown_marker`, `cross_clip` (a marker or element of another recording), `seconds_on_marked_clip` (source seconds on a recording that has markers), `reversed_range`, `outside_clip` (an offset past either end of the recording), `move_outside_scene` (a camera move's `at` outside the scene's footage), `bad_target` (a target that is no element ID, `full` or box), `unknown_element` (an element no marker captured), `target_outside` (a target box not inside the footage), `zoom_too_far` (a zoom past the limit), `event_needs_footage` (a highlight or mask on a scene that is not footage), `duplicate_event` (a second caption_pill or flash on one scene), `reversed_event` (an event's end not after its start), `event_outside_scene` (an event's start or end outside the scene's footage), `unknown_language`. A bad event target gives the camera's target errors.

Warnings: `seconds_addressed` (a footage scene in source seconds), `too_long`.
