---
name: motion-studio-edit
description: End-to-end workflow for editing raw talking-head footage into short social videos (Instagram Reels, X) with motion-studio. Use whenever the user asks to edit, cut, trim or produce a video, reel or short from files in a motion-studio workspace.
---

# Editing a video with motion-studio

Run every command from the workspace root. Each command prints the paths it wrote; add `--json` when you want to parse the result. Exit codes: 0 OK, 1 a fixable EDL or input error (read the message and its hint, fix, rerun), 2 a missing dependency (run `motion-studio doctor`; when it lists a missing model or the renderer, `motion-studio doctor --fix` downloads it, otherwise tell the user what it reports), 3 an internal error (report it to the user with the message).

## 0. Orient
- `motion-studio status <slug>`. If the project does not exist, create it with `motion-studio new <slug> --from <paths>`. If it reports 0 clips in `raw/`, ask the user to copy their takes into `projects/<slug>/raw/` and wait; files added there later are picked up by `motion-studio ingest <slug>`.
- Read `projects/<slug>/notes.md` if it exists, and the effective config (`motion-studio config show <slug>`).
- Note the user's requests: target length, formats, tone, must-keep lines, CTA.

## 1. Prepare (skip stages that `status` reports as done)
- `motion-studio ingest <slug>`, then `motion-studio analyze <slug>`.

## 2. Understand
- Read `projects/<slug>/analysis/packed.md` in full, and `analysis/assets.md`.
- For each B-roll or image asset, view its contact sheet (`motion-studio look-asset <slug> <asset-id>`) and write a one-line description into `assets.md`.
- Identify the core message, the strongest hook candidates, retake winners, tangents and the CTA.

## 3. Plan
- `motion-studio plan draft <slug>`, unless `edl.json` already exists from earlier work; then build on it.
- Edit `projects/<slug>/edl.json` following the `motion-studio-plan` skill: choose the hook, order the segments, trim, drop soft fillers where they hurt, add emphasis, zooms, B-roll and titles, set the music block, and write a short `rationale`.
- `motion-studio plan validate <slug>`. Fix every error; resolve warnings unless they are deliberate.
- GATE (plan): if `[review] plan` is true or the user asked to review, present the hook line, duration, structure (one line per segment) and what was cut, then wait.

## 4. Music
- `motion-studio music <slug>`. Follow `motion-studio-music` for the prompt.

## 5. Preview and self-check
- `motion-studio render <slug> --preview` renders every format in the EDL.
- `motion-studio check <slug> --preview`, then view `check/cuts.png`. Fix blocking issues by editing the EDL (see `motion-studio-review`), validate, render and check again. Stop after 3 loops and report what remains.
- GATE (preview): if `[review] preview` is true or the user asked to review, give the preview paths plus a 3-line summary and wait. Apply feedback with `motion-studio-review`.

## 6. Final
- `motion-studio render <slug> --final`, then `motion-studio check <slug> --final`.
- Deliver: the final file paths, duration, hook line, the music used (prompt and seed, or track and licence) and anything the user should know.
- Update `projects/<slug>/notes.md` with decisions, feedback and lessons.
