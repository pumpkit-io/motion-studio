import stat
import sys
import textwrap
from collections.abc import Iterator
from pathlib import Path

import pytest

from reelcut.media.ffmpeg import ffmpeg_caps


class FakeTools:
    """A directory of stand-in executables that replaces PATH for one test."""

    def __init__(self, directory: Path) -> None:
        self.dir = directory

    def add(self, name: str, body: str) -> Path:
        script = self.dir / name
        script.write_text(f"#!{sys.executable}\n{textwrap.dedent(body)}", encoding="utf-8")
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        return script


@pytest.fixture
def fake_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeTools]:
    directory = tmp_path / "bin"
    directory.mkdir()
    monkeypatch.setenv("PATH", str(directory))
    ffmpeg_caps.cache_clear()
    yield FakeTools(directory)
    ffmpeg_caps.cache_clear()


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Keep tests out of the real machine-wide cache, including its heavy-model lock."""
    cache = tmp_path / "cache"
    monkeypatch.setenv("REELCUT_CACHE_DIR", str(cache))
    return cache
