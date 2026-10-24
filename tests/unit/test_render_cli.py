"""`reelcut render` on generated media, with a stand-in for the Remotion CLI.

The stand-in scales the assembled video to the format's size, so assemble and mix run for real
in CI; the real renderer is covered by tests/integration/test_render_fixtures.py.
"""

import json
import re
import shutil
import sys
import textwrap
from pathlib import Path
from typing import Any

import pytest
from edl_fixtures import clip
from test_plan_cli import write_analyses
from typer.testing import CliRunner

from reelcut.cli import app
from reelcut.media.ffmpeg import run_ffmpeg, run_ffprobe

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")

FPS = 30
C1 = clip(
    "c1",
    "Welcome back everyone to the channel today.",
    "The reason I built this tool is simple and clear.",
    "See you soon in the next one.",
)

runner = CliRunner()

FAKE_REMOTION = """
    import json, subprocess, sys
    from pathlib import Path

    args = sys.argv[1:]
    opts = dict(a[2:].split("=", 1) for a in args if a.startswith("--") and "=" in a)
    command, out = args[0], Path(args[3])
    props = json.loads(Path(opts["props"]).read_text())
    log = Path(__file__).resolve().parents[2] / "calls.jsonl"
    with log.open("a") as f:
        f.write(json.dumps({"argv": args, "props": props, "cwd": str(Path.cwd())}) + "\\n")
    spec = next(f for f in props["timeline"]["formats"] if f["name"] == props["format"])
    scale = float(opts.get("scale", "1"))
    w, h = round(spec["width"] * scale), round(spec["height"] * scale)
    video = Path(opts["public-dir"]) / props["video"]
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vf", f"scale={w}:{h},setsar=1",
         "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(out)],
        check=True,
    )
"""


def invoke(*args: str | Path):
    return runner.invoke(app, [str(a) for a in args])


def render(*args: str) -> dict[str, Any]:
    result = invoke("render", "demo", *args, "--json")
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


def video_stream(path: Path) -> dict[str, Any]:
    out = run_ffprobe(["-v", "error", "-count_frames", "-show_streams", "-of", "json", path])
    return next(s for s in json.loads(out)["streams"] if s["codec_type"] == "video")


def ebur128(path: Path) -> tuple[float, float]:
    """Integrated loudness (LUFS) and true peak (dBTP) of `path`'s audio."""
    lines = run_ffmpeg(["-i", path, "-map", "0:a", "-af", "ebur128=peak=true", "-f", "null", "-"])
    summary = "\n".join(lines[-15:])
    integrated = re.search(r"I:\s+(-?[\d.]+) LUFS", summary)
    peak = re.search(r"Peak:\s+(-?[\d.]+|-inf) dBFS", summary)
    assert integrated and peak, summary
    return float(integrated.group(1)), float(peak.group(1))


@pytest.fixture(autouse=True)
def no_disk_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    # CI runners have less free disk than the 20 GB default.
    monkeypatch.setenv("REELCUT_MIN_FREE_GB", "0")


@pytest.fixture
def fake_renderer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    renderer = tmp_path / "renderer"
    bin_dir = renderer / "node_modules" / ".bin"
    bin_dir.mkdir(parents=True)
    script = bin_dir / "remotion"
    script.write_text(f"#!{sys.executable}\n{textwrap.dedent(FAKE_REMOTION)}", encoding="utf-8")
    script.chmod(0o755)
    monkeypatch.setenv("REELCUT_RENDERER_DIR", str(renderer))
    return renderer


def calls(renderer: Path) -> list[dict[str, Any]]:
    log = renderer / "calls.jsonl"
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


def write_edl(project: Path, **extra: Any) -> None:
    edl = {
        "segments": [
            {"id": "intro", "from": "c1.s0", "to": "c1.s0"},
            {"id": "body", "from": "c1.s2", "to": "c1.s2"},
            {"id": "end", "from": "c1.s1", "to": "c1.s1"},
        ],
        "formats": ["9x16", "16x9"],
        "music": {"mode": "none"},
        **extra,
    }
    (project / "edl.json").write_text(json.dumps(edl), encoding="utf-8")


@pytest.fixture
def demo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_renderer: Path) -> Path:
    ws = tmp_path / "reels è"
    assert invoke("init", ws).exit_code == 0
    take = tmp_path / "take.mov"
    take.write_bytes(b"replaced by the generated mezzanine below")
    monkeypatch.chdir(ws)
    assert invoke("new", "demo", "--from", take).exit_code == 0
    project = ws / "projects" / "demo"
    duration = C1.clip.duration_s
    media = project / "media"
    run_ffmpeg(
        [
            "-f", "lavfi", "-i", f"testsrc2=size=360x640:rate={FPS}", "-t", str(duration),
            "-c:v", "libx264", "-preset", "ultrafast", "-g", str(FPS), "-pix_fmt", "yuv420p",
            "-an", media / "c1.mp4",
        ]
    )  # fmt: skip
    run_ffmpeg(
        [
            "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=48000", "-t", str(duration),
            "-ac", "1", "-c:a", "pcm_s16le", media / "c1.wav",
        ]
    )  # fmt: skip
    manifest = {
        "schema_version": 1,
        "clips": [
            {
                "id": "c1",
                "role": "aroll",
                "source": "raw/take.mov",
                "kind": "video",
                "mezzanine": "media/c1.mp4",
                "audio": "media/c1.wav",
                "audio_16k": None,
                "width": 360,
                "height": 640,
                "fps": FPS,
                "duration_s": duration,
            }
        ],
    }
    (media / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    write_analyses(project, [C1])
    write_edl(project)
    return project


def timeline(project: Path) -> dict[str, Any]:
    return json.loads((project / "build" / "timeline.json").read_text(encoding="utf-8"))


def test_preview_writes_a_half_size_file_per_format_lasting_the_timeline(demo: Path) -> None:
    out = render("--preview")

    frames = timeline(demo)["duration_frames"]
    sizes = {"9x16": (540, 960), "16x9": (960, 540)}
    assert [o["format"] for o in out["outputs"]] == ["9x16", "16x9"]
    for item in out["outputs"]:
        path = Path(item["path"])
        assert path == demo / "preview" / f"{item['format']}.mp4"
        video = video_stream(path)
        assert (video["width"], video["height"]) == sizes[item["format"]]
        assert abs(int(video["nb_read_frames"]) - frames) <= 1


def test_preview_passes_half_scale_and_the_concurrency_to_remotion(
    demo: Path, fake_renderer: Path
) -> None:
    render("--preview", "--format", "16x9", "--concurrency", "2")

    [call] = calls(fake_renderer)
    assert call["argv"][:3] == ["render", "src/index.ts", "Reel"]
    assert "--scale=0.5" in call["argv"]
    assert "--concurrency=2" in call["argv"]
    assert call["cwd"] == str(fake_renderer)
    assert call["props"]["format"] == "16x9"
    assert call["props"]["source"] == {"width": 360, "height": 640}
    assert call["props"]["video"] == "assembled.mp4"


def test_final_with_music_none_is_mastered_to_minus_14_lufs(demo: Path) -> None:
    out = render("--final", "--format", "9x16")

    [item] = out["outputs"]
    path = Path(item["path"])
    assert path == demo / "final" / "demo_9x16.mp4"
    assert (item["width"], item["height"]) == (1080, 1920)
    integrated, peak = ebur128(path)
    assert abs(integrated + 14) <= 1
    assert peak <= -1


def test_final_ducks_a_looped_music_bed_and_still_masters_loudness(demo: Path) -> None:
    write_edl(demo, music={"mode": "generate"})
    # A 2 s tone bed, shorter than the video, so the mix has to loop it.
    run_ffmpeg(
        [
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-t", "2",
            "-ac", "2", demo / "build" / "music.wav",
        ]
    )  # fmt: skip

    out = render("--final", "--format", "9x16")

    [item] = out["outputs"]
    integrated, peak = ebur128(Path(item["path"]))
    assert abs(integrated + 14) <= 1
    assert peak <= -1
    master, voice = Path(item["path"]), Path(item["voice"])
    # The looped bed still plays near the end, ducked: -20 dB of gain alone would leave it 20 dB
    # under the voice tone, and the voice stem kept for `check` has no music at all.
    assert band_level(master, 440) > -60
    assert band_level(master, 220) - band_level(master, 440) > 24
    assert band_level(voice, 440) < band_level(master, 440) - 10


def test_the_edl_music_gain_overrides_the_config_level(demo: Path) -> None:
    run_ffmpeg(
        [
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-t", "2",
            "-ac", "2", demo / "build" / "music.wav",
        ]
    )  # fmt: skip
    write_edl(demo, music={"mode": "generate", "gain_db": -20})
    loud = band_level(Path(render("--final", "--format", "9x16")["outputs"][0]["path"]), 440)
    write_edl(demo, music={"mode": "generate", "gain_db": -32})

    out = render("--final", "--format", "9x16")

    assert out["noop"] is False
    # The ducking compressor squeezes the 12 dB gain change into a smaller drop at the output.
    assert band_level(Path(out["outputs"][0]["path"]), 440) < loud - 3


def band_level(path: Path, hz: int) -> float:
    """Mean dB around `hz` from 4 s to 2 s before the end of `path`."""
    lines = run_ffmpeg(
        ["-sseof", "-4", "-t", "2", "-i", path, "-map", "0:a", "-af",
         f"bandpass=f={hz}:width_type=q:w=30,volumedetect", "-f", "null", "-"]
    )  # fmt: skip
    mean = next(line for line in lines if "mean_volume" in line)
    return float(mean.split("mean_volume:")[1].split()[0])


def test_mix_copies_the_composed_video_stream_bit_for_bit(demo: Path) -> None:
    out = render("--final", "--format", "9x16")

    final = Path(out["outputs"][0]["path"])
    composed = demo / "build" / "composed_9x16.mp4"
    assert stream_hash(final) == stream_hash(composed)


def stream_hash(path: Path) -> str:
    lines = run_ffmpeg(
        ["-v", "error", "-i", path, "-map", "0:v", "-c", "copy",
         "-f", "streamhash", "-hash", "md5", "-"]
    )  # fmt: skip
    return "\n".join(lines)


def test_the_voice_stem_is_kept_per_format_for_check(demo: Path) -> None:
    out = render("--preview")

    for item in out["outputs"]:
        voice = Path(item["voice"])
        assert voice == demo / "build" / f"voice_{item['format']}.wav"
        info = json.loads(run_ffprobe(["-v", "error", "-show_streams", "-of", "json", voice]))
        stream = info["streams"][0]
        assert (stream["codec_name"], stream["sample_rate"]) == ("pcm_s16le", "48000")
    runs = timeline(demo)["runs"]
    assert len(runs) >= 3
    assert out["cuts_s"] == [round(r["out_in"] / FPS, 3) for r in runs[1:]]


def test_a_second_render_with_nothing_changed_is_a_no_op(demo: Path, fake_renderer: Path) -> None:
    render("--preview")
    again = render("--preview")

    assert again["noop"] is True
    assert len(calls(fake_renderer)) == 2
    assert [o["format"] for o in again["outputs"]] == ["9x16", "16x9"]


def test_an_edited_edl_is_validated_and_rendered_again(demo: Path, fake_renderer: Path) -> None:
    render("--preview", "--format", "9x16")
    write_edl(demo, segments=[{"id": "intro", "from": "c1.s0", "to": "c1.s0"}])

    out = render("--preview", "--format", "9x16")

    assert out["noop"] is False
    assert out["cuts_s"] == []
    assert len(calls(fake_renderer)) == 2


def test_render_refuses_to_start_below_the_free_disk_threshold(
    demo: Path, monkeypatch: pytest.MonkeyPatch, fake_renderer: Path
) -> None:
    monkeypatch.setenv("REELCUT_MIN_FREE_GB", "1000000")

    result = invoke("render", "demo", "--preview", "--json")

    assert result.exit_code == 2
    assert "free" in json.loads(result.stdout)["error"]
    assert calls(fake_renderer) == []


def test_a_missing_music_bed_fails_with_a_hint_to_run_music(demo: Path) -> None:
    write_edl(demo, music={"mode": "generate"})

    result = invoke("render", "demo", "--preview", "--json")

    assert result.exit_code == 1
    body = json.loads(result.stdout)
    assert "music.wav" in body["error"]
    assert "music demo" in body["hint"]


def test_a_format_missing_from_the_timeline_is_a_user_error(demo: Path) -> None:
    result = invoke("render", "demo", "--preview", "--format", "4x5")

    assert result.exit_code == 1
    assert "4x5" in result.output


def test_preview_and_final_together_is_a_user_error(demo: Path) -> None:
    assert invoke("render", "demo", "--preview", "--final").exit_code == 1


def test_a_missing_renderer_fails_with_exit_2_and_points_at_setup(
    demo: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("REELCUT_RENDERER_DIR", str(tmp_path / "nowhere"))

    result = invoke("render", "demo", "--preview", "--json")

    assert result.exit_code == 2


def test_an_unknown_caption_font_falls_back_to_inter_with_a_warning(
    demo: Path, fake_renderer: Path
) -> None:
    ws = demo.parents[1]
    toml = ws / "reelcut.toml"
    toml.write_text(
        toml.read_text(encoding="utf-8").replace('font = "Inter"', 'font = "Montserrat"'),
        encoding="utf-8",
    )

    result = invoke("render", "demo", "--preview", "--format", "9x16")

    assert result.exit_code == 0, result.output
    warnings = [line for line in result.stderr.splitlines() if line.startswith("warning:")]
    assert len(warnings) == 1
    assert "Montserrat" in warnings[0] and "Inter" in warnings[0]
    state = json.loads((demo / "state.json").read_text(encoding="utf-8"))
    assert any("Montserrat" in w for w in state["stages"]["preview"]["warnings"])
    assert calls(fake_renderer)[0]["props"]["font_file"] is None


def test_brand_font_and_logo_are_linked_into_the_public_dir(
    demo: Path, fake_renderer: Path
) -> None:
    ws = demo.parents[1]
    fonts = ws / "library" / "brand" / "fonts"
    fonts.mkdir(parents=True, exist_ok=True)
    (fonts / "Montserrat-ExtraBold.ttf").write_bytes(b"font bytes")
    (ws / "library" / "brand" / "logo.png").write_bytes(b"png bytes")
    toml = ws / "reelcut.toml"
    toml.write_text(
        toml.read_text(encoding="utf-8").replace('font = "Inter"', 'font = "Montserrat"'),
        encoding="utf-8",
    )

    result = invoke("render", "demo", "--preview", "--format", "9x16")

    assert result.exit_code == 0, result.output
    assert "warning:" not in result.stderr
    props = calls(fake_renderer)[0]["props"]
    public = demo / "build" / "public"
    assert (public / props["font_file"]).read_bytes() == b"font bytes"
    assert (public / props["logo_file"]).read_bytes() == b"png bytes"
    assert props["timeline"]["captions"]["font"].isalnum()
