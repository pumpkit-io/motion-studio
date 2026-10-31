"""`motion-studio music` on a planned project with a stand-in ACE-Step worker and voice detector."""

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from edl_fixtures import clip
from music_fixtures import jobs
from typer.testing import CliRunner

from motion_studio.cli import app
from motion_studio.edl import Timeline
from motion_studio.music import acestep
from motion_studio.paths import project_paths
from motion_studio.state import mark_done

runner = CliRunner()


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

    assert "music: none (voice only)" in invoke("music", "demo").output
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


SECTIONED_BPM = 119.8
FIRST_BEAT_S = 0.3
# Bars and layers per section: intro, build, drop, ending, then two seconds of silence.
SECTIONS: list[tuple[int, set[str]]] = [
    (8, {"hat"}),
    (8, {"hat", "kick"}),
    (8, {"hat", "kick", "lead"}),
    (4, {"hat"}),
]


def sectioned_bed(path: Path, bpm: float = SECTIONED_BPM) -> None:
    """Hats, then a kick, then a lead, then hats alone; librosa alone reports 117.5 bpm for it."""
    sr = 44100
    beat = 60 / bpm
    bars = sum(n for n, _ in SECTIONS)
    y = np.zeros(int((FIRST_BEAT_S + bars * 4 * beat + 2.0) * sr))
    n = np.arange(int(0.08 * sr))
    hat = 0.08 * np.random.default_rng(1).uniform(-1, 1, len(n)) * np.exp(-n / 300)
    kick = 0.6 * np.sin(2 * np.pi * 55 * n / sr) * np.exp(-n / 2500)
    m = np.arange(int(0.9 * beat * sr))
    lead = 0.15 * np.sin(2 * np.pi * 660 * m / sr) * np.exp(-m / (0.2 * sr))

    def add(t: float, sound: np.ndarray) -> None:
        i = round(t * sr)
        y[i : i + len(sound)] += sound

    t = FIRST_BEAT_S
    for count, layers in SECTIONS:
        for b in range(count * 4):
            at = t + b * beat
            if "hat" in layers:
                add(at, hat)
                add(at + beat / 2, 0.6 * hat)
            if "kick" in layers:
                add(at, kick)
            if "lead" in layers:
                add(at, lead)
        t += count * 4 * beat
    sf.write(path, y.astype(np.float32), sr)


def test_music_json_reports_the_true_tempo_bar_grid_and_section_hits(demo: Path) -> None:
    music = demo.parents[1] / "library" / "music"
    music.mkdir(parents=True, exist_ok=True)
    sectioned_bed(music / "launch.wav")
    track = {"file": "launch.wav", "title": "Launch", "bpm": 120, "licence": "CC0"}
    (music / "tags.json").write_text(json.dumps([track]), encoding="utf-8")
    set_music(demo, mode="library", track="launch.wav")

    result = invoke("music", "demo", "--json")

    assert result.exit_code == 0, result.output
    info = json.loads((demo / "build" / "music.json").read_text(encoding="utf-8"))
    beat = 60 / SECTIONED_BPM
    assert info["detected_bpm"] == pytest.approx(SECTIONED_BPM, abs=0.5)
    assert info["beats_per_bar"] == 4
    assert float(np.median(np.diff(info["beats"]))) == pytest.approx(beat, abs=0.01)
    assert float(np.median(np.diff(info["bars"]))) == pytest.approx(4 * beat, abs=0.02)
    assert info["bars"][0] == pytest.approx(FIRST_BEAT_S, abs=beat / 2)
    hits = {h["name"]: h["time_s"] for h in info["hits"]}
    bar_s = 4 * beat
    expected = {
        "intro_end": FIRST_BEAT_S + 8 * bar_s,
        "build": FIRST_BEAT_S + 8 * bar_s,
        "drop": FIRST_BEAT_S + 16 * bar_s,
        "ending": FIRST_BEAT_S + 24 * bar_s,
    }
    assert set(hits) == set(expected)
    for name, at in expected.items():
        assert hits[name] == pytest.approx(at, abs=beat), name
    starts = [s["start_s"] for s in info["sections"]]
    assert starts[0] == 0
    assert len(starts) == 4
    loudest = max(info["sections"], key=lambda s: s["energy_db"])
    assert loudest["start_s"] == hits["drop"]
    assert [h["name"] for h in json.loads(result.stdout)["hits"]] == list(expected)


def drifting_bed(path: Path, click_bpm: float, section_s: float) -> None:
    """Clicks at `click_bpm` over sustained pads that change every `section_s`, four times."""
    sr = 44100
    t = np.arange(int((FIRST_BEAT_S + 4 * section_s + 2) * sr)) / sr
    y = np.zeros_like(t)
    for k, (low, high) in enumerate([(0.02, 0.0), (0.05, 0.02), (0.12, 0.08), (0.02, 0.0)]):
        m = (t >= FIRST_BEAT_S + k * section_s) & (t < FIRST_BEAT_S + (k + 1) * section_s)
        y[m] += (
            low * np.sin(2 * np.pi * 80 * t[m])
            + high * np.sin(2 * np.pi * 2000 * t[m])
            + 0.03 * np.sin(2 * np.pi * 440 * t[m])
        )
    n = np.arange(2000)
    click = 0.3 * np.sin(2 * np.pi * 800 * n / sr) * np.exp(-n / 250)
    for beat in np.arange(FIRST_BEAT_S, FIRST_BEAT_S + 4 * section_s, 60 / click_bpm):
        y[int(beat * sr) : int(beat * sr) + 2000] += click
    sf.write(path, y.astype(np.float32), sr)


def test_the_section_period_corrects_a_tempo_the_onsets_get_wrong(demo: Path) -> None:
    # The Pumpkit bed: sections every 16.03 s are 8 bars at 119.8 bpm, though it read as 117.5.
    music = demo.parents[1] / "library" / "music"
    music.mkdir(parents=True, exist_ok=True)
    drifting_bed(music / "drift.wav", click_bpm=117.5, section_s=16.03)
    track = {"file": "drift.wav", "title": "Drift", "licence": "CC0"}
    (music / "tags.json").write_text(json.dumps([track]), encoding="utf-8")
    set_music(demo, mode="library", track="drift.wav")

    result = invoke("music", "demo")

    assert result.exit_code == 0, result.output
    info = json.loads((demo / "build" / "music.json").read_text(encoding="utf-8"))
    assert info["tracker_bpm"] == pytest.approx(117.5, abs=0.1)
    assert info["detected_bpm"] == pytest.approx(119.8, abs=0.5)
    assert info["tempo_from"] == "sections"
    hits = {h["name"]: h["time_s"] for h in info["hits"]}
    assert hits["drop"] == pytest.approx(FIRST_BEAT_S + 2 * 16.03, abs=60 / 119.8)
    assert "corrected from 117.5" in result.output


def test_a_bed_analysed_before_the_bar_grid_is_analysed_again_without_regenerating(
    demo: Path, worker: Path
) -> None:
    set_music(demo, mode="generate", prompt="lo-fi piano, instrumental", bpm=120, seed=2)
    assert invoke("music", "demo").exit_code == 0
    path = demo / "build" / "music.json"
    old = json.loads(path.read_text(encoding="utf-8"))
    for key in ("tracker_bpm", "tempo_from", "bars", "sections", "hits"):
        del old[key]
    path.write_text(json.dumps(old), encoding="utf-8")

    result = invoke("music", "demo", "--json")

    assert result.exit_code == 0, result.output
    assert len(jobs(worker)) == 1
    info = json.loads(path.read_text(encoding="utf-8"))
    assert info["tempo_from"] == "onsets"
    assert info["bars"]


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


def write_pre_shaping_bed(project: Path, seconds: float, *, seed: int, accepted: int) -> Path:
    """A generated bed as music wrote it before shaping: unshaped wav, music.json and state."""
    length = round(seconds + 3, 3)
    wav = project / "build" / "music.wav"
    wav.parent.mkdir(parents=True, exist_ok=True)
    t = np.arange(int(48000 * length)) / 48000
    bed = eval(BASS_HEAVY, {"np": np, "t": t})
    sf.write(str(wav), np.stack([bed, bed], axis=1), 48000, subtype="PCM_16")
    attempts = [
        {"seed": s, "speech_ratio": 0.0 if s == accepted else 0.9, "accepted": s == accepted}
        for s in range(seed, accepted + 1)
    ]
    info = {
        "schema_version": 1, "mode": "generate", "path": "build/music.wav",
        "duration_s": length, "prompt": "deep house, instrumental", "seed": accepted,
        "bpm": 120, "detected_bpm": 120.0, "model": acestep.MODEL, "beats": [0.5, 1.0],
        "attempts": attempts, "elapsed_s": 12.0,
    }  # fmt: skip
    music_json = project / "build" / "music.json"
    music_json.write_text(json.dumps(info), encoding="utf-8")
    params = {
        "mode": "generate", "prompt": "deep house, instrumental", "bpm": 120, "seed": seed,
        "duration": length, "model": acestep.MODEL,
    }  # fmt: skip
    paths = project_paths(project.parents[1], project.name)
    mark_done(paths, "music", [], outputs=[wav, music_json], params=params)
    return wav


def test_a_bed_generated_before_shaping_is_shaped_without_generating_again(
    demo: Path, worker: Path
) -> None:
    set_music(demo, mode="generate", prompt="deep house, instrumental", bpm=120, seed=4)
    wav = write_pre_shaping_bed(demo, timeline_seconds(demo), seed=4, accepted=5)

    result = invoke("music", "demo", "--json")
    again = invoke("music", "demo", "--json")

    assert result.exit_code == 0, result.output
    assert jobs(worker) == []
    out = json.loads(result.stdout)
    assert out["seed"] == 5
    assert [(c["seed"], c["accepted"]) for c in out["candidates"]] == [(4, False), (5, True)]
    shaped, rate = sf.read(str(wav))
    assert bass_over_top_db(shaped[rate * 2 : rate * 6], rate) <= 10
    assert json.loads(again.stdout)["fresh"] is True
    assert jobs(worker) == []


def test_a_pre_shaping_bed_that_is_gone_is_generated_again_with_a_notice(
    demo: Path, worker: Path
) -> None:
    set_music(demo, mode="generate", prompt="deep house, instrumental", bpm=120, seed=4)
    write_pre_shaping_bed(demo, timeline_seconds(demo), seed=4, accepted=4).unlink()

    result = invoke("music", "demo")

    assert result.exit_code == 0, result.output
    assert len(jobs(worker)) == 1
    (notice,) = [line for line in result.output.splitlines() if line.startswith("warning:")]
    assert "before shaping" in notice
    state = json.loads((demo / "state.json").read_text(encoding="utf-8"))
    assert state["stages"]["music"]["warnings"] == [notice.removeprefix("warning: ")]
