set shell := ["bash", "-euo", "pipefail", "-c"]

# Markers that need a Mac, models, the renderer, ACE-Step or Playwright; CI and `just test` skip them.
local_only := "not slow and not mac and not models and not renderer and not music and not record"

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

# Everything, including tests that need a Mac, models, the renderer, music or Playwright.
test-all:
    uv run pytest
    cd renderer && npx vitest run --passWithNoTests

# The resolver's test bar (spec #1, seam 2): at least 95% line coverage of src/motion_studio/edl.
edl-coverage:
    uv run pytest -q tests/unit/test_edl_*.py tests/unit/test_resolver*.py tests/unit/test_product_draft_cli.py --cov=motion_studio.edl --cov-report=term-missing --cov-fail-under=95

schema:
    uv run python scripts/gen_schemas.py

# Regenerate the contracts and fail when the committed copies differ.
schema-check: schema
    git diff --exit-code -- schemas renderer/src/types.gen.ts
    test -z "$(git ls-files --others --exclude-standard -- schemas renderer/src/types.gen.ts)"

# Regenerate the synthetic test media and its ground truth (macOS: needs `say` and ffmpeg).
fixtures:
    uv run python scripts/make_fixtures.py

# The whole pipeline on the EN and IT fixtures through the CLI (macOS; needs `motion-studio setup --music`).
e2e:
    uv run pytest tests/e2e -v -s

ci: lint schema-check test edl-coverage
