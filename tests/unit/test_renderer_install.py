"""`setup`'s renderer install into the cache, and `doctor` reporting it, with a stand-in npm."""

import json
from pathlib import Path

import pytest
from conftest import FakeTools
from test_doctor_cli import FILTERS, check, doctor_json, fake_ffmpeg, fake_node

from reelcut import __version__
from reelcut.errors import DependencyError
from reelcut.render.renderer import install_renderer

# `npm ci` lays down a remotion binary that logs its arguments, and the remotion package.json.
FAKE_NPM = """
    import sys
    from pathlib import Path
    if sys.argv[1:2] == ["--version"]:
        print("11.6.0")
        raise SystemExit(0)
    if {fail!r}:
        print("npm error network", file=sys.stderr)
        raise SystemExit(1)
    bin_dir = Path("node_modules/.bin")
    bin_dir.mkdir(parents=True)
    remotion = bin_dir / "remotion"
    log = "open('browser.log', 'a').write(' '.join(sys.argv[1:]))"
    remotion.write_text("#!{python}\\nimport sys; " + log + "\\n")
    remotion.chmod(0o755)
    pkg = Path("node_modules/remotion")
    pkg.mkdir(parents=True)
    (pkg / "package.json").write_text('{{"version": "4.0.538"}}')
"""


def fake_npm(tools: FakeTools, *, fail: bool = False) -> None:
    import sys

    tools.add("npm", FAKE_NPM.format(fail=fail, python=sys.executable))
    tools.add("node", 'print("v24.8.0")\n')


def test_install_copies_the_renderer_runs_npm_ci_and_fetches_the_browser(
    fake_tools: FakeTools, isolated_cache: Path
) -> None:
    fake_npm(fake_tools)

    root = install_renderer()

    assert root == isolated_cache / "renderer" / __version__
    assert (root / "src" / "index.ts").is_file()
    assert json.loads((root / "package.json").read_text())["name"] == "reelcut-renderer"
    assert (root / "browser.log").read_text() == "browser ensure"
    assert not root.with_name(root.name + ".partial").exists()


def test_doctor_reports_the_installed_renderer_and_its_remotion_version(
    fake_tools: FakeTools, isolated_cache: Path
) -> None:
    fake_ffmpeg(fake_tools, FILTERS)
    fake_npm(fake_tools)
    _, before = doctor_json()
    install_renderer()

    _, after = doctor_json()

    assert check(before, "renderer")["status"] == "warn"
    assert "setup" in check(before, "renderer")["fix"]
    assert check(after, "renderer")["status"] == "ok"
    detail = check(after, "renderer")["detail"]
    assert str(isolated_cache / "renderer" / __version__) in detail
    assert "4.0.538" in detail


def test_a_failed_npm_ci_leaves_nothing_that_looks_installed(
    fake_tools: FakeTools, isolated_cache: Path
) -> None:
    fake_ffmpeg(fake_tools, FILTERS)
    fake_npm(fake_tools, fail=True)

    with pytest.raises(DependencyError, match="network"):
        install_renderer()

    assert not (isolated_cache / "renderer" / __version__).exists()
    fake_node(fake_tools)
    _, payload = doctor_json()
    assert check(payload, "renderer")["status"] == "warn"
