"""`motion-studio music` on a product project: bed length, alignment, the launch preset, candidates.

The stand-in worker writes a synthetic bed at 120 bpm whose sections are known: intro, build,
drop and ending of 8, 8, 8 and 4 bars from 0.25 s, the drop carrying a 660 Hz lead.
"""

import json
import shutil
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import soundfile as sf
from edl_fixtures import screen
from music_fixtures import jobs
from typer.testing import CliRunner

from motion_studio.cli import app
from motion_studio.edl import Timeline

runner = CliRunner()

BEAT = 0.5
BAR = 2.0
FIRST_BEAT_S = 0.25
RAW_HITS = {"intro_end": 16.25, "build": 16.25, "drop": 32.25, "ending": 48.25}
FPS = 30
BRAND_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "brand"
BRAND_TOML = """
[brand]
wordmark = "library/brand/wordmark.svg"
mascot = { sheet = "library/brand/mascot.png", timings = "library/brand/mascot.json" }
"""


def invoke(*args: str | Path):
    return runner.invoke(app, [str(a) for a in args])


def title(scene_id: str, bars: int) -> dict[str, Any]:
    return {"id": scene_id, "type": "title_card", "bars": bars, "headline": "Hello there."}


@pytest.fixture
def launch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, worker: Path) -> Path:
    monkeypatch.setenv("MOTION_STUDIO_MIN_FREE_GB", "0")
    (worker / "SECTIONED").write_text("")
    ws = tmp_path / "videos"
    assert invoke("init", ws).exit_code == 0
    monkeypatch.chdir(ws)
    assert invoke("new", "launch", "--kind", "product").exit_code == 0
    project = ws / "projects" / "launch"
    analysis = screen("c1", 12.0, {"open": 0.5, "picked": 4.5})
    (project / "analysis" / "c1.json").write_text(analysis.model_dump_json(), encoding="utf-8")
    return project


def write_edl(project: Path, scenes: list[dict[str, Any]], **music: Any) -> None:
    edl = {"kind": "product", "title": "Launch", "scenes": scenes, "music": music}
    (project / "edl.json").write_text(json.dumps(edl), encoding="utf-8")


def validated(project: Path) -> Timeline:
    result = invoke("plan", "validate", "launch")
    assert result.exit_code == 0, result.output
    return Timeline.model_validate_json((project / "build" / "timeline.json").read_text())


def scene_start_s(timeline: Timeline, scene_id: str) -> float:
    (scene,) = [s for s in timeline.scenes if s.id == scene_id]
    return scene.start / timeline.fps


def music_json(project: Path) -> dict[str, Any]:
    return json.loads((project / "build" / "music.json").read_text(encoding="utf-8"))


def lead_onset_s(wav: Path) -> float:
    """The first time the drop's 660 Hz lead is in the bed, from 40 ms windows 10 ms apart."""
    y, rate = sf.read(str(wav))
    mono = y.mean(axis=1)
    hop = rate // 100
    t = np.arange(hop * 4) / rate
    probe = np.exp(-2j * np.pi * 660 * t)
    level = np.array(
        [abs(np.dot(mono[i : i + len(t)], probe)) for i in range(0, len(mono) - len(t), hop)]
    )
    first = int(np.flatnonzero(level > 0.5 * level.max())[0])
    return (first * hop + len(t) / 2) / rate


def test_music_sizes_the_bed_from_the_scene_total(launch: Path, worker: Path) -> None:
    write_edl(
        launch, [title("intro", 4), title("outro", 2)], prompt="bright, instrumental", bpm=120
    )

    result = invoke("music", "launch")

    assert result.exit_code == 0, result.output
    (job,) = jobs(worker)
    assert job["duration"] == pytest.approx(12 + 3, abs=0.01)


def test_the_launch_preset_supplies_the_prompt_and_tempo(launch: Path, worker: Path) -> None:
    write_edl(launch, [title("intro", 4)], preset="launch")

    result = invoke("music", "launch", "--json")

    assert result.exit_code == 0, result.output
    (job,) = jobs(worker)
    assert "future house" in str(job["prompt"])
    assert job["bpm"] == 124
    assert json.loads(result.stdout)["preset"] == "launch"


def test_align_lands_the_drop_on_the_scene_and_ends_on_the_natural_ending(
    launch: Path, worker: Path
) -> None:
    # The outro starts at 12 s and lasts 16 s; the bed's drop is at 32.25 s and its ending
    # section 16 s after it, so 4 bars come out between them.
    scenes = [title("intro", 4), title("step1", 2), title("outro", 8)]
    write_edl(launch, scenes, bpm=120, seed=3, align={"hit": "drop", "at": "outro"})

    result = invoke("music", "launch", "--json")

    assert result.exit_code == 0, result.output
    timeline = validated(launch)
    at = scene_start_s(timeline, "outro")
    wav = launch / "build" / "music.wav"
    assert abs(lead_onset_s(wav) - at) <= 1 / FPS
    assert sf.info(str(wav)).duration == pytest.approx(timeline.duration_frames / FPS, abs=0.01)
    info = music_json(launch)
    hits = {h["name"]: h["time_s"] for h in info["hits"]}
    assert hits["drop"] == pytest.approx(at, abs=1 / FPS)
    assert hits["ending"] == pytest.approx(at + 8, abs=BEAT)
    assert info["align"]["ending"] == "natural"
    (edit,) = info["align"]["edits"]
    assert edit["bars"] == -4
    assert edit["crossfade_ms"] == 30
    assert min(abs(edit["at_s"] - b) for b in info["bars"]) < 0.002


def test_align_repeats_whole_bars_when_the_hit_comes_too_early(launch: Path, worker: Path) -> None:
    # The intro ends at 16.25 s in the bed but the scene starts at 20 s: two bars go in.
    scenes = [title("intro", 10), title("step1", 2), title("outro", 2)]
    write_edl(launch, scenes, bpm=120, align={"hit": "intro_end", "at": "step1"})

    result = invoke("music", "launch", "--json")

    assert result.exit_code == 0, result.output
    timeline = validated(launch)
    at = scene_start_s(timeline, "step1")
    info = music_json(launch)
    hits = {h["name"]: h["time_s"] for h in info["hits"]}
    assert hits["intro_end"] == pytest.approx(at, abs=1 / FPS)
    edits = info["align"]["edits"]
    assert sum(e["bars"] for e in edits if e["at_s"] < at) == 2
    for edit in edits:
        assert min(abs(edit["at_s"] - b) for b in info["bars"]) < 0.002
    gaps = np.diff(info["beats"])
    assert gaps == pytest.approx(BEAT, abs=0.002)


def test_a_bed_cut_short_rings_out_on_an_echo_tail(launch: Path, worker: Path) -> None:
    scenes = [title("intro", 4), title("outro", 3)]
    write_edl(launch, scenes, bpm=120, align={"hit": "drop", "at": "outro"})

    result = invoke("music", "launch", "--json")

    assert result.exit_code == 0, result.output
    timeline = validated(launch)
    info = music_json(launch)
    assert info["align"]["ending"] == "echo"
    y, rate = sf.read(str(launch / "build" / "music.wav"))
    assert len(y) / rate == pytest.approx(timeline.duration_frames / FPS, abs=0.01)
    tail_at = {h["name"]: h["time_s"] for h in info["hits"]}["ending"]
    beats = [y[int((tail_at + k * BEAT) * rate) : int((tail_at + (k + 1) * BEAT) * rate)]
             for k in range(3)]  # fmt: skip
    levels = [float(np.sqrt(np.mean(b**2))) for b in beats]
    assert levels[0] > levels[1] > levels[2] > 0
    assert float(np.abs(y[-int(0.02 * rate) :]).max()) < 0.01


def test_align_needs_a_hit_the_bed_has(launch: Path, worker: Path) -> None:
    (worker / "SECTIONED").unlink()
    write_edl(launch, [title("intro", 4), title("outro", 2)], align={"hit": "drop", "at": "outro"})

    result = invoke("music", "launch", "--json")

    assert result.exit_code == 1
    out = json.loads(result.stdout)
    assert "drop" in out["error"]


def test_validate_rejects_an_align_at_a_scene_that_does_not_exist(launch: Path) -> None:
    write_edl(launch, [title("intro", 4)], align={"hit": "drop", "at": "logo"})

    result = invoke("plan", "validate", "launch", "--json")

    assert result.exit_code == 1
    codes = [e["code"] for e in json.loads(result.stdout)["errors"]]
    assert codes == ["align_scene"]


def test_validate_rejects_an_align_without_a_generated_bed(launch: Path) -> None:
    write_edl(launch, [title("intro", 4)], mode="none", align={"hit": "drop", "at": "intro"})

    result = invoke("plan", "validate", "launch", "--json")

    assert result.exit_code == 1
    codes = [e["code"] for e in json.loads(result.stdout)["errors"]]
    assert codes == ["align_mode"]


def test_candidates_are_generated_in_one_worker_and_listed(launch: Path, worker: Path) -> None:
    write_edl(launch, [title("intro", 4), title("outro", 4)], bpm=120, seed=7)

    result = invoke("music", "launch", "--candidates", "3", "--json")

    assert result.exit_code == 0, result.output
    made = jobs(worker)
    assert [j["seed"] for j in made] == [7, 8, 9]
    assert len({j["pid"] for j in made}) == 1
    out = json.loads(result.stdout)
    assert out["model_loads"] == 1
    candidates = music_json(launch)["candidates"]
    assert [c["seed"] for c in candidates] == [7, 8, 9]
    for candidate in candidates:
        assert candidate["detected_bpm"] == pytest.approx(120, abs=0.5)
        hits = {h["name"]: h["time_s"] for h in candidate["hits"]}
        assert hits["drop"] == pytest.approx(RAW_HITS["drop"], abs=BEAT)
    assert music_json(launch)["seed"] == 7


def test_the_edl_seed_picks_a_candidate_without_generating_again(
    launch: Path, worker: Path
) -> None:
    write_edl(launch, [title("intro", 4)], bpm=120, seed=7)
    assert invoke("music", "launch", "--candidates", "3").exit_code == 0
    write_edl(launch, [title("intro", 4)], bpm=120, seed=9)

    result = invoke("music", "launch", "--json")

    assert result.exit_code == 0, result.output
    assert len(jobs(worker)) == 3
    assert json.loads(result.stdout)["seed"] == 9
    assert json.loads(result.stdout)["model_loads"] == 0


def test_low_memory_before_a_candidate_stops_and_keeps_those_made(
    launch: Path, worker: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_edl(launch, [title("intro", 4)], bpm=120, seed=1)
    monkeypatch.setenv("MOTION_STUDIO_MIN_FREE_MEMORY_GB", "4")
    free = iter([16.0, 8.0, 1.5])
    monkeypatch.setattr("motion_studio.music.acestep.free_memory_gb", lambda: next(free))

    stopped = invoke("music", "launch", "--candidates", "3", "--json")
    monkeypatch.setattr("motion_studio.music.acestep.free_memory_gb", lambda: 16.0)
    again = invoke("music", "launch", "--candidates", "3", "--json")

    assert stopped.exit_code == 1
    error = json.loads(stopped.stdout)
    assert "1.5 GB" in error["error"]
    assert "candidate 3 of 3" in error["error"]
    assert "2 already made" in error["hint"]
    assert again.exit_code == 0, again.output
    assert [j["seed"] for j in jobs(worker)] == [1, 2, 3]
    assert [c["seed"] for c in music_json(launch)["candidates"]] == [1, 2, 3]


def test_candidates_need_a_generated_bed(launch: Path) -> None:
    write_edl(launch, [title("intro", 4)], mode="none")

    result = invoke("music", "launch", "--candidates", "2", "--json")

    assert result.exit_code == 1
    assert "generate" in json.loads(result.stdout)["error"]


def test_more_than_four_candidates_is_refused(launch: Path) -> None:
    write_edl(launch, [title("intro", 4)])

    result = invoke("music", "launch", "--candidates", "5")

    assert result.exit_code != 0


def test_music_generates_for_an_edl_ending_on_a_branded_logo_outro(
    launch: Path, worker: Path
) -> None:
    ws = launch.parents[1]
    for name in ("wordmark.svg", "mascot.png", "mascot.json"):
        shutil.copy(BRAND_FIXTURES / name, ws / "library" / "brand" / name)
    (launch / "project.toml").open("a", encoding="utf-8").write(BRAND_TOML)
    outro = {"id": "logo_outro", "type": "logo_outro", "bars": 4, "url": "example.com"}
    write_edl(
        launch, [title("intro", 4), outro], bpm=120, align={"hit": "drop", "at": "logo_outro"}
    )

    result = invoke("music", "launch", "--json")

    assert result.exit_code == 0, result.output
    assert len(jobs(worker)) == 1
    timeline = validated(launch)
    hits = {h["name"]: h["time_s"] for h in music_json(launch)["hits"]}
    assert hits["drop"] == pytest.approx(scene_start_s(timeline, "logo_outro"), abs=1 / FPS)
