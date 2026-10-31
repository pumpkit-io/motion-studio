"""`plan validate` and `docs edl` for product EDLs, on a product workspace with written analyses."""

import json
from pathlib import Path
from typing import Any

import pytest
from edl_fixtures import screen
from typer.testing import CliRunner

from motion_studio.cli import app
from motion_studio.edl import Timeline

runner = CliRunner()

EDL: dict[str, Any] = {
    "kind": "product",
    "title": "Launch",
    "scenes": [
        {"id": "intro", "type": "title_card", "beats": 4, "headline": "Meet the app."},
        {"id": "step1", "type": "title_card", "beats": 2, "step": "01", "headline": "Pick one."},
        {"id": "pick", "type": "footage", "clip": "c1", "from": "c1.m.open", "to": "c1.m.picked"},
    ],
    "rationale": "Intro, then the one step.",
}


def invoke(*args: str | Path):
    return runner.invoke(app, [str(a) for a in args])


@pytest.fixture
def launch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    ws = tmp_path / "videos"
    assert invoke("init", ws).exit_code == 0
    monkeypatch.chdir(ws)
    assert invoke("new", "launch", "--kind", "product").exit_code == 0
    project = ws / "projects" / "launch"
    analysis = screen("c1", 12.0, {"open": 0.5, "picked": 4.5})
    (project / "analysis" / "c1.json").write_text(analysis.model_dump_json(), encoding="utf-8")
    return project


def write_edl(project: Path, edl: dict[str, Any]) -> None:
    (project / "edl.json").write_text(json.dumps(edl), encoding="utf-8")


def test_plan_validate_resolves_scenes_into_the_timeline_and_summarises_them(launch: Path) -> None:
    write_edl(launch, EDL)

    result = invoke("plan", "validate", "launch")

    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert lines[0] == "✓ edl.json valid · product · 3 scenes · 16x9"
    assert lines[1] == "Duration 7.0s (limit 60s) · grid 120 bpm, steady (no music yet)"
    assert lines[2] == "Scenes: 2 title_card · 1 footage"
    timeline_file = launch / "build" / "timeline.json"
    assert lines[-1] == f"→ {timeline_file}"
    timeline = Timeline.model_validate_json(timeline_file.read_text(encoding="utf-8"))
    # 4 s of footage at 1x is 8 beats: 2 s + 1 s + 4 s at 30 fps.
    assert [(s.id, s.start, s.end) for s in timeline.scenes] == [
        ("intro", 0, 60),
        ("step1", 60, 90),
        ("pick", 90, 210),
    ]


def test_plan_validate_lays_scenes_on_the_beds_grid_once_there_is_music(launch: Path) -> None:
    write_edl(launch, {**EDL, "scenes": EDL["scenes"][:1]})
    beats = [round(k * 0.4, 3) for k in range(20)]
    music = {"beats": beats, "beats_per_bar": 3}
    (launch / "build").mkdir(exist_ok=True)
    (launch / "build" / "music.json").write_text(json.dumps(music), encoding="utf-8")

    out = json.loads(invoke("plan", "validate", "launch", "--json").stdout)

    assert out["duration_s"] == 1.6
    assert out["grid"] == {"bpm": 150.0, "beats_per_bar": 3, "from_music": True}


def test_plan_validate_json_lists_every_problem_with_its_code(launch: Path) -> None:
    footage = {**EDL["scenes"][2], "from": "c1.m.nope", "to": 3.0}
    write_edl(launch, {**EDL, "formats": ["9x16"], "scenes": [footage]})

    result = invoke("plan", "validate", "launch", "--json")

    assert result.exit_code == 1
    out = json.loads(result.stdout)
    assert out["valid"] is False
    assert sorted(e["code"] for e in out["errors"]) == [
        "product_format",
        "seconds_on_marked_clip",
        "unknown_marker",
    ]
    assert all(e["hint"] for e in out["errors"])


def test_plan_validate_prints_the_seconds_addressed_warning(launch: Path) -> None:
    analysis = screen("c1", 12.0)
    (launch / "analysis" / "c1.json").write_text(analysis.model_dump_json(), encoding="utf-8")
    write_edl(launch, {**EDL, "scenes": [{**EDL["scenes"][2], "from": 1.0, "to": 3.0}]})

    result = invoke("plan", "validate", "launch")

    assert result.exit_code == 0, result.output
    assert any(
        line.startswith("⚠ scene pick: c1 has no markers") for line in result.output.splitlines()
    )


def test_an_unknown_kind_in_the_edl_is_a_schema_error(launch: Path) -> None:
    write_edl(launch, {**EDL, "kind": "promo"})

    out = json.loads(invoke("plan", "validate", "launch", "--json").stdout)

    assert [e["code"] for e in out["errors"]] == ["invalid_edl"]
    assert "kind must be talk or product" in out["errors"][0]["message"]


def test_docs_edl_documents_the_product_edl(launch: Path) -> None:
    text = invoke("docs", "edl").output

    assert "## Product EDLs" in text
    assert "`c2.m.v1_shown`" in text
