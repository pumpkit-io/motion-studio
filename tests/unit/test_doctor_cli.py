import json
from pathlib import Path
from typing import Any

import pytest
from conftest import FakeTools
from typer.testing import CliRunner

from reelcut.asr import DEFAULT_MODELS, default_backend
from reelcut.asr.vad import SILERO_VERSION
from reelcut.cli import app

runner = CliRunner()

FILTERS = [
    "tonemap",
    "loudnorm",
    "sidechaincompress",
    "ebur128",
    "blackdetect",
    "freezedetect",
    "arnndn",
    "colorspace",
]


def fake_ffmpeg(tools: FakeTools, filters: list[str]) -> None:
    listing = "\n".join(f" TS {name:<16} A->A       test" for name in filters)
    tools.add(
        "ffmpeg",
        f"""
        import sys
        args = sys.argv[1:]
        if "-version" in args:
            print("ffmpeg version 9.0.1 Copyright (c) 2000-2026")
        elif "-filters" in args:
            print({listing!r})
        elif "-h" in args:
            print("-fps_mode[:<stream_spec>]  set framerate mode")
        """,
    )
    tools.add("ffprobe", 'print("ffprobe version 9.0.1")\n')


def fake_node(tools: FakeTools, version: str = "v24.8.0") -> None:
    tools.add("node", f'print("{version}")\n')
    tools.add("npm", 'print("11.6.0")\n')


def doctor_json() -> tuple[int, dict[str, Any]]:
    result = runner.invoke(app, ["doctor", "--json"])
    return result.exit_code, json.loads(result.output)


def check(payload: dict[str, Any], name: str) -> dict[str, Any]:
    return next(c for c in payload["checks"] if c["name"] == name)


def test_doctor_passes_with_every_required_tool(fake_tools: FakeTools) -> None:
    fake_ffmpeg(fake_tools, FILTERS)
    fake_node(fake_tools)
    code, payload = doctor_json()
    assert code == 0, payload
    assert payload["ok"] is True
    assert payload["ffmpeg"]["version"] == "9.0.1"
    assert all(payload["ffmpeg"]["filters"][name] for name in FILTERS)
    assert payload["ffmpeg"]["filters"]["zscale"] is False
    assert check(payload, "node")["status"] == "ok"
    assert payload["disk"]["free_gb"] > 0
    assert payload["ram_gb"] > 0


def test_doctor_exits_2_when_a_required_filter_is_missing(fake_tools: FakeTools) -> None:
    fake_ffmpeg(fake_tools, [f for f in FILTERS if f != "loudnorm"])
    fake_node(fake_tools)
    code, payload = doctor_json()
    assert code == 2
    assert payload["ok"] is False
    filters = check(payload, "ffmpeg filters")
    assert filters["status"] == "missing"
    assert "loudnorm" in filters["detail"]


def test_doctor_exits_2_without_ffmpeg_or_node(fake_tools: FakeTools) -> None:
    code, payload = doctor_json()
    assert code == 2
    assert check(payload, "ffmpeg")["status"] == "missing"
    assert check(payload, "node")["status"] == "missing"
    assert check(payload, "ffmpeg")["fix"]


def test_doctor_rejects_an_old_node(fake_tools: FakeTools) -> None:
    fake_ffmpeg(fake_tools, FILTERS)
    fake_node(fake_tools, "v18.19.0")
    code, payload = doctor_json()
    assert code == 2
    assert check(payload, "node")["status"] == "missing"


def test_doctor_warns_but_passes_on_low_disk(
    fake_tools: FakeTools, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_ffmpeg(fake_tools, FILTERS)
    fake_node(fake_tools)
    monkeypatch.setenv("REELCUT_MIN_FREE_GB", "1000000000")
    code, payload = doctor_json()
    assert code == 0
    assert check(payload, "disk")["status"] == "warn"


def test_doctor_human_output_is_short(fake_tools: FakeTools) -> None:
    fake_ffmpeg(fake_tools, FILTERS)
    fake_node(fake_tools)
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert len(result.output.splitlines()) <= 30
    assert "ffmpeg" in result.output


def test_doctor_warns_when_deepfilternet_is_missing(fake_tools: FakeTools) -> None:
    fake_ffmpeg(fake_tools, FILTERS)
    fake_node(fake_tools)
    code, payload = doctor_json()
    assert code == 0
    deep_filter = check(payload, "deepfilternet")
    assert deep_filter["status"] == "warn"
    assert "arnndn" in deep_filter["detail"]


def test_doctor_finds_deepfilternet_in_the_cache(
    fake_tools: FakeTools, isolated_cache: Path
) -> None:
    fake_ffmpeg(fake_tools, FILTERS)
    fake_node(fake_tools)
    binary = isolated_cache / "bin" / "deep-filter"
    binary.parent.mkdir(parents=True)
    binary.write_text("", encoding="utf-8")
    _, payload = doctor_json()
    assert check(payload, "deepfilternet")["status"] == "ok"
    assert str(binary) in check(payload, "deepfilternet")["detail"]


def test_doctor_warns_until_setup_has_downloaded_the_speech_models(fake_tools: FakeTools) -> None:
    fake_ffmpeg(fake_tools, FILTERS)
    fake_node(fake_tools)
    code, payload = doctor_json()
    assert code == 0
    for name in ("vad model", "asr model"):
        assert check(payload, name)["status"] == "warn"
        assert "setup" in check(payload, name)["fix"]


def test_doctor_finds_the_speech_models_in_the_cache(
    fake_tools: FakeTools, isolated_cache: Path
) -> None:
    fake_ffmpeg(fake_tools, FILTERS)
    fake_node(fake_tools)
    vad = isolated_cache / "models" / f"silero_vad-{SILERO_VERSION}.onnx"
    vad.parent.mkdir(parents=True)
    vad.write_bytes(b"onnx")
    ref = DEFAULT_MODELS[default_backend()]
    repo_dir = "models--" + ref.repo.replace("/", "--")
    snapshot = isolated_cache / "models" / "huggingface" / repo_dir / "snapshots" / ref.revision
    snapshot.mkdir(parents=True)
    (snapshot / "config.json").write_text("{}", encoding="utf-8")
    _, payload = doctor_json()
    assert check(payload, "vad model")["status"] == "ok"
    assert check(payload, "asr model")["status"] == "ok"
    assert str(snapshot) in check(payload, "asr model")["detail"]


def test_doctor_warns_until_setup_has_downloaded_the_face_models(
    fake_tools: FakeTools, isolated_cache: Path
) -> None:
    fake_ffmpeg(fake_tools, FILTERS)
    fake_node(fake_tools)
    code, payload = doctor_json()
    assert code == 0
    assert check(payload, "face model")["status"] == "warn"
    assert "setup" in check(payload, "face model")["fix"]

    models = isolated_cache / "models"
    models.mkdir(parents=True)
    (models / "face_detection_yunet_2023mar.onnx").write_bytes(b"onnx")
    _, payload = doctor_json()
    assert check(payload, "face model")["status"] == "warn"
    assert "YuNet fallback only" in check(payload, "face model")["detail"]

    (models / "blaze_face_full_range-float16-1.tflite").write_bytes(b"tflite")
    _, payload = doctor_json()
    assert check(payload, "face model")["status"] == "ok"


def test_doctor_reports_the_acestep_env_and_its_weights_licence_once_setup_finished(
    fake_tools: FakeTools, isolated_cache: Path
) -> None:
    fake_ffmpeg(fake_tools, FILTERS)
    fake_node(fake_tools)
    env = isolated_cache / "envs" / "ace-step"
    (env / "src").mkdir(parents=True)
    _, half_done = doctor_json()
    (env / "install.json").write_text(
        json.dumps(
            {
                "source": "ace-step/ACE-Step-1.5@abc",
                "weights": "ACE-Step/Ace-Step1.5@def",
                "dit": "acestep-v15-turbo",
                "licence": "mit",
                "licence_source": "README.md front matter",
            }
        ),
        encoding="utf-8",
    )
    _, done = doctor_json()
    assert check(half_done, "ace-step env")["status"] == "warn"
    assert "setup --music" in check(half_done, "ace-step env")["fix"]
    assert check(done, "ace-step env")["status"] == "ok"
    assert "licence mit" in check(done, "ace-step env")["detail"]


def fake_setup(monkeypatch: pytest.MonkeyPatch, cache: Path) -> list[dict[str, Any]]:
    """Stand in for `setup`'s downloads: it lays down the DeepFilterNet binary and logs the call."""
    from reelcut.setup import Item, SetupReport

    calls: list[dict[str, Any]] = []

    def run_setup(**kwargs: Any) -> SetupReport:
        calls.append(kwargs)
        binary = cache / "bin" / "deep-filter"
        binary.parent.mkdir(parents=True, exist_ok=True)
        binary.write_text("", encoding="utf-8")
        return SetupReport([Item("deepfilternet", "installed", str(binary))])

    monkeypatch.setattr("reelcut.doctor.run_setup", run_setup)
    return calls


def test_doctor_fix_runs_the_setup_downloads_then_checks_again(
    fake_tools: FakeTools, isolated_cache: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_ffmpeg(fake_tools, FILTERS)
    fake_node(fake_tools)
    calls = fake_setup(monkeypatch, isolated_cache)

    result = runner.invoke(app, ["doctor", "--fix", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert [c.get("music", False) for c in calls] == [False]
    assert check(payload, "deepfilternet")["status"] == "ok"
    assert payload["fixed"] == [
        {
            "name": "deepfilternet",
            "status": "installed",
            "path": str(isolated_cache / "bin" / "deep-filter"),
            "licence": None,
        }
    ]


def test_doctor_fix_does_nothing_when_setup_has_nothing_to_add(
    fake_tools: FakeTools, isolated_cache: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_ffmpeg(fake_tools, FILTERS)
    fake_node(fake_tools)
    calls = fake_setup(monkeypatch, isolated_cache)
    monkeypatch.setattr("reelcut.doctor.SETUP_FIXES", frozenset())

    result = runner.invoke(app, ["doctor", "--fix"])

    assert result.exit_code == 0, result.output
    assert calls == []
    assert "nothing to install" in result.output


def test_doctor_fix_leaves_system_tools_to_the_user(
    fake_tools: FakeTools, isolated_cache: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_ffmpeg(fake_tools, FILTERS)
    fake_setup(monkeypatch, isolated_cache)

    result = runner.invoke(app, ["doctor", "--fix", "--json"])

    assert result.exit_code == 2
    node = check(json.loads(result.output), "node")
    assert node["status"] == "missing"
    assert "brew install node" in node["fix"]
