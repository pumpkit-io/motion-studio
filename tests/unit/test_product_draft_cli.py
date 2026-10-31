"""`plan draft` on a product workspace with written analyses: the baseline scenes it lays out."""

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from edl_fixtures import asset, screen
from typer.testing import CliRunner

from motion_studio.analysis.models import ClipAnalysis, CursorSample
from motion_studio.cli import app
from motion_studio.edl import Timeline

BRAND_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "brand"
WORDMARK_TOML = '\n[brand]\nwordmark = "library/brand/wordmark.svg"\n'
MASCOT_TOML = (
    'mascot = { sheet = "library/brand/mascot.png", timings = "library/brand/mascot.json" }\n'
)

runner = CliRunner()


def invoke(*args: str | Path):
    return runner.invoke(app, [str(a) for a in args])


@pytest.fixture
def launch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Two web recordings, one image and a wordmark."""
    ws = tmp_path / "videos"
    assert invoke("init", ws).exit_code == 0
    monkeypatch.chdir(ws)
    result = invoke("new", "launch", "--kind", "product", "--title", "Meet Pumpkit")
    assert result.exit_code == 0, result.output
    project = ws / "projects" / "launch"
    shutil.copy(BRAND_FIXTURES / "wordmark.svg", ws / "library" / "brand" / "wordmark.svg")
    configure(project, WORDMARK_TOML)
    write(project, web(screen("c1", 12.0, {"open": 0.5, "picked": 4.5}, source="pick-authors")))
    write(project, web(screen("c2", 8.0, {"start": 1.0, "typed": 3.0, "posted": 6.0})))
    write(project, asset("i1", "image", 0.0))
    return project


def web(analysis: ClipAnalysis) -> ClipAnalysis:
    """As `record web` writes it: with the cursor track a terminal take lacks."""
    return analysis.model_copy(update={"cursor": [CursorSample(t=0.5, x=10, y=10)]})


def configure(project: Path, toml: str) -> None:
    with (project / "project.toml").open("a", encoding="utf-8") as file:
        file.write(toml)


def write(project: Path, analysis: ClipAnalysis) -> None:
    path = project / "analysis" / f"{analysis.clip.id}.json"
    path.write_text(analysis.model_dump_json(), encoding="utf-8")


def edl_of(project: Path) -> dict[str, Any]:
    return json.loads((project / "edl.json").read_text(encoding="utf-8"))


def scenes_of(project: Path) -> list[dict[str, Any]]:
    return edl_of(project)["scenes"]


def timeline_of(project: Path) -> Timeline:
    path = project / "build" / "timeline.json"
    return Timeline.model_validate_json(path.read_text(encoding="utf-8"))


def test_the_draft_lays_out_intro_steps_proof_and_outro_and_validates_cleanly(
    launch: Path,
) -> None:
    result = invoke("plan", "draft", "launch")

    assert result.exit_code == 0, result.output
    assert str(launch / "edl.json") in result.output
    edl = edl_of(launch)
    assert edl["kind"] == "product"
    assert edl["title"] == "Meet Pumpkit"
    assert [(s["id"], s["type"]) for s in edl["scenes"]] == [
        ("intro", "title_card"),
        ("step1", "title_card"),
        ("demo1", "footage"),
        ("step2", "title_card"),
        ("demo2", "footage"),
        ("proof1", "proof"),
        ("outro", "logo_outro"),
    ]
    intro, step1, c1, step2, c2, _, outro = edl["scenes"]
    assert intro["headline"] == "Meet Pumpkit"
    assert (step1["step"], step1["headline"]) == ("01", "Pick authors")
    assert (step2["step"], step2["headline"]) == ("02", "C2")
    assert (c1["clip"], c1["from"], c1["to"]) == ("c1", "c1.m.open", "c1.m.picked")
    assert (c2["from"], c2["to"]) == ("c2.m.start", "c2.m.posted")
    assert (c1["device_frame"], c2["device_frame"]) == ("browser", "browser")
    assert outro["mascot"] is False

    validated = invoke("plan", "validate", "launch", "--json")

    assert validated.exit_code == 0, validated.output
    assert json.loads(validated.stdout)["warnings"] == []


def test_without_music_the_draft_sits_on_a_steady_120_bpm_grid(launch: Path) -> None:
    out = json.loads(invoke("plan", "draft", "launch", "--json").stdout)

    assert out["grid"] == {"bpm": 120.0, "beats_per_bar": 4, "from_music": False}
    assert out["music"] == {"mode": "generate", "preset": "launch", "seed": 1}
    rationale = edl_of(launch)["rationale"]
    assert "steady grid (no music yet) at 120 bpm" in rationale
    assert rationale == out["rationale"]
    assert invoke("plan", "validate", "launch").exit_code == 0
    # Cards are one 2 s bar, the proof and outro two; footage runs first to last marker at 1x.
    assert [(s.id, s.start, s.end) for s in timeline_of(launch).scenes] == [
        ("intro", 0, 60),
        ("step1", 60, 120),
        ("demo1", 120, 240),
        ("step2", 240, 300),
        ("demo2", 300, 450),
        ("proof1", 450, 570),
        ("outro", 570, 690),
    ]


def test_with_a_bed_the_draft_sits_on_its_grid(launch: Path) -> None:
    # 150 bpm in 3/4: a bar is 1.2 s, so a card is two bars and the proof and outro three.
    music = {"beats": [round(k * 0.4, 3) for k in range(200)], "beats_per_bar": 3}
    (launch / "build").mkdir(exist_ok=True)
    (launch / "build" / "music.json").write_text(json.dumps(music), encoding="utf-8")

    out = json.loads(invoke("plan", "draft", "launch", "--json").stdout)

    assert out["grid"] == {"bpm": 150.0, "beats_per_bar": 3, "from_music": True}
    assert "the bed's grid at 150 bpm, 3 beats a bar" in out["rationale"]
    lengths = {s["id"]: s.get("bars") for s in scenes_of(launch)}
    assert lengths == {
        "intro": 2,
        "step1": 2,
        "demo1": None,
        "step2": 2,
        "demo2": None,
        "proof1": 3,
        "outro": 3,
    }
    assert invoke("plan", "validate", "launch").exit_code == 0
    starts = [s.start for s in timeline_of(launch).scenes]
    assert starts == [0, 72, 144, 264, 336, 480, 588]
    assert all(start % 12 == 0 for start in starts)


def test_a_recording_without_markers_gets_footage_in_source_seconds_and_the_warning(
    launch: Path,
) -> None:
    write(launch, screen("c2", 8.0))

    assert invoke("plan", "draft", "launch").exit_code == 0

    demo2 = next(s for s in scenes_of(launch) if s["id"] == "demo2")
    assert (demo2["from"], demo2["to"]) == (0.0, 8.0)
    assert "c2 has no markers" in edl_of(launch)["rationale"]
    out = json.loads(invoke("plan", "validate", "launch", "--json").stdout)
    assert out["ok"] is True
    assert [w["code"] for w in out["warnings"]] == ["seconds_addressed"]


def test_a_recording_with_one_marker_plays_whole_around_it(launch: Path) -> None:
    write(launch, screen("c2", 8.0, {"only": 3.0}))

    assert invoke("plan", "draft", "launch").exit_code == 0

    demo2 = next(s for s in scenes_of(launch) if s["id"] == "demo2")
    assert demo2["from"] == {"marker": "c2.m.only", "offset_s": -3.0}
    assert demo2["to"] == {"marker": "c2.m.only", "offset_s": 5.0}
    assert invoke("plan", "validate", "launch").exit_code == 0
    assert timeline_of(launch).scenes[4].src_out_s == 8.0  # type: ignore[union-attr]


def test_a_terminal_take_is_drawn_in_a_terminal_frame(launch: Path) -> None:
    write(launch, screen("c2", 8.0, {"start": 1.0, "done": 6.0}))

    assert invoke("plan", "draft", "launch").exit_code == 0

    frames = {s["id"]: s.get("device_frame") for s in scenes_of(launch) if s["type"] == "footage"}
    assert frames == {"demo1": "browser", "demo2": "terminal"}
    assert "c2 has markers but no cursor or elements" in edl_of(launch)["rationale"]


def test_the_outro_draws_the_mascot_when_one_is_configured(launch: Path) -> None:
    ws = launch.parents[1]
    for name in ("mascot.png", "mascot.json"):
        shutil.copy(BRAND_FIXTURES / name, ws / "library" / "brand" / name)
    # Appended under the fixture's [brand] table, the last one in project.toml.
    configure(launch, MASCOT_TOML)

    assert invoke("plan", "draft", "launch").exit_code == 0

    assert scenes_of(launch)[-1]["mascot"] is True
    assert invoke("plan", "validate", "launch").exit_code == 0


def test_without_a_wordmark_the_draft_ends_on_the_title_in_type_and_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = tmp_path / "videos"
    assert invoke("init", ws).exit_code == 0
    monkeypatch.chdir(ws)
    assert invoke("new", "launch", "--kind", "product").exit_code == 0
    project = ws / "projects" / "launch"
    write(project, screen("c1", 6.0, {"open": 0.5, "done": 4.5}))

    assert invoke("plan", "draft", "launch").exit_code == 0

    assert [s["id"] for s in scenes_of(project)] == ["intro", "step1", "demo1", "outro"]
    assert (
        "[brand] has no wordmark, so the outro sets the title in type."
        in (edl_of(project)["rationale"])
    )
    assert invoke("plan", "validate", "launch").exit_code == 0
    outro = timeline_of(project).scenes[-1]
    assert outro.type == "logo_outro"
    assert outro.name == "launch"


def test_a_mascot_that_does_not_load_is_left_out_of_the_outro_and_named(launch: Path) -> None:
    configure(launch, MASCOT_TOML)

    assert invoke("plan", "draft", "launch").exit_code == 0

    assert scenes_of(launch)[-1]["mascot"] is False
    assert (
        "The outro has no mascot: the [brand] mascot names library/brand/mascot.png, which does "
        "not exist." in edl_of(launch)["rationale"]
    )
    assert invoke("plan", "validate", "launch").exit_code == 0


def test_the_draft_needs_a_recording_or_an_image(launch: Path) -> None:
    for path in (launch / "analysis").iterdir():
        path.unlink()
    write(launch, asset("b1", "broll", 4.0))

    result = invoke("plan", "draft", "launch", "--json")

    assert result.exit_code == 1
    assert "no screen recordings or images" in json.loads(result.stdout)["error"]


def test_the_product_draft_refuses_to_overwrite_without_force(launch: Path) -> None:
    assert invoke("plan", "draft", "launch").exit_code == 0
    (launch / "edl.json").write_text('{"kind": "product"}', encoding="utf-8")

    assert invoke("plan", "draft", "launch").exit_code == 1
    assert invoke("plan", "draft", "launch", "--force").exit_code == 0
    assert edl_of(launch)["scenes"]


def test_the_draft_prints_its_scenes_and_grid(launch: Path) -> None:
    result = invoke("plan", "draft", "launch")

    lines = result.output.splitlines()
    assert lines[0] == f"wrote {launch / 'edl.json'}"
    assert lines[1] == "  7 scenes: intro · step1 · demo1 · step2 · demo2 · proof1 · outro"
    assert lines[2] == "  grid 120 bpm, steady (no music yet)"
    assert lines[-1] == "next: write the headlines, then `motion-studio plan validate launch`"
