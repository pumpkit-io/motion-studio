# Renaming reelcut

The product name lives in one constant in code, `APP_NAME` in `src/reelcut/__init__.py`. Everything the CLI derives from it follows a change there: the command name in help and `--version`, the workspace file `<name>.toml`, the environment variable prefix `<NAME>_`, the cache directory (`~/Library/Caches/<name>` on macOS) and every `run <name> ...` hint.

Everything else that says `reelcut` is listed below, built from `git grep -n reelcut` (the same files match case-insensitively) and `git ls-files | grep reelcut`, and checked by hand on 2026-10-24. `tests/unit/test_docs.py` fails when a tracked file names the product and no entry below covers it, or when an entry matches no such file. Entries are shell patterns in which `*` also matches `/`.

To rename, work through the sections in order, then run `git grep -n -i reelcut` and expect only the historical records listed at the end.

## 1. Code that names the product

Change these by hand.

- `src/reelcut/__init__.py`: `APP_NAME` and the module docstring.
- `pyproject.toml`: the distribution `name`, the `[project.scripts]` entry point (`reelcut = "reelcut.cli:app"`), the wheel `packages` path, the five `force-include` targets under `reelcut/_renderer/`, and the pyright `strict` paths.
- `uv.lock`: run `uv lock` after changing `pyproject.toml`; do not edit it by hand.
- `justfile`: `--cov=reelcut.edl` in `edl-coverage`, and two comments.
- `renderer/package.json`: the package `name` (`reelcut-renderer`) and `description`.
- `renderer/package-lock.json`: run `npm install --package-lock-only` in `renderer/` after changing the name, then restore the platform optional packages npm drops (see BUILD_LOG.md, ticket #10).
- `src/reelcut/render/renderer.py`: the install marker `.reelcut-installed` is a literal string, not derived from `APP_NAME`.

## 2. The Python package directory

`git mv src/reelcut src/<name>`, then replace `reelcut` with the new name in every import (`from reelcut...`, `import reelcut`, `python -m reelcut.asr.worker`, `files("reelcut")`). The import lines are mechanical; the rest of each file's matches are docstrings and comments that mention the command, which a plain search-and-replace also handles.

- `src/reelcut/agents/__init__.py`: `files("reelcut")` resource lookups.
- `src/reelcut/cli/docs.py`: `files("reelcut")` for the packaged EDL reference.
- `src/reelcut/workspace.py`: `files("reelcut")` for the workspace template.
- `src/reelcut/audio/enhance.py`: `files("reelcut.audio")` for the vendored RNNoise model.
- `src/reelcut/asr/__init__.py`: the worker command `python -m reelcut.asr.worker`.
- `src/reelcut/vision/__init__.py`: the worker command `python -m reelcut.vision.worker`.
- `src/reelcut/music/acestep_worker.py`: a docstring that says the worker must not import reelcut; keep the rule.
- `src/reelcut/*`: every other module under the package: imports, docstrings, comments and hint strings.
- `scripts/gen_schemas.py`: imports and a comment.

## 3. Text the host agent and the creator read

These are part of the product's interface: rename them by hand and read the result.

- `src/reelcut/templates/skills/reelcut-*`: the five skill folders (`reelcut-edit`, `reelcut-plan`, `reelcut-look`, `reelcut-music`, `reelcut-review`), their `name:` frontmatter, which must match the folder, and every command in their text. `reelcut agents sync` replaces folders by these names, so existing workspaces keep the old `reelcut-*` folders until someone deletes them.
- `src/reelcut/templates/workspace/AGENTS.md`: the title, golden rules and quick reference.
- `src/reelcut/templates/workspace/reelcut.toml`: the file name must equal `<APP_NAME>.toml`, because `find_workspace` looks for that name. `tests/unit/test_config.py` compares it with `Config()`.
- `src/reelcut/templates/workspace/library/*`: the music and brand library READMEs.
- `src/reelcut/reference/edl.md`: the EDL reference that `reelcut docs edl` prints (`docs/edl.md` is a symlink to it).
- `src/reelcut/lang/*`: a comment at the top of each language file.

## 4. Generated contracts

- `schemas/*`: the JSON Schemas carry model docstrings that mention reelcut. Run `just schema` after renaming the package; never edit them by hand.

## 5. Tests

The tests spell out the user-facing names (`reelcut.toml`, the `reelcut-*` skills, `reelcut 0.1.0` from `--version`, `reelcut ...` commands in the agent texts) on purpose: they check the interface a creator sees. Replace the name in all of them along with the code.

- `tests/unit/test_agents.py`: the `SKILLS` list, skill paths and the `reelcut ...` command pattern that checks the agent texts against the CLI.
- `tests/unit/test_cli.py`: the expected `--version` output.
- `tests/unit/test_docs.py`: uses `APP_NAME`, so it follows the constant; update its docstring.
- `tests/*`: every other test: imports, `reelcut.toml` fixtures and the CLI subprocess calls in the e2e and integration tests.

## 6. Documentation

Rename these by hand and reread them.

- `README.md`
- `AGENTS.md`: the developer guide, including rule 13 on `APP_NAME`.
- `CONTRIBUTING.md`
- `CHANGELOG.md`: keep past entries as written; add a line for the rename.
- `GLOSSARY.md`: the title and two definitions.
- `ROADMAP.md`
- `THIRD_PARTY.md`
- `docs/adr/*`: ADRs 0001 to 0003 name the product in their decisions.
- `docs/agents.md`
- `docs/architecture.md`
- `docs/adding-a-language.md`
- `docs/cli.md`: regenerate the option lists with `uv run typer <name>.cli utils docs --name <name>` and carry the examples across.
- `docs/dependencies.md`
- `docs/renaming.md`: this file. Update the patterns as the paths change.

## 7. Historical records

Leave these as they are: they describe what was built under the old name.

- `BUILD_LOG.md`
- `HANDOFF.md`: the v0.1.0 hand-off to the creator, dated and tied to that build.
- `video-harness-build-guide.md`

## Outside the repository

`git grep` cannot see these.

- The GitHub repository `pumpkit-io/reelcut` and its clone URLs in README.md.
- The package name on PyPI, if it is ever published, and the `uv tool install` commands in README.md.
- Creators' machines: the old cache (`~/Library/Caches/reelcut`, 16 GB on the build machine with the ACE-Step environment) is orphaned; `reelcut setup` under the new name downloads everything again unless the directory is moved or `<NAME>_CACHE_DIR` points at it.
- Existing workspaces: their `reelcut.toml` must be renamed to `<name>.toml`, and their `.claude/skills/reelcut-*` and `.agents/skills/reelcut-*` folders deleted before `agents sync` installs the renamed skills.
- The environment variables people may have set (`REELCUT_CACHE_DIR`, `REELCUT_MIN_FREE_GB` and the others in `docs/cli.md`) change prefix with `APP_NAME`.
