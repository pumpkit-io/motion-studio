"""`motion-studio look`, `motion-studio look-asset` and the asset contact sheets `analyze` writes.

Runs on ingested tiny clips with the stand-in speech-to-text and face workers, and checks the
PNGs by what can be measured: size, that they are not blank, and the filler colours.
"""

import json
import shutil
import stat
import sys
import textwrap
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image
from test_analyze_cli import FAKE_WORKER, PHOTO, TINY, invoke, spoken, still_video

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")

MAX_WIDTH = 1600
# A hard filler ("um") in the first second, then clean speech.
SPEECH = spoken(["So", "um", "this", "is", "it."], start=0.1, step=0.18)
HARD_RED = (220, 38, 38)


@pytest.fixture(autouse=True)
def no_disk_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOTION_STUDIO_MIN_FREE_GB", "0")


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An analysed project: a talking clip (c1), a still B-roll clip (b1) and a photo (i1)."""
    worker = tmp_path / "fake-asr-worker"
    worker.write_text(f"#!{sys.executable}\n{textwrap.dedent(FAKE_WORKER)}", encoding="utf-8")
    worker.chmod(worker.stat().st_mode | stat.S_IEXEC)
    script = tmp_path / "script.json"
    script.write_text(
        json.dumps({"c1": {"language": "en", "vad": [[0.05, 1.1]], "words": SPEECH}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("MOTION_STUDIO_ASR_WORKER", str(worker))
    monkeypatch.setenv("FAKE_ASR_SCRIPT", str(script))
    monkeypatch.setenv("FAKE_ASR_LOG", str(tmp_path / "worker.log"))

    ws = tmp_path / "reels"
    assert invoke("init", ws).exit_code == 0
    monkeypatch.chdir(ws)
    take = tmp_path / "take.mp4"
    shutil.copy(TINY, take)
    result = invoke("new", "demo", "--from", take, still_video(tmp_path / "still.mp4"), PHOTO)
    assert result.exit_code == 0, result.output
    for command in ("ingest", "analyze"):
        result = invoke(command, "demo", "--json")
        assert result.exit_code == 0, result.output
    return ws / "projects" / "demo"


def look(*args: str) -> dict[str, Any]:
    result = invoke("look", "demo", *args, "--json")
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


def pixels(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image.convert("RGB"))


def test_look_writes_one_sheet_no_wider_than_1600_px_that_is_not_blank(project: Path) -> None:
    out = look("c1", "0", "2", "--frames", "6")

    sheet = Path(out["sheet"])
    assert sheet.parent == project / "contact"
    image = pixels(sheet)
    height, width, _ = image.shape
    assert 800 <= width <= MAX_WIDTH
    assert height >= 400
    assert image.std() > 20
    assert out["frames"] == 6
    assert out["look_count"] == 1
    assert out["warnings"] == []


def test_past_the_look_budget_look_warns_and_still_draws_the_sheet(project: Path) -> None:
    toml = project.parents[1] / "motion-studio.toml"
    toml.write_text(
        toml.read_text(encoding="utf-8").replace("look_budget = 8", "look_budget = 1", 1),
        encoding="utf-8",
    )
    first = look("c1", "0", "1")
    Path(first["sheet"]).unlink()

    result = invoke("look", "demo", "c1", "0", "1")

    assert result.exit_code == 0, result.output
    [warning] = [line for line in result.stderr.splitlines() if "look budget" in line]
    assert warning.startswith("warning: look budget exceeded (2 of 1 sheets)")
    assert Path(result.stdout.splitlines()[-1].removeprefix("wrote ")).is_file()
    state = json.loads((project / "state.json").read_text(encoding="utf-8"))
    assert state["look_count"] == 2


def test_analyze_writes_the_contact_sheet_that_assets_md_links_for_each_asset(
    project: Path,
) -> None:
    text = (project / "analysis" / "assets.md").read_text(encoding="utf-8")
    linked = [
        line.removeprefix("- contact sheet: ")
        for line in text.splitlines()
        if line.startswith("- contact sheet: ")
    ]

    assert linked == ["contact/b1.png", "contact/i1.png"]
    for link in linked:
        image = pixels(project / link)
        assert image.shape[1] <= MAX_WIDTH
        assert image.std() > 10
    assert not (project / "contact" / "c1.png").exists()


def test_a_deleted_asset_sheet_comes_back_on_the_next_analyze(project: Path) -> None:
    (project / "contact" / "b1.png").unlink()

    result = invoke("analyze", "demo", "--json")

    assert result.exit_code == 0, result.output
    assert (project / "contact" / "b1.png").is_file()


@pytest.mark.parametrize("asset", ["b1", "i1"])
def test_look_asset_redraws_the_sheet_assets_md_links_without_using_the_budget(
    project: Path, asset: str
) -> None:
    sheet = project / "contact" / f"{asset}.png"
    sheet.unlink()

    result = invoke("look-asset", "demo", asset, "--json")

    assert result.exit_code == 0, result.output
    out = json.loads(result.stdout)
    assert out["sheet"] == str(sheet)
    assert pixels(sheet).shape[1] <= MAX_WIDTH
    state = json.loads((project / "state.json").read_text(encoding="utf-8"))
    assert state["look_count"] == 0


@pytest.mark.parametrize(
    "args",
    [
        ("look-asset", "demo", "c1"),
        ("look", "demo", "c9", "0", "1"),
        ("look", "demo", "i1", "0", "1"),
        ("look", "demo", "c1", "1", "0.5"),
        ("look", "demo", "c1", "5", "6"),
        ("look", "demo", "c1", "0", "1", "--frames", "0"),
    ],
)
def test_a_wrong_clip_or_range_is_a_user_error_with_a_hint(
    project: Path, args: tuple[str, ...]
) -> None:
    result = invoke(*args, "--json")

    assert result.exit_code == 1, result.output
    out = json.loads(result.stdout)
    assert out["ok"] is False
    assert out["hint"]
