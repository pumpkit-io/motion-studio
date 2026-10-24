# Contributing to reelcut

Thanks for helping. reelcut is deterministic plumbing: the editorial judgement lives in the host agent, and the harness turns footage into text and an EDL into video.

## Set up

You need Python 3.12, [uv](https://docs.astral.sh/uv/), [just](https://just.systems/), Node 22.13+ or 24+, and ffmpeg 7 or later.

```sh
just setup
just lint
just test
```

## Before you open a pull request

- `just lint` and `just test` pass. CI runs the same on Linux.
- If you touched a pipeline stage, run `just e2e` on a Mac (after `reelcut setup --music` and `just fixtures`): the whole pipeline on the EN and IT fixtures, about 10 minutes.
- If you changed a Pydantic contract, run `just schema` and commit the regenerated files.
- Tests drive a module through its public interface. Mark tests that need a Mac, models, the renderer or ACE-Step (see `AGENTS.md`).
- Add a line to `CHANGELOG.md` under "Unreleased".

## Adding a language

Add one data file under `src/reelcut/lang/`. See [docs/adding-a-language.md](docs/adding-a-language.md).
