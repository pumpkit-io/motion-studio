"""The recorders' dependencies: Playwright for `record web`, vhs and ttyd for `record terminal`.

`setup --record` installs the pinned Playwright and its headless Chromium into
`<cache>/recorder/playwright-<version>/`; recording finds them there and exits 2 with the
`setup --record` hint when they are missing. vhs and ttyd are system tools nothing installs.
"""

import json
import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from motion_studio import APP_NAME
from motion_studio.errors import DependencyError
from motion_studio.paths import cache_dir

NODE_DIR = Path(__file__).parent / "node"
MARKER = ".installed"
INSTALL_TIMEOUT_S = 1800
SETUP_HINT = f"run `{APP_NAME} setup --record` once while online"
TERMINAL_TOOLS = ("vhs", "ttyd")
# Homebrew's vhs formula depends on ffmpeg, so installing it can replace the ffmpeg build.
TERMINAL_HINT = (
    "brew install vhs (it brings ttyd); Homebrew may upgrade ffmpeg as a side effect,"
    f" so run `{APP_NAME} doctor` again afterwards"
)


def playwright_version() -> str:
    package = json.loads((NODE_DIR / "package.json").read_text(encoding="utf-8"))
    return str(package["dependencies"]["playwright"])


def recorder_dir() -> Path:
    return cache_dir() / "recorder" / f"playwright-{playwright_version()}"


def browsers_dir(root: Path) -> Path:
    return root / "browsers"


def is_installed(root: Path) -> bool:
    return (
        (root / MARKER).is_file()
        and (root / "node_modules" / "playwright").is_dir()
        and any(browsers_dir(root).glob("chromium_headless_shell-*"))
    )


def node_binary() -> str:
    node = shutil.which("node")
    if node is None:
        raise DependencyError(
            "node not found on PATH; `record web` runs the recording script in Node",
            hint="brew install node (Node 22 or newer)",
        )
    return node


def find_recorder() -> Path:
    root = recorder_dir()
    if not is_installed(root):
        raise DependencyError(
            f"Playwright {playwright_version()} and its Chromium are not installed in {root}",
            hint=SETUP_HINT,
        )
    return root


def terminal_tools() -> dict[str, str]:
    """The paths of vhs and ttyd; exits 2 naming whichever is missing."""
    found = {tool: shutil.which(tool) for tool in TERMINAL_TOOLS}
    missing = [tool for tool, path in found.items() if path is None]
    if missing:
        raise DependencyError(
            f"{' and '.join(missing)} not found on PATH; `record terminal` runs the tape with vhs,"
            " which drives the shell through ttyd",
            hint=TERMINAL_HINT,
        )
    return {tool: path for tool, path in found.items() if path is not None}


def browser_env(root: Path) -> dict[str, str]:
    return {**os.environ, "PLAYWRIGHT_BROWSERS_PATH": str(browsers_dir(root))}


def install_recorder(on_step: Callable[[str], None] | None = None) -> Path:
    """`npm ci` the pinned Playwright and fetch its headless Chromium into the cache.

    Builds in a sibling directory and renames it into place, so an interrupted install never
    looks installed.
    """
    step = on_step or (lambda _msg: None)
    npm = shutil.which("npm")
    if npm is None:
        raise DependencyError("npm not found on PATH", hint="brew install node (Node 22 or newer)")
    dest = recorder_dir()
    partial = dest.with_name(dest.name + ".partial")
    shutil.rmtree(partial, ignore_errors=True)
    partial.mkdir(parents=True)
    for name in ("package.json", "package-lock.json"):
        shutil.copy2(NODE_DIR / name, partial / name)
    step(f"installing Playwright {playwright_version()}")
    _run([npm, "ci", "--no-audit", "--no-fund"], partial, os.environ.copy())
    step("downloading Playwright's headless Chromium (about 200 MB, once)")
    cli = partial / "node_modules" / "playwright" / "cli.js"
    # Recording runs headless only, so the headless shell is the whole browser it needs.
    _run(
        [node_binary(), str(cli), "install", "--only-shell", "chromium"],
        partial,
        browser_env(partial),
    )
    (partial / MARKER).write_text(playwright_version() + "\n", encoding="utf-8")
    shutil.rmtree(dest, ignore_errors=True)
    partial.rename(dest)
    return dest


def _run(argv: list[str], cwd: Path, env: dict[str, str]) -> None:
    try:
        result = subprocess.run(
            argv,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=INSTALL_TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise DependencyError(f"`{' '.join(argv)}` timed out", hint="check the network") from exc
    if result.returncode != 0:
        tail = "\n".join((result.stdout + result.stderr).splitlines()[-20:])
        raise DependencyError(
            f"`{Path(argv[0]).name} {' '.join(argv[1:])}` failed in {cwd}:\n{tail}",
            hint="check the network and that Node 22+ is installed",
        )
