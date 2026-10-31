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
