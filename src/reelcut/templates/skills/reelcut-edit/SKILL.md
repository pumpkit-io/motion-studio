---
name: reelcut-edit
description: End-to-end workflow for editing raw talking-head footage into short social videos (Instagram Reels, X) with reelcut. Use whenever the user asks to edit, cut, trim or produce a video, reel or short from files in a reelcut workspace.
---

# Editing a video with reelcut

Run every command from the workspace root. Each command prints the paths it wrote; add `--json` when you want to parse the result. Exit codes: 0 OK, 1 a fixable EDL or input error (read the message and its hint, fix, rerun), 2 a missing dependency (run `reelcut doctor` and tell the user what it reports), 3 an internal error (report it to the user with the message).

## 0. Orient
- `reelcut status <slug>`. If the project does not exist, create it with `reelcut new <slug> --from <paths>`. If it reports 0 clips in `raw/`, ask the user to copy their takes into `projects/<slug>/raw/` and wait; files added there later are picked up by `reelcut ingest <slug>`.
- Read `projects/<slug>/notes.md` if it exists, and the effective config (`reelcut config show <slug>`).
- Note the user's requests: target length, formats, tone, must-keep lines, CTA.

## 1. Prepare (skip stages that `status` reports as done)
- `reelcut ingest <slug>`, then `reelcut analyze <slug>`.

## 2. Understand
- Read `projects/<slug>/analysis/packed.md` in full, and `analysis/assets.md`.
- For each B-roll or image asset, view its contact sheet (`reelcut look-asset <slug> <asset-id>`) and write a one-line description into `assets.md`.
- Identify the core message, the strongest hook candidates, retake winners, tangents and the CTA.

## 3. Plan
- `reelcut plan draft <slug>`, unless `edl.json` already exists from earlier work; then build on it.
- Edit `projects/<slug>/edl.json` following the `reelcut-plan` skill: choose the hook, order the segments, trim, drop soft fillers where they hurt, add emphasis, zooms, B-roll and titles, set the music block, and write a short `rationale`.
- `reelcut plan validate <slug>`. Fix every error; resolve warnings unless they are deliberate.
- GATE (plan): if `[review] plan` is true or the user asked to review, present the hook line, duration, structure (one line per segment) and what was cut, then wait.

## 4. Music
- `reelcut music <slug>`. Follow `reelcut-music` for the prompt.

## 5. Preview and self-check
- `reelcut render <slug> --preview` renders every format in the EDL.
- `reelcut check <slug> --preview`, then view `check/cuts.png`. Fix blocking issues by editing the EDL (see `reelcut-review`), validate, render and check again. Stop after 3 loops and report what remains.
- GATE (preview): if `[review] preview` is true or the user asked to review, give the preview paths plus a 3-line summary and wait. Apply feedback with `reelcut-review`.

## 6. Final
- `reelcut render <slug> --final`, then `reelcut check <slug> --final`.
- Deliver: the final file paths, duration, hook line, the music used (prompt and seed, or track and licence) and anything the user should know.
- Update `projects/<slug>/notes.md` with decisions, feedback and lessons.
