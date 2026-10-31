"""`motion-studio check` with the real speech model and renderer on the EN and IT fixtures.

Uses the real cache; run `motion-studio setup` and `just fixtures` first. Set
MOTION_STUDIO_CHECK_STILLS=<dir> to copy each run's cuts.png and report.md there.
"""

import json
import os
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from motion_studio.asr import DEFAULT_MODELS, model_path, resolve_backend
from motion_studio.asr.vad import vad_model_path
from motion_studio.audio.enhance import deep_filter_binary
from motion_studio.cli import app
from motion_studio.render.renderer import find_renderer

pytestmark = [pytest.mark.slow, pytest.mark.mac, pytest.mark.models, pytest.mark.renderer]

MEDIA = Path(__file__).resolve().parents[1] / "fixtures" / "media"

runner = CliRunner()


def run(*args: str) -> Any:
    result = runner.invoke(app, [*args, "--json"])
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


def check(*args: str) -> tuple[int, dict[str, Any]]:
    result = runner.invoke(app, ["check", "demo", *args, "--json"])
    assert result.exit_code in (0, 1), result.output
    return result.exit_code, json.loads(result.stdout)


def edit_edl(project: Path, **changes: Any) -> None:
    edl = json.loads((project / "edl.json").read_text(encoding="utf-8"))
    edl.update(changes)
    edl["music"]["mode"] = "none"
    (project / "edl.json").write_text(json.dumps(edl, indent=2), encoding="utf-8")


def keep(project: Path, name: str) -> None:
    out = os.environ.get("MOTION_STUDIO_CHECK_STILLS")
    if out:
        target = Path(out) / name
        target.mkdir(parents=True, exist_ok=True)
        shutil.copy(project / "check" / "cuts.png", target / "cuts.png")
        shutil.copy(project / "check" / "report.md", target / "report.md")


@pytest.fixture(scope="module", params=["en", "it"])
def planned(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[tuple[str, Path]]:
    language: str = request.param
    source = MEDIA / f"{language}_talking.mov"
    if not source.exists():
        pytest.skip("fixtures not generated; run `just fixtures`")
    backend = resolve_backend("auto")
    if not vad_model_path().is_file() or model_path(DEFAULT_MODELS[backend]) is None:
        pytest.skip("speech models not in the cache; run `motion-studio setup`")
    find_renderer()
    with pytest.MonkeyPatch.context() as monkeypatch:
        deep_filter = deep_filter_binary()
        if deep_filter:
            monkeypatch.setenv("MOTION_STUDIO_DEEP_FILTER", str(deep_filter))
        monkeypatch.setenv("MOTION_STUDIO_MIN_FREE_GB", "0")
        workspace = tmp_path_factory.mktemp(language) / "reels"
        run("init", str(workspace))
        monkeypatch.chdir(workspace)
        run("new", "demo", "--from", str(source))
        run("ingest", "demo")
        run("analyze", "demo")
        run("plan", "draft", "demo")
        project = workspace / "projects" / "demo"
        edit_edl(project)
        run("plan", "validate", "demo")
        yield language, project


def test_a_good_fixture_render_passes_with_exit_0(planned: tuple[str, Path]) -> None:
    language, project = planned
    run("render", "demo", "--preview", "--format", "9x16")

    code, body = check("--preview")

    keep(project, f"{language}_good")
    print(json.dumps(body["metrics"], indent=1), [i["message"] for i in body["issues"]])
    assert code == 0, body["issues"]
    assert body["verdict"] == "pass"
    assert body["metrics"]["cuts"] >= 1
    assert (project / "check" / "cuts.png").is_file()


def test_zero_padding_produces_a_blocking_clipped_cut(planned: tuple[str, Path]) -> None:
    language, project = planned
    if language != "en":
        pytest.skip("one language is enough for the bad render")
    edit_edl(project, policy={"pad_in_ms": 0, "pad_out_ms": 0})
    run("plan", "validate", "demo")
    run("render", "demo", "--preview", "--format", "9x16")

    code, body = check("--preview")

    keep(project, f"{language}_zero_pad")
    print([(i["message"], i["fix"]) for i in body["issues"]])
    assert code == 1
    assert "clipped_cut" in [i["code"] for i in body["issues"] if i["severity"] == "blocking"]


def test_an_edl_over_max_duration_blocks(planned: tuple[str, Path]) -> None:
    language, project = planned
    if language != "en":
        pytest.skip("one language is enough for the bad render")
    edit_edl(project, policy={}, max_duration_s=5)
    run("plan", "validate", "demo")
    run("render", "demo", "--preview", "--format", "9x16")

    code, body = check("--preview")

    assert code == 1
    assert "over_duration" in [i["code"] for i in body["issues"] if i["severity"] == "blocking"]
