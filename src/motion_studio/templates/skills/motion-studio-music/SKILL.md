---
name: motion-studio-music
description: How to choose or generate background music for a motion-studio edit, covering mood prompts for local ACE-Step generation, library picks, BPM and levels. Use when setting the music block of edl.json or when the user asks to change the music.
---

# Music

Default: local generation (`"mode": "generate"`). It runs offline and costs nothing. Its licence is the one recorded for the downloaded model weights; `motion-studio music <slug>` writes it into `build/music.json` with the prompt, seed, the measured BPM, the beat and bar grid, and the section hits (intro end, build, drop, ending).

## Writing the prompt
Describe genre, instrumentation, mood and energy, and always include "instrumental". Match the *content*, not the topic:
- confident tech or build-in-public: "minimal electronic, warm analog synths, soft punchy drums, confident, optimistic, instrumental"
- storytelling or reflective: "lo-fi piano, gentle vinyl texture, soft brushes, warm, reflective, instrumental"
- high-energy tips or lists: "upbeat indie electronic, plucky synths, driving four-on-the-floor, energetic, instrumental"
- serious or explainer: "ambient cinematic pads, subtle pulse, focused, calm, instrumental"

Keep melodies sparse: the music sits under speech. motion-studio rejects generated beds with vocals and retries with a new seed.

## BPM
Pick from the speech pace (`motion-studio plan validate` reports words per second): below 2.3 w/s → 85–95; 2.3–3 → 96–110; above 3 → 112–124.

## Levels
`gain_db` from −20 (calm) to −16 (energetic). Ducking under the voice and loudness mastering are automatic.

## Changing music
- Change `seed` for a variation of the same vibe; change `prompt` for a different vibe.
- `"mode": "library"` picks from `library/music/tags.json` by mood and BPM; only tracks with a recorded licence are used, and attributions go to `final/<slug>_credits.txt`.
- `"mode": "none"` publishes voice only.
- Rerun `motion-studio music <slug>` after changing the block, then render again.

Always tell the user what was used: prompt and seed, or track and licence or attribution.
