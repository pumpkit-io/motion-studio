# Renaming motion-studio

The product name lives in one constant in code, `APP_NAME` in `src/motion_studio/__init__.py`. Everything the CLI derives from it follows a change there: the command name in help and `--version`, the workspace file `<name>.toml`, the cache directory (`~/Library/Caches/<name>` on macOS), the renderer's install marker `.<name>-installed` and every `run <name> ...` hint.

`ENV_PREFIX`, next to it, is `APP_NAME` in upper case with hyphens turned into underscores (`MOTION_STUDIO`), so that every environment variable is a valid shell name: `MOTION_STUDIO_CACHE_DIR`, `MOTION_STUDIO_MIN_FREE_GB` and the others in `docs/cli.md`. Code that names a variable builds it as `f"{ENV_PREFIX}_..."`, never from `APP_NAME.upper()`.

Everything else that names the product is listed below, built from `git grep -n -i -e motion-studio -e motion_studio` and `git ls-files`, and checked by hand on 2026-10-31. `tests/unit/test_docs.py` fails when a tracked file names the product (with either spelling) and no entry below covers it, or when an entry matches no such file. Entries are shell patterns in which `*` also matches `/`.

To rename, work through the sections in order, then run `git grep -n -i <old name>` and expect only the files listed under [Where the previous name stays](#where-the-previous-name-stays).

## 1. Code that names the product

Change these by hand.

- `src/motion_studio/__init__.py`: `APP_NAME` and the module docstring. `ENV_PREFIX` follows `APP_NAME`.
- `pyproject.toml`: the distribution `name`, the `[project.scripts]` entry point (`motion-studio = "motion_studio.cli:app"`), the wheel `packages` path, the five `force-include` targets under `motion_studio/_renderer/`, and the pyright `strict` paths.
- `uv.lock`: run `uv lock` after changing `pyproject.toml`; do not edit it by hand.
- `justfile`: `--cov=motion_studio.edl` in `edl-coverage`, and two comments.
- `renderer/package.json`: the package `name` (`motion-studio-renderer`) and `description`.
- `renderer/package-lock.json`: run `npm install --package-lock-only` in `renderer/` after changing the name, then restore the platform optional packages npm drops (see BUILD_LOG.md, ticket #10, and the rename entry).

## 2. The Python package directory

`git mv src/motion_studio src/<package>`, where `<package>` is the new name with hyphens turned into underscores, then replace the old package name in every import (`from motion_studio...`, `import motion_studio`, `python -m motion_studio.asr.worker`, `files("motion_studio")`). The import lines are mechanical; the rest of each file's matches are docstrings and comments that mention the command, which a plain search-and-replace also handles. Keep the two spellings apart: the command, files and folders use the hyphen, Python uses the underscore.

- `src/motion_studio/agents/__init__.py`: `files("motion_studio")` resource lookups.
- `src/motion_studio/cli/docs.py`: `files("motion_studio")` for the packaged EDL reference.
- `src/motion_studio/workspace.py`: `files("motion_studio")` for the workspace template.
- `src/motion_studio/audio/enhance.py`: `files("motion_studio.audio")` for the vendored RNNoise model.
- `src/motion_studio/asr/__init__.py`: the worker command `python -m motion_studio.asr.worker`.
- `src/motion_studio/vision/__init__.py`: the worker command `python -m motion_studio.vision.worker`.
- `src/motion_studio/music/acestep_worker.py`: a docstring that says the worker must not import motion_studio; keep the rule.
- `src/motion_studio/errors.py`: the base exception `MotionStudioError`, named after the product.
- `src/motion_studio/*`: every other module under the package: imports, docstrings, comments and hint strings.
- `scripts/*`: imports and comments in the schema and fixture generators.

## 3. Text the host agent and the creator read

These are part of the product's interface: rename them by hand and read the result.

- `src/motion_studio/templates/skills/motion-studio-*`: the five skill folders (`motion-studio-edit`, `motion-studio-plan`, `motion-studio-look`, `motion-studio-music`, `motion-studio-review`), their `name:` frontmatter, which must match the folder, and every command in their text. `motion-studio agents sync` replaces folders by these names, and in a workspace from before the rename it removes the five old-name folders after installing the new ones (see [Outside the repository](#outside-the-repository)).
- `src/motion_studio/templates/workspace/AGENTS.md`: the title, golden rules and quick reference.
- `src/motion_studio/templates/workspace/motion-studio.toml`: the file name must equal `<APP_NAME>.toml`, because `find_workspace` looks for that name. `tests/unit/test_config.py` compares it with `Config()`.
- `src/motion_studio/templates/workspace/library/*`: the music and brand library READMEs.
- `src/motion_studio/reference/edl.md`: the EDL reference that `motion-studio docs edl` prints (`docs/edl.md` is a symlink to it).
- `src/motion_studio/lang/*`: a comment at the top of each language file.

## 4. Generated contracts

- `schemas/*`: the JSON Schemas carry model docstrings that name the product. Run `just schema` after renaming the package; never edit them by hand.

## 5. Tests

The tests spell out the user-facing names (`motion-studio.toml`, the `motion-studio-*` skills, `motion-studio 0.1.0` from `--version`, `motion-studio ...` commands in the agent texts, the `MOTION_STUDIO_*` variables) on purpose: they check the interface a creator sees. Replace the name in all of them along with the code.

- `tests/unit/test_agents.py`: the `SKILLS` list, skill paths and the `motion-studio ...` command pattern that checks the agent texts against the CLI.
- `tests/unit/test_cli.py`: the expected `--version` output.
- `tests/unit/test_docs.py`: uses `APP_NAME`, so it follows the constant; update its docstring.
- `tests/*`: every other test: imports, `motion-studio.toml` fixtures and the CLI subprocess calls in the e2e and integration tests.

## 6. Documentation

Rename these by hand and reread them.

- `README.md`: including the clone URL and the `uv tool install` commands.
- `AGENTS.md`: the developer guide, including rule 13 on `APP_NAME`.
- `CONTRIBUTING.md`
- `CHANGELOG.md`: rewrite past entries under the new name and add one line that records the rename (section 7).
- `GLOSSARY.md`: the title and two definitions.
- `ROADMAP.md`
- `THIRD_PARTY.md`
- `docs/adr/*`: ADRs 0001 to 0003 name the product in their decisions.
- `docs/agents.md`
- `docs/architecture.md`
- `docs/adding-a-language.md`
- `docs/cli.md`: regenerate the option lists with `uv run typer <package>.cli utils docs --name <name>` and carry the examples across.
- `docs/dependencies.md`
- `docs/renaming.md`: this file. Update the patterns as the paths change.

## 7. Historical records

Rewrite these under the new name too, so that a search for the old name finds nothing stale. They describe what was built, not what it was called at the time. The old name stays only in the files listed under [Where the previous name stays](#where-the-previous-name-stays).

- `BUILD_LOG.md`
- `HANDOFF.md`: the v0.1.0 hand-off to the creator.
- `video-harness-build-guide.md`

## Outside the repository

`git grep` cannot see these.

- The GitHub repository and its clone URLs in README.md: the maintainer renames the repository, and GitHub redirects the old URLs.
- The local clone folder, and the tool install: `uv tool uninstall <old name>`, then `uv tool install` again from the renamed checkout.
- The package name on PyPI, if it is ever published (`motion-studio` is taken by an unrelated project).
- Creators' machines: the old cache (`~/Library/Caches/<old name>`, or wherever the old cache variable points; 16 GB on the build machine with the ACE-Step environment) is orphaned. `doctor` and `setup` print the command that adopts it (an `mv` into the new default location, or for a location the old variable chose, an `export` of `MOTION_STUDIO_CACHE_DIR` pointing at it), and `setup` stops rather than download everything again.
- Existing workspaces: `agents sync` renames their `<old name>.toml` to `<name>.toml`, brings their `AGENTS.md` up to date, installs the new skills and then deletes the five shipped skills' old-name folders from `.claude/skills/` and `.agents/skills/`. A creator's own skill whose name starts with the old name stays. Every other command points at `agents sync`.
- The environment variables people may have set change prefix with `ENV_PREFIX`; a set variable with the old prefix prints a warning naming its replacement.

## Where the previous name stays

`tests/unit/test_docs.py` fails when the previous name appears in a tracked file these entries do not cover. On the next rename, in `src/<package>/migrate.py`, set `OLD_APP_NAME` to the name being replaced, set `OLD_COMMANDS` to the top-level commands the CLI has under that name (`<old name> --help` lists them), set `OLD_AGENTS_MD_SHA256` to the SHA-256 of the workspace `AGENTS.md` template being replaced, and copy that template over the test fixture below; the migration follows. `tests/unit/test_migration.py` fails when a command the fixture names is missing from `OLD_COMMANDS` or when `OLD_COMMANDS` names a command the CLI does not have.

- `CHANGELOG.md`: the line that records the rename.
- `src/motion_studio/migrate.py`: `OLD_APP_NAME`, the one constant behind the migration of old workspaces, the old cache and the old environment variables.
- `tests/fixtures/old_workspace/AGENTS.md`: the workspace `AGENTS.md` that `init` wrote under the old name, which `agents sync` recognises by its hash and replaces.
