"""`reelcut ingest` on small generated media, measured with ffprobe."""

import json
import shutil
import subprocess
import sys
import tomllib
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest
from PIL import Image
from typer.testing import CliRunner

from reelcut.cli import app
from reelcut.media.ffmpeg import ffmpeg_caps, run_ffmpeg, run_ffprobe

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def _has_encoder(name: str) -> bool:
    if shutil.which("ffmpeg") is None:
        return False
    listing = subprocess.run(
        ["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True
    )
    return name in listing.stdout


needs_x265 = pytest.mark.skipif(not _has_encoder("libx265"), reason="ffmpeg without libx265")

TINY = Path(__file__).resolve().parents[1] / "fixtures" / "tiny.mp4"
FPS = 30

runner = CliRunner()


def invoke(*args: str | Path):
    return runner.invoke(app, [str(a) for a in args])


def ingest(slug: str = "demo") -> dict[str, Any]:
    result = invoke("ingest", slug, "--json")
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


def streams(path: Path) -> list[dict[str, Any]]:
    out = run_ffprobe(["-v", "error", "-show_streams", "-show_format", "-of", "json", path])
    data = json.loads(out)
    return [*data["streams"], {"codec_type": "format", **data["format"]}]


def stream(path: Path, kind: str) -> dict[str, Any]:
    return next(s for s in streams(path) if s["codec_type"] == kind)


def clips(project: Path) -> dict[str, dict[str, Any]]:
    return tomllib.loads((project / "project.toml").read_text(encoding="utf-8"))["clips"]


@pytest.fixture(autouse=True)
def no_disk_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    # CI runners have less free disk than the 20 GB default.
    monkeypatch.setenv("REELCUT_MIN_FREE_GB", "0")


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    ws = tmp_path / "reels è"
    assert invoke("init", ws).exit_code == 0
    monkeypatch.chdir(ws)
    return ws


def new_project(workspace: Path, *sources: Path, slug: str = "demo") -> Path:
    result = invoke("new", slug, "--from", *sources)
    assert result.exit_code == 0, result.output
    return workspace / "projects" / slug


@pytest.fixture
def take(tmp_path: Path) -> Path:
    clip = tmp_path / "src" / "prova clip è.mov"
    clip.parent.mkdir()
    shutil.copyfile(TINY, clip)
    return clip


def test_a_take_becomes_a_cfr_mezzanine_and_clean_audio(workspace: Path, take: Path) -> None:
    project = new_project(workspace, take)
    report = ingest()

    assert clips(project) == {
        "c1": {"source": "raw/prova clip è.mov", "role": "aroll", "auto_role": "aroll"}
    }
    mezzanine = project / "media" / "c1.mp4"
    assert str(mezzanine) in json.dumps(report, ensure_ascii=False)
    video = stream(mezzanine, "video")
    assert Fraction(video["avg_frame_rate"]) == FPS
    assert Fraction(video["r_frame_rate"]) == FPS
    assert video["pix_fmt"] == "yuv420p"
    assert abs(float(video["duration"]) - 2.0) <= 1 / FPS
    for name, rate in (("c1.wav", 48_000), ("c1_16k.wav", 16_000)):
        audio = stream(project / "media" / name, "audio")
        assert int(audio["sample_rate"]) == rate
        assert audio["channels"] == 1
        assert abs(float(audio["duration"]) - 2.0) <= 1 / FPS


def make_video(
    path: Path, *, seconds: float = 1.0, audio: str | None = "sine", **extra: str
) -> Path:
    args: list[str | Path] = ["-y", "-loglevel", "error"]
    args += ["-f", "lavfi", "-i", f"testsrc2=s=320x180:r=25:d={seconds}"]
    if audio == "sine":
        args += ["-f", "lavfi", "-i", f"sine=f=300:sample_rate=48000:d={seconds}"]
    elif audio == "quiet":
        args += ["-f", "lavfi", "-i", f"anoisesrc=c=pink:a=0.002:r=48000:d={seconds}"]
    for key, value in extra.items():
        args += [f"-{key}", value]
    args += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-shortest", path]
    run_ffmpeg(args)
    return path


def test_rerunning_with_unchanged_inputs_is_a_no_op(workspace: Path, take: Path) -> None:
    project = new_project(workspace, take)
    ingest()
    media = project / "media"
    before = {p.name: p.stat().st_mtime_ns for p in media.iterdir()}
    toml_before = (project / "project.toml").stat().st_mtime_ns

    report = ingest()

    assert report["noop"] is True
    assert [c["status"] for c in report["clips"]] == ["unchanged"]
    assert {p.name: p.stat().st_mtime_ns for p in media.iterdir()} == before
    assert (project / "project.toml").stat().st_mtime_ns == toml_before


def test_a_new_file_gets_the_next_id_and_existing_ids_stay(workspace: Path, take: Path) -> None:
    project = new_project(workspace, take)
    ingest()
    mezzanine = project / "media" / "c1.mp4"
    first = mezzanine.stat().st_mtime_ns
    # Sorts before the first take, so a renumbering ingest would hand it c1.
    shutil.copyfile(TINY, project / "raw" / "a second take.mp4")

    report = ingest()

    assert clips(project)["c1"]["source"] == "raw/prova clip è.mov"
    assert clips(project)["c2"]["source"] == "raw/a second take.mp4"
    statuses = {c["id"]: c["status"] for c in report["clips"]}
    assert statuses == {"c1": "unchanged", "c2": "ingested"}
    assert mezzanine.stat().st_mtime_ns == first


def test_quiet_and_silent_videos_are_broll_and_images_are_images(
    workspace: Path, tmp_path: Path
) -> None:
    sources = tmp_path / "src"
    sources.mkdir()
    make_video(sources / "city.mp4", audio="quiet")
    make_video(sources / "sky.mov", audio=None)
    Image.new("RGB", (5000, 2500), "orange").save(sources / "logo card.jpg")
    project = new_project(workspace, sources)

    report = ingest()

    assert {k: v["role"] for k, v in clips(project).items()} == {
        "b1": "broll",
        "b2": "broll",
        "i1": "image",
    }
    by_id = {c["id"]: c for c in report["clips"]}
    assert by_id["b2"]["audio"] is None
    image = Path(by_id["i1"]["mezzanine"])
    assert image.name == "i1.jpg"
    with Image.open(image) as normalised:
        assert normalised.size == (4096, 2048)


def test_a_role_override_survives_reingest(workspace: Path, take: Path) -> None:
    project = new_project(workspace, take)
    ingest()
    toml_path = project / "project.toml"
    toml_path.write_text(
        toml_path.read_text(encoding="utf-8").replace('role = "aroll"', 'role = "broll"', 1),
        encoding="utf-8",
    )
    shutil.copyfile(TINY, project / "raw" / "later.mp4")

    report = ingest()

    assert clips(project)["c1"] == {
        "source": "raw/prova clip è.mov",
        "role": "broll",
        "auto_role": "aroll",
    }
    assert {c["id"]: c["role"] for c in report["clips"]} == {"c1": "broll", "c2": "aroll"}


def test_an_invalid_role_is_a_user_error(workspace: Path, take: Path) -> None:
    project = new_project(workspace, take)
    ingest()
    toml_path = project / "project.toml"
    toml_path.write_text(
        toml_path.read_text(encoding="utf-8").replace('role = "aroll"', 'role = "talking"', 1),
        encoding="utf-8",
    )
    shutil.copyfile(TINY, project / "raw" / "x.mp4")

    result = invoke("ingest", "demo", "--json")

    assert result.exit_code == 1
    assert "talking" in json.loads(result.stdout)["error"]


def test_rotation_is_applied(workspace: Path, tmp_path: Path) -> None:
    upright = make_video(tmp_path / "upright.mp4")
    rotated = tmp_path / "rotated.mov"
    run_ffmpeg(
        [
            "-y",
            "-loglevel",
            "error",
            "-display_rotation",
            "90",
            "-i",
            upright,
            "-c",
            "copy",
            rotated,
        ]
    )
    project = new_project(workspace, rotated)

    ingest()

    video = stream(project / "media" / "c1.mp4", "video")
    assert (video["width"], video["height"]) == (180, 320)
    assert not any("rotation" in side for side in video.get("side_data_list", []))


def test_unreadable_files_are_skipped_with_a_warning(workspace: Path, take: Path) -> None:
    project = new_project(workspace, take)
    (project / "raw" / "notes.txt").write_text("not media", encoding="utf-8")

    report = ingest()

    assert list(clips(project)) == ["c1"]
    assert any("notes.txt" in w for w in report["warnings"])
    state = json.loads((project / "state.json").read_text(encoding="utf-8"))
    assert any("notes.txt" in w for w in state["stages"]["ingest"]["warnings"])


@pytest.mark.mac
def test_a_heic_photo_becomes_a_png_image(workspace: Path, tmp_path: Path) -> None:
    sources = tmp_path / "src"
    sources.mkdir()
    Image.new("RGB", (640, 480), "teal").save(sources / "card.png")
    subprocess.run(
        ["sips", "-s", "format", "heic", sources / "card.png", "--out", sources / "IMG 1.heic"],
        check=True,
        capture_output=True,
    )
    (sources / "card.png").unlink()
    new_project(workspace, sources)

    report = ingest()

    [image] = report["clips"]
    assert (image["id"], image["kind"], image["width"], image["height"]) == (
        "i1",
        "image",
        640,
        480,
    )
    with Image.open(image["mezzanine"]) as normalised:
        assert (normalised.format, normalised.size) == ("PNG", (640, 480))


@pytest.mark.mac
def test_a_heic_photo_keeps_its_orientation(workspace: Path, tmp_path: Path) -> None:
    sources = tmp_path / "src"
    sources.mkdir()
    shot = Image.new("RGB", (400, 200), "red")
    exif = shot.getexif()
    exif[0x0112] = 6  # rotate 90 degrees clockwise to display
    shot.save(sources / "shot.jpg", exif=exif)
    subprocess.run(
        ["sips", "-s", "format", "heic", sources / "shot.jpg", "--out", sources / "shot.heic"],
        check=True,
        capture_output=True,
    )
    (sources / "shot.jpg").unlink()
    new_project(workspace, sources)

    [image] = ingest()["clips"]

    assert (image["width"], image["height"]) == (200, 400)


def test_a_heic_photo_is_skipped_with_a_warning_when_nothing_can_decode_it(
    workspace: Path, tmp_path: Path, take: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("reelcut.ingest.heif_decoder", lambda: None)
    project = new_project(workspace, take)
    (project / "raw" / "IMG_0001.HEIC").write_bytes(b"not decoded here")

    report = ingest()

    assert list(clips(project)) == ["c1"]
    [warning] = [w for w in report["warnings"] if "IMG_0001.HEIC" in w]
    assert "heif-convert" in warning
    state = json.loads((project / "state.json").read_text(encoding="utf-8"))
    assert warning in state["stages"]["ingest"]["warnings"]


def test_an_empty_raw_folder_is_a_user_error_naming_the_folder(
    workspace: Path, tmp_path: Path
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    project = new_project(workspace, empty)

    result = invoke("ingest", "demo", "--json")

    assert result.exit_code == 1
    error = json.loads(result.stdout)
    assert str(project / "raw") in error["error"]
    assert "ingest demo" in error["hint"]


def test_ingest_refuses_to_start_when_disk_is_low(
    workspace: Path, take: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    new_project(workspace, take)
    monkeypatch.setenv("REELCUT_MIN_FREE_GB", "1000000")

    result = invoke("ingest", "demo", "--json")

    assert result.exit_code == 2
    assert "free" in json.loads(result.stdout)["error"]


def make_hlg(path: Path) -> Path:
    """A 10-bit HEVC clip tagged BT.2020 HLG, as an iPhone records it."""
    tags = "color_primaries=bt2020:color_trc=arib-std-b67:colorspace=bt2020nc"
    x265 = "log-level=error:colorprim=bt2020:transfer=arib-std-b67:colormatrix=bt2020nc"
    run_ffmpeg(
        [
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=320x180:r=30:d=1",
            "-f",
            "lavfi",
            "-i",
            "sine=f=300:sample_rate=48000:d=1",
            "-vf",
            f"format=yuv420p10le,setparams={tags}",
            "-c:v",
            "libx265",
            "-x265-params",
            x265,
            "-tag:v",
            "hvc1",
            "-pix_fmt",
            "yuv420p10le",
            "-shortest",
            path,
        ]
    )
    assert stream(path, "video")["color_transfer"] == "arib-std-b67"
    return path


def mean_rgb(path: Path) -> list[float]:
    frame = path.with_suffix(".rgb")
    run_ffmpeg(
        [
            "-y",
            "-loglevel",
            "error",
            "-i",
            path,
            "-frames:v",
            "1",
            "-vf",
            "scale=32:18",
            "-pix_fmt",
            "rgb24",
            "-f",
            "rawvideo",
            frame,
        ]
    )
    data = frame.read_bytes()
    return [sum(data[i::3]) / (len(data) / 3) for i in range(3)]


@needs_x265
def test_an_hlg_clip_is_tone_mapped_and_tagged_bt709(workspace: Path, tmp_path: Path) -> None:
    project = new_project(workspace, make_hlg(tmp_path / "hlg clip.mov"))

    report = ingest()

    video = stream(project / "media" / "c1.mp4", "video")
    assert video["color_transfer"] == "bt709"
    assert video["color_primaries"] == "bt709"
    assert video["color_space"] == "bt709"
    clip = report["clips"][0]
    assert clip["hdr"] == "hlg"
    caps = ffmpeg_caps()
    if sys.platform == "darwin" and caps.has_filter("scale_vt"):
        assert clip["tonemap"] == "scale_vt"
    elif caps.has_filter("zscale"):
        assert clip["tonemap"] == "zscale"
    else:
        assert clip["tonemap"] == "colorspace"
    assert not any("tone-map failed" in w for w in report["warnings"])
    assert mean_rgb(project / "media" / "c1.mp4") != mean_rgb(tmp_path / "hlg clip.mov")


@needs_x265
def test_the_colorspace_fallback_warns_and_is_recorded(
    workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REELCUT_TONEMAP", "colorspace")
    project = new_project(workspace, make_hlg(tmp_path / "hlg.mov"))

    result = invoke("ingest", "demo")

    assert result.exit_code == 0, result.output
    warnings = [line for line in result.stderr.splitlines() if "colorspace" in line]
    assert len(warnings) == 1 and warnings[0].startswith("warning: c1:")
    assert stream(project / "media" / "c1.mp4", "video")["color_transfer"] == "bt709"
    state = json.loads((project / "state.json").read_text(encoding="utf-8"))
    assert any("colorspace" in w for w in state["stages"]["ingest"]["warnings"])


def test_without_deepfilternet_arnndn_cleans_the_voice_and_warns(
    workspace: Path, take: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REELCUT_DEEP_FILTER", str(workspace / "no-such-binary"))
    project = new_project(workspace, take)

    result = invoke("ingest", "demo")

    assert result.exit_code == 0, result.output
    warnings = [line for line in result.stderr.splitlines() if line.startswith("warning:")]
    assert len(warnings) == 1 and "arnndn" in warnings[0]
    manifest = json.loads((project / "media" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["clips"][0]["denoiser"] == "arnndn"
    state = json.loads((project / "state.json").read_text(encoding="utf-8"))
    assert state["stages"]["ingest"]["warnings"] == [warnings[0].removeprefix("warning: ")]
