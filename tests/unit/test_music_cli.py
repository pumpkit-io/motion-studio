"""`motion-studio music` on a planned project with a stand-in ACE-Step worker and voice detector."""

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from conftest import FakeTools
from edl_fixtures import clip
from typer.testing import CliRunner

from motion_studio.analysis import Span
from motion_studio.cli import app
from motion_studio.edl import Timeline

runner = CliRunner()

# Writes a 48 kHz stereo click track at the job's BPM, or loud noise (vocals to the stub
# detector) for the seeds listed in the VOCAL_SEEDS file, or the numpy expression of t in
# BASS_HEAVY when that file exists. Every job is appended to jobs.jsonl.
FAKE_WORKER = """
import json, sys
from pathlib import Path
import numpy as np, soundfile as sf

job = json.loads(sys.stdin.read())
here = Path(__file__).parent
with open(here / "jobs.jsonl", "a") as log:
    log.write(json.dumps(job) + "\\n")
vocal = here / "VOCAL_SEEDS"
vocal_seeds = json.loads(vocal.read_text()) if vocal.exists() else []
sr = 48000
n = int(job["duration"] * sr)
t = np.arange(n) / sr
if job["seed"] in vocal_seeds:
    y = np.random.default_rng(0).uniform(-0.9, 0.9, n)
elif (here / "BASS_HEAVY").exists():
    y = eval((here / "BASS_HEAVY").read_text(), {"np": np, "t": t})
else:
    y = np.zeros(n)
    click = 0.3 * np.sin(2 * np.pi * 1000 * np.arange(2400) / sr) * np.exp(-np.arange(2400) / 300)
    step = 60 / (job["bpm"] or 120)
    t = 0.5
    while t * sr + 2400 < n:
        i = int(t * sr)
        y[i:i + 2400] += click
        t += step
out = Path(job["out"])
out.parent.mkdir(parents=True, exist_ok=True)
sf.write(out, np.stack([y, y], axis=1).astype(np.float32), sr)
print("model chatter on stderr", file=sys.stderr)
print(json.dumps({"wav": str(out), "seed": job["seed"], "load_s": 1.0, "generate_s": 2.0}))
"""


class LoudIsSpeech:
    """Stands in for Silero: any 0.5 s window with an RMS above 0.1 counts as speech."""

    def __init__(self, path: Path | None = None) -> None:
        pass

    def speech(self, samples: np.ndarray, params: object = None) -> list[Span]:
        window = 8000
        spans: list[Span] = []
        for start in range(0, len(samples) - window + 1, window):
            if float(np.sqrt(np.mean(samples[start : start + window] ** 2))) > 0.1:
                spans.append(Span(start=start / 16000, end=(start + window) / 16000))
        return spans


def invoke(*args: str | Path):
    return runner.invoke(app, [str(a) for a in args])


def write_analysis(project: Path) -> None:
    analysis = clip(
        "c1",
        "Welcome back everyone.",
        "Today I show you how I edit.",
        "It takes one command.",
        "See you soon.",
    )
    (project / "analysis" / "c1.json").write_text(analysis.model_dump_json(), encoding="utf-8")


@pytest.fixture
def worker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    tools = tmp_path / "worker"
    tools.mkdir()
    script = FakeTools(tools).add("fake-acestep", FAKE_WORKER)
    monkeypatch.setenv("MOTION_STUDIO_MUSIC_WORKER", str(script))
    monkeypatch.setattr("motion_studio.music.vocals.SileroVad", LoudIsSpeech)
    return tools


@pytest.fixture
def demo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, worker: Path) -> Path:
    # CI runners have less free disk than the guard's default threshold.
    monkeypatch.setenv("MOTION_STUDIO_MIN_FREE_GB", "0")
    ws = tmp_path / "reels"
    assert invoke("init", ws).exit_code == 0
    take = tmp_path / "take.mov"
    take.write_bytes(b"not really a movie")
    monkeypatch.chdir(ws)
    assert invoke("new", "demo", "--from", take).exit_code == 0
    project = ws / "projects" / "demo"
    write_analysis(project)
    assert invoke("plan", "draft", "demo").exit_code == 0
    return project


def set_music(project: Path, **music: object) -> None:
    edl = json.loads((project / "edl.json").read_text(encoding="utf-8"))
    edl["music"] = music
    (project / "edl.json").write_text(json.dumps(edl), encoding="utf-8")


def timeline_seconds(project: Path) -> float:
    assert invoke("plan", "validate", "demo").exit_code == 0
    timeline = Timeline.model_validate_json((project / "build/timeline.json").read_text())
    return timeline.duration_frames / timeline.fps


def jobs(worker: Path) -> list[dict[str, object]]:
    log = worker / "jobs.jsonl"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines()]


def test_music_generates_the_bed_and_records_how_in_music_json(demo: Path, worker: Path) -> None:
    set_music(demo, mode="generate", prompt="lo-fi piano, warm, instrumental", bpm=120, seed=7)
    seconds = timeline_seconds(demo)

    result = invoke("music", "demo")

    assert result.exit_code == 0, result.output
    wav = demo / "build" / "music.wav"
    assert str(wav) in result.output
    assert str(demo / "build" / "music.json") in result.output
    (job,) = jobs(worker)
    assert job["duration"] == pytest.approx(seconds + 3, abs=0.01)
    assert job["prompt"] == "lo-fi piano, warm, instrumental"
    info = json.loads((demo / "build" / "music.json").read_text(encoding="utf-8"))
    assert info["mode"] == "generate"
    assert info["prompt"] == "lo-fi piano, warm, instrumental"
    assert info["seed"] == 7
    assert info["bpm"] == 120
    assert info["model"].startswith("ACE-Step/Ace-Step1.5@")
    assert "licence" in info
    beats = info["beats"]
    assert len(beats) >= 4
    gaps = np.diff(beats)
    assert float(np.median(gaps)) == pytest.approx(0.5, abs=0.03)
    assert sf.info(str(wav)).duration == pytest.approx(seconds + 3, abs=0.05)


def test_a_bed_with_vocals_is_regenerated_with_the_next_seed(demo: Path, worker: Path) -> None:
    set_music(demo, mode="generate", prompt="indie electronic, instrumental", bpm=100, seed=4)
    (worker / "VOCAL_SEEDS").write_text("[4, 5]")

    result = invoke("music", "demo", "--json")

    assert result.exit_code == 0, result.output
    out = json.loads(result.stdout)
    assert [j["seed"] for j in jobs(worker)] == [4, 5, 6]
    assert out["seed"] == 6
    assert [a["accepted"] for a in out["attempts"]] == [False, False, True]
    assert out["attempts"][0]["speech_ratio"] > 0.5


def test_music_gives_up_after_three_beds_with_vocals(demo: Path, worker: Path) -> None:
    set_music(demo, mode="generate", prompt="pop song", seed=1)
    (worker / "VOCAL_SEEDS").write_text("[1, 2, 3]")

    result = invoke("music", "demo", "--json")

    assert result.exit_code == 1
    assert "vocals" in json.loads(result.stdout)["error"]
    assert len(jobs(worker)) == 3
    assert not (demo / "build" / "music.wav").exists()
    assert not (demo / "build" / "music.json").exists()


def test_an_unchanged_music_block_is_not_generated_again(demo: Path, worker: Path) -> None:
    set_music(demo, mode="generate", prompt="lo-fi piano, instrumental", seed=2)
    assert invoke("music", "demo").exit_code == 0

    again = invoke("music", "demo", "--json")
    set_music(demo, mode="generate", prompt="lo-fi piano, instrumental", seed=3)
    changed = invoke("music", "demo")

    assert json.loads(again.stdout)["fresh"] is True
    assert changed.exit_code == 0
    assert [j["seed"] for j in jobs(worker)] == [2, 3]


def test_generate_without_the_acestep_environment_exits_2(
    demo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MOTION_STUDIO_MUSIC_WORKER")

    result = invoke("music", "demo", "--json")

    assert result.exit_code == 2
    assert "setup --music" in json.loads(result.stdout)["hint"]


def test_music_refuses_to_start_below_the_free_disk_threshold(
    demo: Path, worker: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MOTION_STUDIO_MIN_FREE_GB", "1000000")

    result = invoke("music", "demo")

    assert result.exit_code == 2
    assert jobs(worker) == []


def test_music_none_clears_the_bed_and_the_timeline_has_no_music(demo: Path, worker: Path) -> None:
    set_music(demo, mode="generate", prompt="lo-fi piano, instrumental", seed=2)
    assert invoke("music", "demo").exit_code == 0
    set_music(demo, mode="none")

    result = invoke("music", "demo", "--json")

    assert result.exit_code == 0, result.output
    out = json.loads(result.stdout)
    assert out["mode"] == "none"
    assert out["beats"] == []
    assert not (demo / "build" / "music.wav").exists()
    timeline_seconds(demo)
    timeline = json.loads((demo / "build" / "timeline.json").read_text())
    assert timeline["music_path"] is None


def click_track(path: Path, bpm: float, seconds: float = 12.0) -> None:
    sr = 44100
    y = np.zeros(int(seconds * sr))
    click = 0.3 * np.sin(2 * np.pi * 800 * np.arange(2000) / sr) * np.exp(-np.arange(2000) / 250)
    for beat in np.arange(0.25, seconds - 0.1, 60 / bpm):
        y[int(beat * sr) : int(beat * sr) + 2000] += click
    sf.write(path, y.astype(np.float32), sr)


LIBRARY: list[dict[str, object]] = [
    {
        "file": "calm.wav",
        "title": "Calm",
        "mood": ["calm", "warm"],
        "bpm": 90,
        "licence": "CC0",
        "source_url": "https://example.com/calm",
    },
    {
        "file": "bright.wav",
        "title": "Bright",
        "mood": ["confident", "warm"],
        "bpm": 120,
        "licence": "CC BY 4.0",
        "attribution": "Bright by Example Artist (CC BY 4.0)",
    },
    {
        "file": "near.wav",
        "title": "Near",
        "mood": ["confident", "warm"],
        "bpm": 104,
        "licence": "CC BY 4.0",
        "attribution": "Near by Other Artist (CC BY 4.0)",
    },
    {
        "file": "stolen.wav",
        "title": "Stolen",
        "mood": ["confident", "warm", "optimistic"],
        "bpm": 104,
    },
]


@pytest.fixture
def library(demo: Path) -> Path:
    music = demo.parents[1] / "library" / "music"
    for entry in LIBRARY:
        click_track(music / str(entry["file"]), float(str(entry["bpm"])))
    (music / "tags.json").write_text(json.dumps(LIBRARY), encoding="utf-8")
    return music


def test_library_picks_the_licensed_track_by_mood_then_bpm(demo: Path, library: Path) -> None:
    set_music(demo, mode="library", prompt="confident, warm, optimistic synths", bpm=100)

    first = invoke("music", "demo", "--json")
    (demo / "build" / "music.json").unlink()
    second = invoke("music", "demo", "--json")

    assert first.exit_code == 0, first.output
    out = json.loads(first.stdout)
    assert out["track"] == "near.wav"
    assert json.loads(second.stdout)["track"] == "near.wav"
    assert out["licence"] == "CC BY 4.0"
    assert any("without a licence" in w for w in out["warnings"])
    assert out["beats"]
    credits = demo / "final" / "demo_credits.txt"
    assert out["credits"] == str(credits)
    assert "Near by Other Artist (CC BY 4.0)" in credits.read_text(encoding="utf-8")
    assert sf.info(str(demo / "build" / "music.wav")).samplerate == 48000


def test_library_refuses_a_named_track_without_a_licence(demo: Path, library: Path) -> None:
    set_music(demo, mode="library", track="stolen.wav")

    result = invoke("music", "demo", "--json")

    assert result.exit_code == 1
    assert "licence" in json.loads(result.stdout)["error"]
    assert not (demo / "build" / "music.wav").exists()


def test_library_mode_without_tags_json_explains_what_to_add(demo: Path) -> None:
    set_music(demo, mode="library")

    result = invoke("music", "demo", "--json")

    assert result.exit_code == 1
    assert "tags.json" in json.loads(result.stdout)["error"]


# A 60 Hz bass with a 2.5 kHz line and an 8 kHz shimmer, the top about 15 dB under the bass.
# Its RMS stays under the stand-in voice detector's 0.1.
BASS_HEAVY = (
    "0.12 * np.sin(2 * np.pi * 60 * t) + 0.02 * np.sin(2 * np.pi * 2500 * t)"
    " + 0.01 * np.sin(2 * np.pi * 8000 * t)"
)


def bass_over_top_db(samples: np.ndarray, rate: int) -> float:
    """Energy under 150 Hz minus energy over 1 kHz, in dB, from one FFT of the mono mix."""
    mono = samples.mean(axis=1) if samples.ndim == 2 else samples
    power = np.abs(np.fft.rfft(mono * np.hanning(len(mono)))) ** 2
    freqs = np.fft.rfftfreq(len(mono), 1 / rate)
    return float(10 * np.log10(power[freqs < 150].sum() / power[freqs >= 1000].sum()))


def test_a_generated_bass_heavy_bed_is_shaped_for_small_speakers(demo: Path, worker: Path) -> None:
    (worker / "BASS_HEAVY").write_text(BASS_HEAVY)
    set_music(demo, mode="generate", prompt="deep house, instrumental", bpm=120, seed=1)
    t = np.arange(48000 * 4) / 48000
    raw = eval(BASS_HEAVY, {"np": np, "t": t})
    assert bass_over_top_db(raw, 48000) > 10

    result = invoke("music", "demo")

    assert result.exit_code == 0, result.output
    shaped, rate = sf.read(str(demo / "build" / "music.wav"))
    middle = shaped[rate * 2 : rate * 6]
    assert bass_over_top_db(middle, rate) <= 10
    assert np.abs(shaped).max() <= 1.0


def test_a_library_track_is_left_as_licensed(demo: Path, library: Path) -> None:
    set_music(demo, mode="library", track="bright.wav")

    assert invoke("music", "demo").exit_code == 0

    source, source_rate = sf.read(str(library / "bright.wav"))
    bed, rate = sf.read(str(demo / "build" / "music.wav"))
    assert bass_over_top_db(bed[: rate * 10], rate) == pytest.approx(
        bass_over_top_db(source[: source_rate * 10], source_rate), abs=0.5
    )
