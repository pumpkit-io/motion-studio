"""AGENTS.md rule 6: every path a command writes is printed, however many clips there are.

The stage functions are replaced with canned reports so a 20-clip project costs nothing.
"""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from motion_studio.analyze import AnalyzeReport, ClipSummary
from motion_studio.cli import app
from motion_studio.ingest import ClipMedia, IngestReport
from motion_studio.paths import project_paths

CLIPS = 20

runner = CliRunner()


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "motion-studio.toml").write_text("", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def wrote(stdout: str) -> list[str]:
    return [
        line.split(" (")[0].removeprefix("wrote ")
        for line in stdout.splitlines()
        if line.startswith("wrote ")
    ]


def test_analyze_prints_every_analysis_file_it_wrote(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = project_paths(workspace, "demo")
    project.analysis.mkdir(parents=True)
    packed = project.analysis / "packed.md"
    packed.write_text("x" * 400, encoding="utf-8")
    clips = [
        ClipSummary(f"c{n}", "aroll", "en", 0.9, 10, 2, project.analysis / f"c{n}.json", True)
        for n in range(1, CLIPS + 1)
    ]
    report = AnalyzeReport(
        project=project,
        language="en",
        language_source="detected",
        clips=clips,
        retake_clusters=0,
        packed=packed,
        retakes=project.analysis / "retakes.json",
        assets=project.analysis / "assets.md",
    )
    monkeypatch.setattr("motion_studio.cli.analyze.analyze_project", lambda *_a, **_k: report)

    result = runner.invoke(app, ["analyze", "demo"])

    assert result.exit_code == 0, result.output
    expected = [str(c.path) for c in clips] + [
        str(report.retakes),
        str(packed),
        str(report.assets),
    ]
    assert wrote(result.stdout) == expected


def test_ingest_prints_every_media_file_it_wrote(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = project_paths(workspace, "demo")
    media = [
        ClipMedia(
            id=f"c{n}",
            role="aroll",
            source=f"raw/take{n}.mov",
            kind="video",
            mezzanine=f"media/c{n}.mp4",
            audio=f"media/c{n}.wav",
            audio_16k=f"media/c{n}_16k.wav",
            width=1080,
            height=1920,
            fps=30,
            duration_s=4.0,
        )
        for n in range(1, CLIPS + 1)
    ]
    report = IngestReport(project, media, [c.id for c in media], [])
    monkeypatch.setattr("motion_studio.cli.ingest.ingest_project", lambda *_a, **_k: report)

    result = runner.invoke(app, ["ingest", "demo"])

    assert result.exit_code == 0, result.output
    expected = [
        str(project.root / p) for c in media for p in (c.mezzanine, c.audio, c.audio_16k) if p
    ] + [str(project.media / "manifest.json")]
    assert wrote(result.stdout) == expected
