# EDL reference

`projects/<slug>/edl.json` is the edit. You write it; `motion-studio plan validate <slug>` checks it, resolves it to `build/timeline.json` and prints a short summary. You never write times for cuts: you name words and utterances by ID and motion-studio does the arithmetic.

`motion-studio plan draft <slug>` writes a baseline to start from. The JSON Schema is `schemas/edl.schema.json` in the motion-studio repository.

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
