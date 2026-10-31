---
name: motion-studio-look
description: When and how to look at footage with motion-studio contact sheets without wasting tokens. Use when a decision depends on what is visible, such as choosing between takes by delivery, checking framing, describing B-roll, or verifying a cut.
---

# Looking at footage

You read video as text; `motion-studio look <slug> <clip> <t0> <t1>` is your one window onto the picture. It writes one PNG (times in seconds): frames across the range, the waveform, the words with timing (hard fillers red, soft fillers orange) and face boxes. It prints the path; open the PNG and inspect it. The sheet has 8 frames unless you pass `--frames`.

Use it for:
- comparing two equally clean retakes (one sheet per candidate: `motion-studio look <slug> <clip> <t0> <t1> --frames 6`);
- checking a `static` stretch ("is anything happening?") before cutting it;
- describing B-roll and images with `motion-studio look-asset <slug> <asset-id>`, once per asset;
- verifying a suspicious cut flagged by `motion-studio check` (view `check/cuts.png` first).

Routine cuts need only the transcript. Keep each range short (20 s at most); split a long range into the moments that matter.

Budget: `look_budget` sheets per project (default 8). Past it, motion-studio warns but still draws the sheet; continue only when the decision really needs it, and say why in `notes.md`.
