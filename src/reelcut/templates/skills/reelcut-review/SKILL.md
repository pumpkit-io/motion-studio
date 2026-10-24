---
name: reelcut-review
description: How to read reelcut check reports and turn user feedback on a preview into precise EDL changes. Use after rendering, when reelcut check reports issues, or when the user comments on a preview ("cut the intro", "more zooms", "music too loud").
---

# Review and feedback

`reelcut check <slug> --preview` (or `reelcut check <slug> --final`) writes `check/report.md` and `check/cuts.png`, and exits 1 when anything blocks. The report gives each blocking issue with a fix in EDL terms; apply it, then `reelcut plan validate <slug>`, render and check again.

## Reading check/report.md
- **Clipped cut**: a word near a cut went missing. Extend the segment's `to` by one word, raise `pad_out_ms` (or `pad_in_ms`) in the EDL `policy`, or remove the offending ID from `drop_words`.
- **Over length**: remove the weakest supporting segment; keep the hook and payoff.
- **Loudness or true peak off target**: blocking on `--final`, a warning on a preview. Mastering is automatic, so lower `music.gain_db` when there is a bed and re-render. If it persists, report it to the user as a reelcut bug.
- **Black or frozen frames**: check the B-roll `asset_in_s` and the event durations against the asset's length.
- **Caption density**: too many words per second on screen. Slow the pace (raise `max_pause_ms`) or cut words.
- View `check/cuts.png` once per loop. Look for faces cut off, captions colliding with titles, and awkward mouth-open frames at cuts (shift the cut by one word).

## Translating feedback into the EDL
| User says | Change |
|---|---|
| "start stronger" / "hook is weak" | Pick a different hook utterance; move it first |
| "too slow" | Lower `max_pause_ms` (min 200), drop soft fillers, cut a supporting point |
| "too choppy" | Raise `max_pause_ms` to 450–550, set `jumpcut_punch` false, fewer zooms |
| "more dynamic" | Add zooms on numbers and punchlines, B-roll or titles every 3–4 s |
| "music too loud" | Lower music `gain_db` by 3–4 dB |
| "different music" | New `seed` (same vibe) or new `prompt` |
| "remove X" | Find the utterance in packed.md, then split the segment around it or leave it out |

Record the feedback and how you applied it in `notes.md` so it carries over to the next video.
