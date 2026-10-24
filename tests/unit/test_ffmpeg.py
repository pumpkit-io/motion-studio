import json
import shutil
from pathlib import Path

import pytest
from conftest import FakeTools

from reelcut.errors import DependencyError
from reelcut.media.ffmpeg import (
    FFmpegError,
    ffmpeg_caps,
    filter_graph_args,
    run_ffmpeg,
    run_ffprobe,
)

real_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def test_arguments_reach_ffmpeg_as_a_list_with_spaces_and_accents_intact(
    fake_tools: FakeTools, tmp_path: Path
) -> None:
    record = tmp_path / "argv.json"
    fake_tools.add(
        "ffmpeg",
        f"""
        import json, sys
        open({str(record)!r}, "w").write(json.dumps(sys.argv[1:]))
        """,
    )
    clip = tmp_path / "prova clip è.mov"
    run_ffmpeg(["-i", clip, "-c", "copy", tmp_path / "out file.mp4"])
    argv = json.loads(record.read_text(encoding="utf-8"))
    assert str(clip) in argv
    assert str(tmp_path / "out file.mp4") in argv
    assert argv[:2] == ["-hide_banner", "-nostdin"]


def test_a_shell_string_is_refused(fake_tools: FakeTools) -> None:
    fake_tools.add("ffmpeg", "pass\n")
    with pytest.raises(TypeError):
        run_ffmpeg("-i in.mov out.mp4")  # pyright: ignore[reportArgumentType]


def test_failure_surfaces_the_last_20_stderr_lines(fake_tools: FakeTools) -> None:
    fake_tools.add(
        "ffmpeg",
        """
        import sys
        for i in range(1, 31):
            print(f"line {i}", file=sys.stderr)
        sys.exit(1)
        """,
    )
    with pytest.raises(FFmpegError) as excinfo:
        run_ffmpeg(["-i", "x.mov", "y.mp4"])
    error = excinfo.value
    assert error.returncode == 1
    assert error.stderr_tail == [f"line {i}" for i in range(11, 31)]
    assert "line 30" in str(error)
    assert "line 10\n" not in str(error)
    assert error.exit_code == 3


def test_progress_is_reported_in_seconds(fake_tools: FakeTools) -> None:
    fake_tools.add(
        "ffmpeg",
        """
        for us in (500000, 1000000, 2500000):
            print(f"out_time_us={us}")
            print("progress=continue")
        print("progress=end")
        """,
    )
    seen: list[float] = []
    run_ffmpeg(["-i", "x.mov", "y.mp4"], progress=seen.append)
    assert seen == [0.5, 1.0, 2.5]


def test_missing_ffmpeg_is_a_dependency_error(fake_tools: FakeTools) -> None:
    with pytest.raises(DependencyError, match="ffmpeg") as excinfo:
        run_ffmpeg(["-version"])
    assert excinfo.value.exit_code == 2


def test_ffprobe_returns_stdout(fake_tools: FakeTools) -> None:
    fake_tools.add("ffprobe", "print('{\"streams\": []}')\n")
    assert json.loads(run_ffprobe(["-of", "json", "x.mov"])) == {"streams": []}


OLD_FFMPEG = """
import sys
args = sys.argv[1:]
if "-version" in args:
    print("ffmpeg version 6.1.1-3ubuntu5 Copyright (c) 2000-2023")
elif "-filters" in args:
    print(" T.. = Timeline support")
    print(" ------")
    print(" TS loudnorm         A->A       EBU R128 loudness normalization")
    print(" .. tonemap          V->V       Conversion to/from different dynamic ranges.")
elif "-h" in args:
    print("-filter_complex_script filename  deprecated, use -/filter_complex instead")
    print("-vsync               set video sync method globally")
else:
    print("Unrecognized option '/filter_complex'.", file=sys.stderr)
    sys.exit(8)
"""


def test_caps_fall_back_on_an_older_ffmpeg(fake_tools: FakeTools) -> None:
    fake_tools.add("ffmpeg", OLD_FFMPEG)
    caps = ffmpeg_caps()
    assert caps.version == "6.1.1-3ubuntu5"
    assert caps.has_filter("loudnorm")
    assert not caps.has_filter("zscale")
    assert caps.filter_script_option == "-filter_complex_script"
    assert caps.fps_mode_option == "-vsync"


def test_filter_graph_goes_through_a_script_file(fake_tools: FakeTools, tmp_path: Path) -> None:
    fake_tools.add("ffmpeg", OLD_FFMPEG)
    script = tmp_path / "graph.txt"
    args = filter_graph_args(ffmpeg_caps(), "[0:v]null[v]", script)
    assert args == ["-filter_complex_script", str(script)]
    assert script.read_text(encoding="utf-8") == "[0:v]null[v]"


@real_ffmpeg
def test_caps_probe_the_installed_ffmpeg() -> None:
    ffmpeg_caps.cache_clear()
    caps = ffmpeg_caps()
    assert caps.version
    assert caps.has_filter("loudnorm")
    assert caps.filter_script_option in ("-/filter_complex", "-filter_complex_script")
    assert caps.fps_mode_option in ("-fps_mode", "-vsync")


@real_ffmpeg
def test_real_ffmpeg_failure_carries_its_stderr(tmp_path: Path) -> None:
    with pytest.raises(FFmpegError) as excinfo:
        run_ffmpeg(["-i", tmp_path / "does not exist è.mov", "-f", "null", "-"])
    assert any("does not exist" in line for line in excinfo.value.stderr_tail)
