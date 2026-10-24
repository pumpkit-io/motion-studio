"""Run ffmpeg and ffprobe from argument lists, and probe what the installed ffmpeg supports."""

import functools
import re
import shutil
import subprocess
import tempfile
import threading
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from reelcut.errors import DependencyError, InternalError

Arg = str | Path

STDERR_TAIL_LINES = 20

_FILTER_LINE = re.compile(r"^\s*[A-Z.|]{2,3}\s+(\w+)\s+\S+->\S+")


class FFmpegError(InternalError):
    """ffmpeg or ffprobe exited non-zero; the message ends with its last 20 stderr lines."""

    def __init__(self, tool: str, args: Sequence[str], returncode: int, stderr: Sequence[str]):
        self.args_list = list(args)
        self.returncode = returncode
        self.stderr_tail = list(stderr)[-STDERR_TAIL_LINES:]
        tail = "\n".join(self.stderr_tail)
        super().__init__(f"{tool} exited with code {returncode}:\n{tail}")


def binary(tool: str) -> str:
    path = shutil.which(tool)
    if path is None:
        raise DependencyError(
            f"{tool} not found on PATH",
            hint="install it with `brew install ffmpeg` (macOS) or your package manager",
        )
    return path


def _stringify(args: Sequence[Arg]) -> list[str]:
    if isinstance(args, str | bytes):
        raise TypeError("pass ffmpeg arguments as a list, never a shell string")
    return [str(a) for a in args]


def run_ffmpeg(
    args: Sequence[Arg],
    *,
    progress: Callable[[float], None] | None = None,
    timeout_s: float | None = None,
) -> list[str]:
    """Run ffmpeg with `args` (no shell) and return its stderr lines.

    With `progress`, ffmpeg writes `-progress` key=value pairs to stdout and the callback gets
    the output position in seconds after each update.
    """
    argv = [binary("ffmpeg"), "-hide_banner", "-nostdin"]
    if progress is not None:
        argv += ["-progress", "pipe:1", "-nostats"]
    argv += _stringify(args)
    stderr: deque[str] = deque(maxlen=500)
    with subprocess.Popen(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    ) as proc:
        assert proc.stdout is not None and proc.stderr is not None
        err_pipe = proc.stderr
        # Drain stderr on a thread so a chatty ffmpeg never blocks on a full pipe.
        reader = threading.Thread(target=lambda: stderr.extend(err_pipe), daemon=True)
        reader.start()
        for line in proc.stdout:
            seconds = _progress_seconds(line)
            if seconds is not None and progress is not None:
                progress(seconds)
        try:
            returncode = proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired as exc:
            proc.kill()
            raise InternalError(f"ffmpeg timed out after {timeout_s} s") from exc
        reader.join()
    lines = [line.rstrip("\n") for line in stderr]
    if returncode != 0:
        raise FFmpegError("ffmpeg", argv, returncode, lines)
    return lines


def _progress_seconds(line: str) -> float | None:
    key, _, value = line.strip().partition("=")
    if key == "out_time_us" and value.isdigit():
        return int(value) / 1_000_000
    return None


def run_ffprobe(args: Sequence[Arg], *, timeout_s: float | None = 60) -> str:
    """Run ffprobe with `args` (no shell) and return its stdout."""
    argv = [binary("ffprobe"), "-hide_banner", *_stringify(args)]
    result = subprocess.run(
        argv,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_s,
        check=False,
    )
    if result.returncode != 0:
        raise FFmpegError("ffprobe", argv, result.returncode, result.stderr.splitlines())
    return result.stdout


@dataclass(frozen=True)
class FFmpegCaps:
    """What the installed ffmpeg supports, probed rather than assumed from its version."""

    path: str
    version: str
    filters: frozenset[str]
    # `-/filter_complex <file>` (ffmpeg 7+) or `-filter_complex_script` (removed in ffmpeg 8).
    filter_script_option: str | None
    # `-fps_mode` (ffmpeg 5.1+) or the older `-vsync`.
    fps_mode_option: str

    def has_filter(self, name: str) -> bool:
        return name in self.filters


@functools.cache
def ffmpeg_caps() -> FFmpegCaps:
    path = binary("ffmpeg")
    version_out = _capture([path, "-hide_banner", "-version"])
    match = re.search(r"ffmpeg version (\S+)", version_out)
    filters_out = _capture([path, "-hide_banner", "-filters"])
    filters = frozenset(
        m.group(1) for line in filters_out.splitlines() if (m := _FILTER_LINE.match(line))
    )
    help_out = _capture([path, "-hide_banner", "-h", "full"])
    if _accepts_option_file(path):
        script_option: str | None = "-/filter_complex"
    elif "-filter_complex_script" in help_out:
        script_option = "-filter_complex_script"
    else:
        script_option = None
    return FFmpegCaps(
        path=path,
        version=match.group(1) if match else "unknown",
        filters=filters,
        filter_script_option=script_option,
        fps_mode_option="-fps_mode" if "-fps_mode" in help_out else "-vsync",
    )


def filter_graph_args(caps: FFmpegCaps, graph: str, script: Path) -> list[str]:
    """Write `graph` to `script` and return the options that make ffmpeg read it from there.

    Long graphs go through a file because argv length is limited.
    """
    if caps.filter_script_option is None:
        raise DependencyError(
            f"ffmpeg {caps.version} can read neither -/filter_complex nor -filter_complex_script",
            hint="install ffmpeg 7 or newer",
        )
    script.write_text(graph, encoding="utf-8")
    return [caps.filter_script_option, str(script)]


def _capture(argv: list[str]) -> str:
    result = subprocess.run(
        argv, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30, check=False
    )
    return result.stdout + result.stderr


def _accepts_option_file(path: str) -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        graph = Path(tmp) / "graph.txt"
        graph.write_text("null", encoding="utf-8")
        argv = [path, "-hide_banner", "-nostdin", "-loglevel", "error"]
        argv += ["-f", "lavfi", "-i", "nullsrc=s=16x16:d=0.04", "-/filter_complex", str(graph)]
        argv += ["-f", "null", "-"]
        result = subprocess.run(
            argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=30, check=False
        )
        return result.returncode == 0
