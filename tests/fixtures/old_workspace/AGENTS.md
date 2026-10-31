# Video editing workspace (reelcut)

You are the editor. `reelcut` is your toolchain: it turns footage into text you can read, and renders the edit you describe in `edl.json`. Rendering code is reelcut's job; yours is the EDL.

## Golden rules
1. `projects/*/raw/` is read-only. Keep every project's `final/` and `notes.md`.
2. All creative decisions go in `projects/<slug>/edl.json`. Re-render after editing it.
3. Read `analysis/packed.md` first. Use `reelcut words` for exact word IDs, and `reelcut look` only for decisions that need eyes (budget: `look_budget` sheets per project).
4. Prefer utterance refs (`c1.s4`) for cuts; use word refs (`c1.w52`) for fine trims.
5. Run `reelcut plan validate <slug>` after every EDL change and fix all errors before rendering.
6. Always run `reelcut check <slug>` after rendering; fix blocking issues before delivering.
7. Review gates: if `[review] plan` or `preview` is true in the config, or the user asked to review, stop at that gate with a short summary and wait.
8. Keep `projects/<slug>/notes.md` updated: decisions, the user's feedback, and lessons for next time.

## Workflow
Follow the skill `reelcut-edit`. The editorial rules are in `reelcut-plan`, visual inspection in `reelcut-look`, music in `reelcut-music`, and QA and feedback in `reelcut-review`. If your agent does not load skills, read them directly:

- `.agents/skills/reelcut-edit/SKILL.md`
- `.agents/skills/reelcut-plan/SKILL.md`
- `.agents/skills/reelcut-look/SKILL.md`
- `.agents/skills/reelcut-music/SKILL.md`
- `.agents/skills/reelcut-review/SKILL.md`

After upgrading reelcut, run `reelcut agents sync` to refresh them.

## Quick reference
Every command takes `--json`. Exit codes: 0 OK, 1 fixable EDL or input error, 2 missing dependency (run `reelcut doctor`), 3 internal error.

```
reelcut status <slug>
reelcut new <slug> --from <files>
reelcut ingest <slug>
reelcut analyze <slug>
reelcut words <slug> <ref-from> <ref-to>
reelcut look <slug> <clip> <t0> <t1>
reelcut look-asset <slug> <asset-id>
reelcut plan draft <slug>
reelcut plan validate <slug>
reelcut music <slug>
reelcut render <slug> --preview|--final [--format 9x16]
reelcut check <slug> --preview|--final
reelcut config show <slug>
reelcut docs edl
```
