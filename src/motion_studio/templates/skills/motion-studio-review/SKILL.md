---
name: motion-studio-review
description: How to read motion-studio check reports and turn user feedback on a preview into precise EDL changes. Use after rendering, when motion-studio check reports issues, or when the user comments on a preview ("cut the intro", "more zooms", "music too loud").
---

# Review and feedback

`motion-studio check <slug> --preview` (or `motion-studio check <slug> --final`) writes `check/report.md` and `check/cuts.png`, and exits 1 when anything blocks. The report gives each blocking issue with a fix in EDL terms; apply it, then `motion-studio plan validate <slug>`, render and check again.

## Reading check/report.md
- **Clipped cut**: a word near a cut went missing. Extend the segment's `to` by one word, raise `pad_out_ms` (or `pad_in_ms`) in the EDL `policy`, or remove the offending ID from `drop_words`.
- **Over length**: remove the weakest supporting segment; keep the hook and payoff.
- **Loudness or true peak off target**: blocking on `--final`, a warning on a preview. Mastering is automatic, so lower `music.gain_db` when there is a bed and re-render. If it persists, report it to the user as a motion-studio bug.
- **Black or frozen frames**: check the B-roll `asset_in_s` and the event durations against the asset's length.
- **Caption density**: too many words per second on screen. Slow the pace (raise `max_pause_ms`) or cut words.
- View `check/cuts.png` once per loop. Look for faces cut off, captions colliding with titles, and awkward mouth-open frames at cuts (shift the cut by one word).

## Product videos
A product video is music only, so `check` re-transcribes nothing and reports no clipped cuts. It writes `check/contact.png` (one frame per second, stamped with output time) beside `check/cuts.png` (both sides of every scene cut). View both once per loop.
- **Loudness far below target** (around −70 LUFS) on a product video means it has no music: `"mode": "none"` renders silence. Add a bed; it is not a motion-studio bug.
- **Small speaker** blocks here, on previews too: the mix is bass-heavy and sounds near silent on a laptop. Ask for brighter instruments in `music.prompt` (or a brighter library track), run `music` again and re-render.
- **Masked regions** lists each mask with its scene, box and frames, and a `look --at` command for its middle frame. Run the ones you doubt and confirm the mask covers the leak with nothing left at its edges; widen the box or stretch its `start` and `end` if not.
- **Cursor over target** (a warning): the recorded cursor sits on a highlight's target. Start the highlight after the cursor leaves, or record the take again with `r.park(...)` after the action.
- **Black or frozen frames** inside a title card, kinetic text, proof or outro are intended and not reported; inside footage, check the scene's `from` and `to` against the recording.
- **Over length** names the longest scenes between the intro and the outro: shorten those footage spans or raise `rate`.
- For any moment the sheets leave unclear: `motion-studio look <slug> --at <scene | marker | seconds>`.

| User says | Change |
|---|---|
| "too slow" | Raise `rate` on typing and waiting spans, shorten footage `to`, title cards to 2 beats |
| "can't read it" | Add a camera move targeting the element, or hold it longer before the next move |
| "what am I looking at?" | A `caption_pill` on the scene, or a `highlight` with a `label` |
| "that shouldn't be on screen" | A `mask` over it for the frames it shows |
| "music doesn't hit" | `music.align` the `drop` on the scene that should land on it |

## Translating feedback into the EDL (talk projects)
| User says | Change |
|---|---|
| "start stronger" / "hook is weak" | Pick a different hook utterance; move it first |
| "too slow" | Lower `max_pause_ms` (min 200), drop soft fillers, cut a supporting point |
| "too choppy" | Raise `max_pause_ms` to 450–550, set `jumpcut_punch` false, fewer zooms |
| "more dynamic" | Add zooms on numbers and punchlines, B-roll or titles every 3–4 s. Never switch the captions to `pop` or `karaoke`: keep the caption style as it is |
| "music too loud" | Lower music `gain_db` by 3–4 dB |
| "different music" | New `seed` (same vibe) or new `prompt` |
| "remove X" | Find the utterance in packed.md, then split the segment around it or leave it out |
| "no captions over the B-roll" | Set `"captions": {"hide_during_broll": true}` (full-frame B-roll and images only) |

Record the feedback and how you applied it in `notes.md` so it carries over to the next video.
