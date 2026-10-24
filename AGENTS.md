# Developing reelcut

This file is for agents working on reelcut itself. The agent that edits videos reads the workspace `AGENTS.md` that `reelcut init` writes, not this one.

## Commands

- `just setup`: install Python dependencies (the `mac` extra on macOS, `cpu` elsewhere) and the renderer's npm packages.
- `just lint`: ruff check, ruff format check, pyright, and `tsc --noEmit` in `renderer/`.
- `just test`: pytest without the local-only markers, then vitest in `renderer/`. This is what CI runs.
- `just test-all`: every test, including those marked `slow`, `mac`, `models`, `renderer` and `music`.
- `just edl-coverage`: the resolver's tests with the 95% line-coverage gate on `src/reelcut/edl`.
- `just e2e`: the whole pipeline on the EN and IT fixtures (macOS, after `reelcut setup --music` and `just fixtures`; about 10 minutes).
- `just schema`: regenerate `schemas/` from the Pydantic contracts. `just schema-check` fails when the committed copies are stale.
- `just fixtures`: regenerate the synthetic test media and its ground truth (macOS; see `tests/fixtures/README.md`).
- `uv tool install --editable .`: put the `reelcut` command on your PATH from this checkout.

CI (`.github/workflows/ci.yml`) runs `just lint`, `just schema-check`, `just test` and `just edl-coverage` on Linux for every pushed branch.

## Test markers

Mark any test that cannot run on a Linux CI box: `slow` (long integration or e2e), `mac` (MLX, VideoToolbox, `say`), `models` (loads ASR, VAD or face models; take the machine-wide heavy-model lock), `renderer` (needs the installed Remotion renderer), `music` (needs the ACE-Step environment).

## Coding rules

1. The agent reads; it never watches. Turn video into compact text (`packed.md`) plus on-demand contact sheets.
2. The agent edits data, not code. Creative decisions go in `edl.json`; rendering code is fixed and tested.
3. Reference IDs, not floats. The EDL names utterances and words (`c1.s004`, `c1.w127`); the resolver does the timing (ADR 0002).
4. Deterministic baseline, agent refinement. `plan draft` produces a sensible EDL; the agent improves it.
5. Every stage is idempotent, cached and resumable, keyed by input hashes in `state.json`.
6. Concise stdout (about 30 lines), detail in files, `--json` for machines, and every written path printed.
7. One heavy model in memory at a time: ASR, face detection and music run in separate processes, one after another.
8. Pydantic models are the single source of the contracts. Regenerate schemas and TypeScript types; never edit them by hand, and never merge them by hand.
9. reelcut never calls an LLM (ADR 0001) and never uploads anything.
10. Build ffmpeg argument lists, never shell strings. Paths with spaces and accents must work.
11. Never degrade silently: a fallback prints a one-line warning and is recorded in `state.json`.
12. Exit codes: 0 OK, 1 fixable EDL or user error, 2 missing dependency, 3 internal error.
13. Keep the name `reelcut` in as few places as possible: `APP_NAME` in `src/reelcut/__init__.py` is the only one in code. A new file that names the product needs an entry in `docs/renaming.md`.
14. A new command or option needs its section in `docs/cli.md`; an EDL field or resolver issue code needs its entry in `src/reelcut/reference/edl.md`. Tests fail until they are there.

Check third-party APIs and CLI flags against the installed version before using them, and record verified versions in `docs/dependencies.md`. Log what you built and any deviation from the build guide in `BUILD_LOG.md`. `docs/architecture.md` maps the modules and contracts.

## Agent skills

### Issue tracker

Issues and specs live in GitHub Issues on pumpkit-io/reelcut. See `docs/agents/issue-tracker.md`.

### Domain docs

Single-context: `GLOSSARY.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
