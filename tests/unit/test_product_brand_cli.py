"""`plan validate` on a logo outro: the `[brand]` wordmark and mascot files it loads, or names."""

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from edl_fixtures import screen
from typer.testing import CliRunner

from motion_studio.cli import app
from motion_studio.edl import Timeline

BRAND_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "brand"
OUTRO: dict[str, Any] = {
    "id": "outro",
    "type": "logo_outro",
    "bars": 2,
    "tagline": "Write like the people you admire.",
    "url": "example.com",
}
BRAND_TOML = """
[brand]
wordmark = "library/brand/wordmark.svg"
mascot = { sheet = "library/brand/mascot.png", timings = "library/brand/mascot.json" }
"""

runner = CliRunner()


def invoke(*args: str | Path):
    return runner.invoke(app, [str(a) for a in args])


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    ws = tmp_path / "videos"
    assert invoke("init", ws).exit_code == 0
    monkeypatch.chdir(ws)
    assert invoke("new", "launch", "--kind", "product").exit_code == 0
    project = ws / "projects" / "launch"
    analysis = screen("c1", 12.0, {"open": 0.5})
    (project / "analysis" / "c1.json").write_text(analysis.model_dump_json(), encoding="utf-8")
    edl = {"kind": "product", "scenes": [OUTRO], "music": {"mode": "none"}}
    (project / "edl.json").write_text(json.dumps(edl), encoding="utf-8")
    for name in ("wordmark.svg", "mascot.png", "mascot.json"):
        shutil.copy(BRAND_FIXTURES / name, ws / "library" / "brand" / name)
    return ws


def configure(workspace: Path, toml: str) -> None:
    (workspace / "projects" / "launch" / "project.toml").open("a", encoding="utf-8").write(toml)


def validate(workspace: Path) -> tuple[int, dict[str, Any]]:
    result = invoke("plan", "validate", "launch", "--json")
    return result.exit_code, json.loads(result.stdout)


def test_the_timeline_carries_the_wordmark_and_the_mascots_sprite_sheet(workspace: Path) -> None:
    configure(workspace, BRAND_TOML)

    code, out = validate(workspace)

    assert code == 0, out
    timeline_file = workspace / "projects" / "launch" / "build" / "timeline.json"
    brand = Timeline.model_validate_json(timeline_file.read_text(encoding="utf-8")).brand
    assert brand.wordmark == "library/brand/wordmark.svg"
    assert brand.mascot is not None
    # The fixture is a 15 by 2 grid of 544x416 frames, 22 of them used, looping 4.36 s.
    assert (brand.mascot.sheet_width, brand.mascot.sheet_height) == (8160, 832)
    assert (brand.mascot.frame_width, brand.mascot.frame_height) == (544, 416)
    assert len(brand.mascot.frames) == 22
    assert sum(f.ms for f in brand.mascot.frames) == 4360
    assert brand.mascot.loops == 0


def test_an_outro_with_no_mascot_configured_names_the_key(workspace: Path) -> None:
    edl_path = workspace / "projects" / "launch" / "edl.json"
    edl = json.loads(edl_path.read_text(encoding="utf-8"))
    edl_path.write_text(json.dumps({**edl, "title": "Meet Pumpkit"}), encoding="utf-8")

    code, out = validate(workspace)

    assert code == 1
    [error] = out["errors"]
    assert error["code"] == "missing_brand_asset"
    assert error["message"] == "scene outro: [brand] mascot is not set"


def test_without_a_wordmark_the_outro_sets_the_title_in_type(workspace: Path) -> None:
    edl_path = workspace / "projects" / "launch" / "edl.json"
    edl = json.loads(edl_path.read_text(encoding="utf-8"))
    edl["title"] = "Meet Pumpkit"
    edl["scenes"][0]["mascot"] = False
    edl_path.write_text(json.dumps(edl), encoding="utf-8")

    code, out = validate(workspace)

    assert code == 0, out
    timeline = Timeline.model_validate_json(
        (workspace / "projects" / "launch" / "build" / "timeline.json").read_text(encoding="utf-8")
    )
    assert timeline.brand.wordmark is None
    [outro] = timeline.scenes
    assert outro.type == "logo_outro"
    assert outro.name == "Meet Pumpkit"


def test_an_outro_with_neither_a_wordmark_nor_a_title_is_an_error(workspace: Path) -> None:
    edl_path = workspace / "projects" / "launch" / "edl.json"
    edl = json.loads(edl_path.read_text(encoding="utf-8"))
    edl["scenes"][0]["mascot"] = False
    edl_path.write_text(json.dumps(edl), encoding="utf-8")

    code, out = validate(workspace)

    assert code == 1
    [error] = out["errors"]
    assert error["code"] == "missing_brand_asset"
    assert "no title" in error["message"]


def test_a_configured_file_that_does_not_exist_is_named_with_its_key(workspace: Path) -> None:
    configure(workspace, BRAND_TOML.replace("wordmark.svg", "gone.svg"))

    code, out = validate(workspace)

    assert code == 1
    [error] = out["errors"]
    assert error["message"] == (
        "scene outro: [brand] wordmark names library/brand/gone.svg, which does not exist"
    )


def test_a_mascot_with_broken_timings_is_named_with_its_key(workspace: Path) -> None:
    (workspace / "library" / "brand" / "mascot.json").write_text('{"frames": []}', encoding="utf-8")
    configure(workspace, BRAND_TOML)

    code, out = validate(workspace)

    assert code == 1
    [error] = out["errors"]
    assert error["message"].startswith(
        "scene outro: [brand] mascot timings library/brand/mascot.json is not valid:"
    )
    assert "frame_width" in error["message"]


def test_brand_assets_no_scene_needs_are_not_checked(workspace: Path) -> None:
    configure(workspace, BRAND_TOML.replace("wordmark.svg", "gone.svg"))
    edl = {
        "kind": "product",
        "scenes": [{"id": "t", "type": "title_card", "beats": 4, "headline": "Hi."}],
    }
    (workspace / "projects" / "launch" / "edl.json").write_text(json.dumps(edl), encoding="utf-8")

    code, out = validate(workspace)

    assert code == 0, out
