"""`plan draft`, `plan validate`, `words` and `docs edl` on a workspace with written analyses."""

import json
from pathlib import Path

import pytest
from edl_fixtures import asset, clip
from typer.testing import CliRunner

from reelcut.analysis import ClipAnalysis, find_retakes
from reelcut.cli import app
from reelcut.edl import Timeline

runner = CliRunner()

C1 = clip(
    "c1",
    "Welcome back um everyone.",
    "The reason I built",
    "The reason I built this is simple.",
    "See you soon.",
)
C2 = clip("c2", "The reason I built this is simple.")


def invoke(*args: str | Path):
    return runner.invoke(app, [str(a) for a in args])


def write_analyses(project: Path, clips: list[ClipAnalysis]) -> None:
    for analysis in clips:
        (project / "analysis" / f"{analysis.clip.id}.json").write_text(
            analysis.model_dump_json(indent=2), encoding="utf-8"
        )
    aroll = [c for c in clips if c.clip.role == "aroll"]
    (project / "analysis" / "retakes.json").write_text(
        find_retakes(aroll).model_dump_json(indent=2), encoding="utf-8"
    )


@pytest.fixture
def demo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    ws = tmp_path / "reels"
    assert invoke("init", ws).exit_code == 0
    take = tmp_path / "take.mov"
    take.write_bytes(b"not really a movie")
    monkeypatch.chdir(ws)
    result = invoke("new", "demo", "--from", take, "--title", "Demo video")
    assert result.exit_code == 0, result.output
    project = ws / "projects" / "demo"
    write_analyses(project, [C1, C2, asset("b1", "broll", 6.0)])
    return project


def edl_of(project: Path) -> dict[str, object]:
    return json.loads((project / "edl.json").read_text(encoding="utf-8"))


def test_plan_draft_writes_the_baseline_edl_and_prints_its_path(demo: Path) -> None:
    result = invoke("plan", "draft", "demo")

    assert result.exit_code == 0, result.output
    assert str(demo / "edl.json") in result.output
    data = edl_of(demo)
    assert data["title"] == "Demo video"
    assert data["language"] == "en"
    assert data["rationale"] == "deterministic draft"
    assert [s["id"] for s in data["segments"]] == ["c1-s0", "c1-s3", "c2-s0"]  # type: ignore[index]
    assert data["segments"][0]["from"] == "c1.w0"  # type: ignore[index]


def test_plan_draft_json_reports_the_segments_and_music(demo: Path) -> None:
    result = invoke("plan", "draft", "demo", "--json")

    assert result.exit_code == 0, result.output
    out = json.loads(result.stdout)
    assert out["ok"] is True
    assert out["edl"] == str(demo / "edl.json")
    assert out["segments"] == 3
    assert out["music"]["bpm"] > 0


def test_plan_draft_refuses_to_overwrite_without_force(demo: Path) -> None:
    (demo / "edl.json").write_text('{"segments": "my careful edit"}', encoding="utf-8")

    refused = invoke("plan", "draft", "demo")

    assert refused.exit_code == 1
    assert "--force" in refused.output
    assert edl_of(demo) == {"segments": "my careful edit"}

    forced = invoke("plan", "draft", "demo", "--force")

    assert forced.exit_code == 0, forced.output
    assert edl_of(demo)["rationale"] == "deterministic draft"


def test_plan_draft_needs_an_analysed_project(demo: Path) -> None:
    for path in (demo / "analysis").iterdir():
        path.unlink()

    result = invoke("plan", "draft", "demo", "--json")

    assert result.exit_code == 1
    assert "analyze demo" in json.loads(result.stdout)["hint"]


def test_plan_validate_writes_the_timeline_and_prints_the_summary(demo: Path) -> None:
    assert invoke("plan", "draft", "demo").exit_code == 0

    result = invoke("plan", "validate", "demo")

    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert len(lines) < 30
    assert lines[0] == "✓ edl.json valid · language en · 3 segments → 4 runs"
    assert lines[1].startswith("Duration ")
    assert lines[2].startswith('Hook (first 3s): "Welcome back everyone.')
    assert lines[3] == "Events: none"
    timeline = demo / "build" / "timeline.json"
    assert lines[-1] == f"→ {timeline}"
    parsed = Timeline.model_validate_json(timeline.read_text(encoding="utf-8"))
    assert [w.id for w in parsed.words][:3] == ["c1.w0", "c1.w1", "c1.w3"]


def test_plan_validate_json_returns_the_summary_as_data(demo: Path) -> None:
    assert invoke("plan", "draft", "demo").exit_code == 0

    out = json.loads(invoke("plan", "validate", "demo", "--json").stdout)

    assert out["ok"] is True
    assert out["valid"] is True
    assert out["segments"] == 3
    assert out["hard_fillers_removed"] == 1
    assert out["timeline"] == str(demo / "build" / "timeline.json")


def test_plan_validate_marks_the_plan_stage_done(demo: Path) -> None:
    assert invoke("plan", "draft", "demo").exit_code == 0
    assert invoke("plan", "validate", "demo").exit_code == 0

    status = json.loads(invoke("status", "demo", "--json").stdout)

    [plan] = [s for s in status["stages"] if s["name"] == "plan"]
    assert plan["status"] == "done"


def test_plan_validate_lists_every_error_and_exits_1(demo: Path) -> None:
    edl = {
        "segments": [
            {"id": "a", "from": "c1.s9", "to": "c1.s9"},
            {"id": "b", "from": "c1.w0", "to": "c2.w1"},
        ]
    }
    (demo / "edl.json").write_text(json.dumps(edl), encoding="utf-8")

    result = invoke("plan", "validate", "demo")

    assert result.exit_code == 1
    assert "✗ edl.json has 2 errors" in result.output
    assert "c1.s9 does not exist; c1 has s0-s3" in result.output
    assert "same clip" in result.output
    assert not (demo / "build" / "timeline.json").exists()

    out = json.loads(invoke("plan", "validate", "demo", "--json").stdout)
    assert out["ok"] is False
    assert {e["code"] for e in out["errors"]} == {"unknown_ref", "cross_clip"}


def test_plan_validate_reports_a_schema_error_by_field(demo: Path) -> None:
    (demo / "edl.json").write_text('{"segments": []}', encoding="utf-8")

    result = invoke("plan", "validate", "demo")

    assert result.exit_code == 1
    assert "segments:" in result.output


def test_plan_validate_rejects_broken_json(demo: Path) -> None:
    (demo / "edl.json").write_text("{not json", encoding="utf-8")

    result = invoke("plan", "validate", "demo")

    assert result.exit_code == 1
    assert "not valid JSON" in result.output


def test_plan_validate_without_an_edl_suggests_the_draft(demo: Path) -> None:
    result = invoke("plan", "validate", "demo")

    assert result.exit_code == 1
    assert "plan draft demo" in result.output


def test_words_prints_a_range_of_words_with_ids_and_times(demo: Path) -> None:
    result = invoke("words", "demo", "c1.s0", "c1.s1")

    assert result.exit_code == 0, result.output
    assert "c1.w0 Welcome 0.50-0.80" in result.output
    assert "c1.w2 {um} 1.30-1.60" in result.output
    assert "c1.w7 built 4.30-4.60" in result.output
    assert "c1.w8" not in result.output
    assert "c1.s1 ✗" in result.output


def test_words_with_one_reference_prints_that_utterance(demo: Path) -> None:
    out = json.loads(invoke("words", "demo", "c1.s3", "--json").stdout)

    assert [w["id"] for w in out["words"]] == ["c1.w15", "c1.w16", "c1.w17"]
    assert out["words"][0] == {
        "id": "c1.w15",
        "text": "See",
        "start": 9.5,
        "end": 9.8,
        "conf": 1.0,
        "filler": None,
        "utt": "c1.s3",
    }


def test_words_rejects_a_reversed_or_unknown_range(demo: Path) -> None:
    reversed_ = invoke("words", "demo", "c1.s2", "c1.s0")
    unknown = invoke("words", "demo", "c1.w99")

    assert reversed_.exit_code == 1
    assert "comes after" in reversed_.output
    assert unknown.exit_code == 1
    assert "c1.w99 does not exist; c1 has w0-w17" in unknown.output


def test_words_caps_a_long_range(demo: Path) -> None:
    long = clip("c1", *[f"Line number {n} of the long take." for n in range(40)])
    write_analyses(demo, [long])

    result = invoke("words", "demo", "c1.s0", "c1.s39")

    lines = result.output.splitlines()
    assert result.exit_code == 0
    assert len(lines) <= 30
    assert "more words" in lines[-1]


def test_docs_edl_prints_the_reference_from_any_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    result = invoke("docs", "edl")

    assert result.exit_code == 0, result.output
    assert result.output.startswith("# EDL reference")
    assert "drop_ranges" in result.output


def test_docs_edl_json_carries_the_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    out = json.loads(invoke("docs", "edl", "--json").stdout)

    assert out["ok"] is True
    assert out["text"].startswith("# EDL reference")
    assert Path(out["path"]).is_file()
