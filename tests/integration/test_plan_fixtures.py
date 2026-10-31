"""`plan draft`, `plan validate` and `words` on the analysed EN and IT fixtures.

Uses the real cache and the platform's default speech-to-text backend; run `motion-studio setup`
and `just fixtures` first.
"""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from motion_studio.asr import DEFAULT_MODELS, model_path, resolve_backend
from motion_studio.asr.vad import vad_model_path
from motion_studio.audio.enhance import deep_filter_binary
from motion_studio.cli import app
from motion_studio.edl import Timeline
from motion_studio.text import normalise_words

pytestmark = [pytest.mark.slow, pytest.mark.mac, pytest.mark.models]

ROOT = Path(__file__).resolve().parents[1] / "fixtures"
MEDIA = ROOT / "media"
TRUTH = ROOT / "ground_truth"

runner = CliRunner()


def run(*args: str) -> Any:
    result = runner.invoke(app, [*args, "--json"])
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


@pytest.fixture(scope="module", params=["en", "it"])
def analysed(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[tuple[str, Path]]:
    language: str = request.param
    source = MEDIA / f"{language}_talking.mov"
    if not source.exists():
        pytest.skip("fixtures not generated; run `just fixtures`")
    backend = resolve_backend("auto")
    if not vad_model_path().is_file() or model_path(DEFAULT_MODELS[backend]) is None:  # type: ignore[index]
        pytest.skip("speech models not in the cache; run `motion-studio setup`")
    with pytest.MonkeyPatch.context() as monkeypatch:
        deep_filter = deep_filter_binary()
        if deep_filter:
            monkeypatch.setenv("MOTION_STUDIO_DEEP_FILTER", str(deep_filter))
        monkeypatch.setenv("MOTION_STUDIO_MIN_FREE_GB", "0")
        workspace = tmp_path_factory.mktemp(language) / "reels"
        run("init", str(workspace))
        monkeypatch.chdir(workspace)
        run("new", "demo", "--from", str(source), str(MEDIA / "broll.mp4"))
        run("ingest", "demo")
        run("analyze", "demo")
        yield language, workspace / "projects" / "demo"


def truth(language: str) -> dict[str, Any]:
    return json.loads((TRUTH / f"{language}_talking.json").read_text(encoding="utf-8"))


def test_the_draft_validates_into_a_timeline(analysed: tuple[str, Path]) -> None:
    language, project = analysed

    drafted = run("plan", "draft", "demo", "--force")
    result = runner.invoke(app, ["plan", "validate", "demo"])

    assert drafted["language"] == language
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert len(lines) < 30
    assert lines[0].startswith(f"✓ edl.json valid · language {language} · ")
    assert lines[1].startswith("Duration ")
    assert lines[2].startswith('Hook (first 3s): "')
    assert lines[3] == "Events: none"
    timeline = Timeline.model_validate_json(
        (project / "build" / "timeline.json").read_text(encoding="utf-8")
    )
    assert timeline.duration_frames > 0
    assert timeline.language == language


def test_the_draft_skips_the_abandoned_take_and_drops_the_hard_filler(
    analysed: tuple[str, Path],
) -> None:
    language, project = analysed
    run("plan", "draft", "demo", "--force")

    summary = run("plan", "validate", "demo")

    facts = truth(language)
    lines = [normalise_words(u["text"]) for u in facts["utterances"]]
    edl = json.loads((project / "edl.json").read_text(encoding="utf-8"))
    notes = [normalise_words(s["note"]) for s in edl["segments"]]
    assert lines[facts["retake"]["abandoned"]] not in notes
    assert lines[facts["retake"]["winner"]] in notes
    assert len(notes) == len(lines) - 1
    assert summary["hard_fillers_removed"] >= 1


def test_words_prints_ids_and_times(analysed: tuple[str, Path]) -> None:
    result = runner.invoke(app, ["words", "demo", "c1.s0", "c1.s1"])

    assert result.exit_code == 0, result.output
    assert "c1.w0 " in result.output
    assert "c1.s1" in result.output
