---
name: motion-studio-product
description: End-to-end workflow for a product video (a launch video, feature demo or changelog video) made from screen recordings with motion-studio, from the brief and shot list through recording, scenes, music and review to delivery. Use whenever the user asks for a video of their product, or when `motion-studio status` reports a product project.
---

# Making a product video with motion-studio

A product video is music only: kinetic text, title cards, the real product in a browser or terminal frame with a camera that zooms onto elements, proof shots of real results, and a logo outro. You record the product, then describe the edit in `edl.json`; motion-studio renders it with fixed components. You write recording scripts and tapes, which drive the creator's product and so stay inside golden rule 2 (the edit is data); you never write rendering code, Remotion compositions or ffmpeg edits.

Run every command from the workspace root. Exit codes: 0 OK, 1 a fixable EDL or input error (read the hint, fix, rerun), 2 a missing dependency (`motion-studio doctor` names it and the install line; tell the user), 3 an internal error (report it with the message).

## 1. Brief
- `motion-studio status <slug>`. For a new video, `motion-studio new <slug> --kind product --title "<title>"`; the kind is fixed once set. A talk project cannot become one.
- Agree with the creator: the kind of video, its audience, the target length, the story in one line, the three to five steps to show, the proof shot (a real result such as the published post) and the closing tagline and URL.
- Check `[brand]` in `motion-studio.toml`: `primary`, `accent`, `wordmark` and `mascot`, a sprite sheet or a GIF (see `library/brand/README.md`). Without a wordmark the logo outro sets the EDL's title in type; ask for one if the brand has it. Without a mascot the outro shows the wordmark alone (`"mascot": false`, which the draft sets).

## 2. Demo kit
Ask for the product's **demo kit**: the document in the product's own repository that says how to film it safely (the isolated instance, demo accounts, how to sign in, how to undo each side effect). Read it in full.

When there is none, stop. Tell the creator what it must cover, and wait: guessing how to sign in or how to undo a post is how real accounts get changed. A product with no accounts and no side effects (a static page, a local CLI) still needs the creator to say so.

## 3. Shot list (required gate)
Write the **shot list** to `projects/<slug>/notes.md` and show it to the creator. For each recording:
- what it shows, web or terminal, and the markers and elements you will capture (`v1_shown`, element `hook`);
- every side effect outside the isolated instance: posts, emails, payments, API keys, settings, connected accounts;
- the undo step for each, taken from the demo kit.

Stop here and wait for the creator's explicit approval, always, whatever `[review]` says. Anything public (a real post, a sent email) needs its own yes. Change nothing in any account before approval.

## 4. Prepare the product state
- Create billing, subscriptions, test cards and similar state through the provider's CLI or API (such as the Stripe CLI in test mode), never through its web checkout: checkouts fight headless browsers.
- Keep every credential in a file passed by path: `contextOptions.storageState` for a signed-in browser, an MCP config file for a terminal session. A key typed on a command line or into a page ends up in the recording.
- Record each change you make, with its undo step, in `notes.md` as you go.

## 5. Record
Read [recording.md](recording.md) before writing the first script or tape: it has the helper library, the tape lines and what makes footage that edits well. Keep scripts and tapes in `projects/<slug>/takes/`.
- Browser: `motion-studio record web <slug> <script.mjs>` (one-time setup: `motion-studio setup --record`).
- Terminal: `motion-studio record terminal <slug> <file.tape> --cwd <clean-folder>`.
- A failed take adds nothing to `raw/`. Fix the script and run again; an existing clip needs `--name <take2>`.
- Put proof images (a screenshot of the real result) in `projects/<slug>/raw/`.
- Then `motion-studio ingest <slug>` and `motion-studio analyze <slug>`.

## 6. Understand the footage
- Read `analysis/packed.md` in full: each recording's length, frame size, markers (`c2.m.v1_shown`), element boxes (`c2.e.hook`) and static stretches.
- View each `contact/<id>.png` once (one frame per second, free of the look budget).
- Before choosing an in-point after a state change, check the moments around it: `motion-studio look <slug> <clip> <t0> <t1> --frames 8` over a 2 to 4 s range. Text often lands later than the marker.

## 7. Scenes
- `motion-studio plan draft <slug>` writes a baseline: an intro card, a numbered title card and a footage scene per recording, a proof scene per image and the logo outro. `motion-studio docs edl` has every field under "Product EDLs".
- Refine `edl.json` in this order, validating as you go (`motion-studio plan validate <slug>`):
  1. Story: an intro (`kinetic_text`, three short lines, or a title card), then per step a title card (one bar, as the draft writes it) and 4 to 8 s of footage, the proof, the outro.
  2. Footage spans: `from` and `to` on markers, nudged with `offset_s`; typing at `rate` 2.6 to 3.2, everything else at 1. A scene has one `rate`, so a step that types and then shows a result is two or three footage scenes back to back. Cut waits on slow work by starting the next scene at the marker after the wait.
  3. Camera: one move per moment that matters, targeting an element (`"target": "c2.e.hook"`) and leaving `zoom` out (it fills about 70%); `"full"` with `snap` to pull back. Two or three moves per footage scene at most. Target the smallest element that tells the story: a target already wider than 70% of the frame gets zoom 1, a move that does nothing.
  4. Events: a `caption_pill` on every footage scene (a few words on what is happening), a `highlight` on what changed, a `mask` over anything that must not show (paths, keys, off-message lines), and a `flash` on hard cuts.
  5. `rationale`: one to three sentences.
- Settle the scene lengths before music: the bed is generated for the scenes' total length, and a new length means generating again.
- GATE (plan): if `[review] plan` is true or the user asked, present the scenes (one line each), the duration and the shot each footage scene uses, then wait.

## 8. Music
A product video has no voice, so the bed is its only sound: with `"mode": "none"` the render is silent and `check --final` blocks on loudness. When generation is not set up (`motion-studio setup --music`), use a licensed library track (`"mode": "library"`) or tell the creator the final cannot pass without one. Follow `motion-studio-music`. For a launch video: `"preset": "launch"`, then `motion-studio music <slug> --candidates 3`, pick the seed whose `hits` in `build/music.json` include a `drop`, set `music.seed`, add `"align": {"hit": "drop", "at": "<scene id>"}` for the scene the drop should open (often the outro) and run `motion-studio music <slug>` again. Then `motion-studio plan validate <slug>`, which moves the scenes onto the bed's beats. If you have not refined the draft yet, `motion-studio plan draft <slug> --force` lays it on the bed's grid instead.

## 9. Preview and review
- `motion-studio render <slug> --preview`, then `motion-studio check <slug> --preview`. Product videos render 16x9 only.
- View `check/contact.png` (one frame per second) and `check/cuts.png`. Read the "Masked regions" list and confirm each mask covers what it should.
- For any moment the sheets leave unclear, `motion-studio look <slug> --at <scene id> --at <marker> --at <seconds>`; one call counts once against the look budget, so batch the moments you doubt.
- Fix what `motion-studio-review` describes for product videos, validate, render and check again. Stop after 3 loops and report what remains.
- GATE (preview): if `[review] preview` is true or the user asked, give the preview path and a 3-line summary, then wait.

## 10. Deliver
- `motion-studio render <slug> --final`, then `motion-studio check <slug> --final`, which must pass. It rewrites `check/report.md`, so read the preview's report before this step.
- Give the creator `final/<slug>_16x9.mp4` and the share copy `final/<slug>_16x9_share.mp4` (under 30 MiB, for chat and phones; a plain copy when the final already fits), the duration, the music (preset or prompt and seed) and the scenes in one line each.
- Undo every side effect from the shot list now, unless the creator asked to keep it.
- End with the side-effect report: every side effect you caused, how it was undone and how you confirmed it, plus any you could not undo and what the creator must do. Copy it into `notes.md` with the decisions and lessons for next time.
