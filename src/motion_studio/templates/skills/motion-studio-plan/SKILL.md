---
name: motion-studio-plan
description: Editorial rules and EDL authoring reference for motion-studio talk projects, covering how to pick hooks, retakes and cuts, pace a talking-head short, and place zooms, B-roll, titles, emphasis and captions. Use when writing or revising the edl.json of a talk project.
---

# Planning the edit

These rules are for talk projects. A product project's scenes are covered in `motion-studio-product`.

## Priorities (in order)
1. **Hook in the first 2–3 seconds.** Open with the most specific, surprising or painful claim that makes sense on its own: a number, a bold statement, a result, a question. Moving a later line to the front is normal. Open on substance; greetings, "so", "allora" and "today I want to…" belong cut.
2. **One idea per video.** Cut tangents, repeated explanations and caveats that don't change the message.
3. **Best take wins.** In a retake cluster prefer complete > fluent (fewer fillers, no restarts) > later take. If two takes are equally clean but differ in energy, view both with one `motion-studio look` sheet each and choose the more expressive delivery.
4. **Pace.** Remove dead air (`max_pause_ms` handles most of it). Keep a natural breath before punchlines. Target 2.5–3.5 words/s overall.
5. **End with a payoff or CTA**, then stop. No outro waffle.
6. **Length.** Respect `max_duration_s`. If over, cut the weakest supporting point, never the hook or payoff.

## Fillers
- Hard fillers (`{ehm#…}`, `{um#…}` in packed.md) are removed by policy. Keep one only if removing it breaks a natural rhythm (add its ID to `keep_words`).
- Soft fillers (`~tipo~`, `~like~`, `~cioè~`, `~allora~`) are judgement calls: drop them when they are verbal tics; keep them when they carry meaning ("tipo 3 ore" = "about 3 hours"). Get their IDs with `motion-studio words <slug> <ref-from> <ref-to>`.
- `⟂` marks unaligned voice. Inside a kept segment it is usually a mumble or breath: drop it with `drop_ranges` if it sits inside a sentence.

## Visual rhythm
- Something should change on screen every 2–4 seconds: a cut, a punch-in, B-roll, a title or an image.
- `zoom` (`snap`, 1.12–1.2) on the key word of a punchline or a number, about one per 8–10 s.
- `push` (1.04–1.08) on a calm explanatory segment.
- Jump-cut punch is automatic; manual zooms are for emphasis, not for every cut.
- B-roll and images cover what is being *described* (product, screen, result). `full` for strong visuals, `pip` when the face matters. 2–5 s each, start and end anchored to words.
- `title`: at most 5 words, for the core claim or a number transformation ("3h → 10 min").
- `emphasis`: at most 1–3 words per sentence: numbers, contrasts, the key noun.

## Captions
- Leave the caption style at the config default: omit `captions.style` from the EDL.
- Set `"style": "pop"` or `"karaoke"` only when the creator asks for animated captions by name.
- Keep `max_words_per_page` at 3 or below, so a caption page holds two or three words.

## Language
- Keep the speaker's language. Titles go in the same language as the speech.
- Italian: watch for soft fillers at utterance starts (allora, cioè, praticamente) and false starts like "il… il motivo".

## Formats
- `9x16` is the main deliverable. `16x9` for X reuses the same EDL (vertical sources are shown fit-blur). Make one edit for all formats unless the user asks for separate ones.

## EDL reference
`motion-studio docs edl` prints the full reference. Essentials:
- `segments[]` in output order; `from` and `to` are utterance refs (`c1.s4`) or word refs (`c1.w52`) in the same clip. An utterance in `from` means its first word, in `to` its last word.
- `drop_words[]`, `keep_words[]`, and `drop_ranges[]` (`{clip, start, end}` in source seconds).
- `events[]`: `zoom`, `push`, `broll`, `image`, `title`, `emphasis`. Anchors (`at`, `start`, `end`, `hold_until`, `from`) are word, utterance or segment IDs and follow the speech when cuts change.
- `policy` overrides the `[edit]` config for this video (`pad_in_ms`, `pad_out_ms`, `max_pause_ms`, `drop_fillers`, `jumpcut_punch`).
- `music`: `mode` plus `prompt`, `bpm`, `seed`, `gain_db` (see `motion-studio-music`).
- Always fill `rationale` (1–3 sentences).
