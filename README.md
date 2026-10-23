# reelcut

An offline, agent-agnostic harness that lets a coding agent (Claude Code, Codex, Gemini CLI, Cursor) turn raw talking-head footage, images and B-roll into finished short videos for Instagram Reels and X.

The agent reads a compact text index of the footage and writes an edit decision list (EDL) that names words and utterances by ID. reelcut validates the EDL into a frame-accurate timeline and renders it: cuts, filler and dead-air removal, retake selection, punch-in zooms, face-centred reframing, captions, B-roll, locally generated music, ducking and loudness mastering. reelcut never calls an LLM and never uploads anything.

> Status: v0.1.0 is under construction. This README is a skeleton.

## Quickstart

```sh
uv tool install reelcut          # or, from a checkout: uv tool install --editable .
reelcut setup                    # download models into the cache (once)
reelcut init ~/Videos/reels      # create a workspace
cd ~/Videos/reels && reelcut new my-video --from ~/Desktop/takes/
```

Then open your coding agent in the workspace and ask: "Edit this into a 45-second Reel and an X version."

<!-- Demo GIF placeholder -->

## Licences

reelcut is MIT-licensed. Some dependencies are not:

- **Remotion**, which renders the composition, is not OSI open source. It is free for individuals and for companies of up to 3 people; larger companies need a company licence. See [remotion.dev/license](https://www.remotion.dev/license).
- **ACE-Step 1.5 weights**, used for local music generation, carry their own licence. `reelcut setup --music` prints it and every generated `music.json` records it.

See [THIRD_PARTY.md](THIRD_PARTY.md) for every dependency's licence.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) and [AGENTS.md](AGENTS.md).
