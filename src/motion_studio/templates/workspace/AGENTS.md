# Video editing workspace (motion-studio)

You are the editor. `motion-studio` is your toolchain: it turns footage into text you can read, and renders the edit you describe in `edl.json`. Rendering code is motion-studio's job; yours is the EDL.

This workspace holds two kinds of project, fixed when the project is created and shown by `motion-studio status <slug>`:

- **talk**: talking-head footage cut into videos for Instagram Reels and X. Create one with `motion-studio new <slug> --from <files>`.
- **product**: a product video made from screen recordings, such as a launch video, a feature demo or a changelog video. Create one with `motion-studio new <slug> --kind product`.

## Golden rules
1. `projects/*/raw/` is read-only. Keep every project's `final/` and `notes.md`.
2. All creative decisions go in `projects/<slug>/edl.json`. Re-render after editing it.
3. Read `analysis/packed.md` first, and use `motion-studio look` only for decisions that need eyes (budget: `look_budget` sheets per project).
4. Point at IDs, never times: utterances and words (`c1.s4`, `c1.w52`) in talk projects, markers and elements (`c2.m.v1_shown`, `c2.e.hook`) in product projects.
5. Run `motion-studio plan validate <slug>` after every EDL change and fix all errors before rendering.
6. Always run `motion-studio check <slug>` after rendering; fix blocking issues before delivering.
7. Review gates: if `[review] plan` or `preview` is true in the config, or the user asked to review, stop at that gate with a short summary and wait. A product video's shot list is always a gate.
8. Keep `projects/<slug>/notes.md` updated: decisions, the user's feedback, and lessons for next time.

## Workflow
Pick the skill by project kind, and never mix the two:

- talk projects follow `motion-studio-edit`, with the editorial rules in `motion-studio-plan`;
- product projects follow `motion-studio-product`, from the brief and shot list to delivery.

Both use `motion-studio-look` for visual inspection, `motion-studio-music` for music, and `motion-studio-review` for QA and feedback. If your agent does not load skills, read them directly:

- `.agents/skills/motion-studio-edit/SKILL.md`
- `.agents/skills/motion-studio-plan/SKILL.md`
- `.agents/skills/motion-studio-product/SKILL.md`
- `.agents/skills/motion-studio-look/SKILL.md`
- `.agents/skills/motion-studio-music/SKILL.md`
- `.agents/skills/motion-studio-review/SKILL.md`

After upgrading motion-studio, run `motion-studio agents sync` to refresh them.

## Online video references

When you need to inspect a linked video or Reel, use yt-dlp to retrieve metadata and download the media locally. It supports extraction from YouTube, Instagram, TikTok, X/Twitter, Facebook, Reddit, LinkedIn, Twitch, Vimeo, Pinterest, Dailymotion, Loom and Bilibili; availability depends on the URL and access restrictions. Threads may work through generic extraction. Consult the [upstream supported-sites list](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md) rather than assuming every video type works.

Use `yt-dlp` if it is on PATH. Otherwise use `uv run --with 'yt-dlp[default]==2026.10.26' yt-dlp` in its place in these examples (the package includes YouTube challenge scripts). For YouTube, enable Node.js 22+ with `--js-runtimes node`; ffmpeg is used for merging separate audio and video streams.

```sh
yt-dlp --js-runtimes node --no-playlist --skip-download --dump-single-json 'URL'
yt-dlp --js-runtimes node --no-playlist -P 'references' -o '%(extractor_key)s-%(id)s.%(ext)s' --print after_move:filepath 'URL'
```

Keep reference downloads in `references/`, outside existing projects' read-only `raw/` footage. Analyze downloaded files into compact text and use contact sheets for visual decisions. If reference footage is meant to become source material, create a project from the local file through the normal workflow. Report login requirements, unavailable media or extraction failures explicitly; use authenticated cookies only when the user provides or authorizes them. Download only the requested media; playlists and livestream recording require an explicit request.

## Quick reference
Every command takes `--json`. Exit codes: 0 OK, 1 fixable EDL or input error, 2 missing dependency (run `motion-studio doctor`), 3 internal error.

```
motion-studio status <slug>
motion-studio new <slug> --from <files>
motion-studio new <slug> --kind product
motion-studio record web <slug> <script.mjs>
motion-studio record terminal <slug> <file.tape> --cwd <folder>
motion-studio ingest <slug>
motion-studio analyze <slug>
motion-studio words <slug> <ref-from> <ref-to>
motion-studio look <slug> <clip> <t0> <t1>
motion-studio look <slug> --at <scene | marker | seconds>
motion-studio look-asset <slug> <asset-id>
motion-studio plan draft <slug>
motion-studio plan validate <slug>
motion-studio music <slug> [--candidates 3]
motion-studio render <slug> --preview|--final [--format 9x16]
motion-studio check <slug> --preview|--final
motion-studio config show <slug>
motion-studio docs edl
```
