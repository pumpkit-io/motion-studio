set shell := ["bash", "-euo", "pipefail", "-c"]

# Markers that need a Mac, models, the renderer or ACE-Step; CI and `just test` skip them.
local_only := "not slow and not mac and not models and not renderer and not music"

default:
    @just --list

# Install Python (with the extra for this platform) and renderer dependencies.
setup:
    uv sync --extra {{ if os() == "macos" { "mac" } else { "cpu" } }}
    cd renderer && npm ci

lint:
    uv run ruff check .
    uv run ruff format --check .
    uv run pyright
    cd renderer && npx tsc --noEmit

fmt:
    uv run ruff format .
    uv run ruff check --fix .

test:
    uv run pytest -m "{{ local_only }}"
    cd renderer && npx vitest run --passWithNoTests

# Everything, including tests that need a Mac, models, the renderer or music.
test-all:
    uv run pytest
    cd renderer && npx vitest run --passWithNoTests

schema:
    uv run python scripts/gen_schemas.py

# Regenerate the contracts and fail when the committed copies differ.
schema-check: schema
    git diff --exit-code -- schemas renderer/src/types.gen.ts
    test -z "$(git ls-files --others --exclude-standard -- schemas renderer/src/types.gen.ts)"

# Regenerate the synthetic test media and its ground truth (macOS: needs `say` and ffmpeg).
fixtures:
    uv run python scripts/make_fixtures.py

ci: lint schema-check test
