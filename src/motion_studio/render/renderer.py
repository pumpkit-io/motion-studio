"""Find the Remotion renderer, and install it into the cache for `setup`.

Lookup order: `MOTION_STUDIO_RENDERER_DIR`, then the repo's `renderer/` when running from a source
checkout with its dependencies installed (dev mode), then `<cache>/renderer/<version>/`.
Dev mode wins over the cache because every checkout shares one cache under the same dev version.
"""

import json
import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import motion_studio
from motion_studio import APP_NAME, ENV_PREFIX, __version__
from motion_studio.errors import DependencyError, InternalError
from motion_studio.paths import renderer_dir

RENDERER_ENV = f"{ENV_PREFIX}_RENDERER_DIR"
MARKER = f".{APP_NAME}-installed"
# What `setup` copies; node_modules is rebuilt with `npm ci` from the lock file.
SOURCE_FILES = ("package.json", "package-lock.json", "tsconfig.json", "remotion.config.ts", "src")
INSTALL_TIMEOUT_S = 1800


def remotion_bin(root: Path) -> Path:
    return root / "node_modules" / ".bin" / "remotion"


def renderer_source() -> Path:
    """The renderer sources: packaged in the wheel, or the repo's `renderer/` in a checkout."""
    packaged = Path(motion_studio.__file__).parent / "_renderer"
    repo = Path(__file__).resolve().parents[3] / "renderer"
    for candidate in (packaged, repo):
        if (candidate / "package.json").is_file():
            return candidate
    raise InternalError("the renderer sources are missing from this installation")


def cached_renderer() -> Path:
    return renderer_dir() / __version__


def is_installed(root: Path) -> bool:
    return (root / MARKER).is_file() and remotion_bin(root).exists()


def find_renderer() -> Path:
    override = os.environ.get(RENDERER_ENV)
    if override:
        root = Path(override)
        if not remotion_bin(root).exists():
            raise DependencyError(
                f"{RENDERER_ENV}={override} has no node_modules/.bin/remotion",
                hint="run `npm ci` there, or unset the variable",
            )
        return root
    repo = Path(__file__).resolve().parents[3] / "renderer"
    if remotion_bin(repo).exists():
        return repo
    if is_installed(cached_renderer()):
        return cached_renderer()
    raise DependencyError(
        f"the renderer is not installed in {cached_renderer()}",
        hint=f"run `{APP_NAME} setup` once while online",
    )


def remotion_version(root: Path) -> str | None:
    package = root / "node_modules" / "remotion" / "package.json"
    if not package.is_file():
        return None
    return str(json.loads(package.read_text(encoding="utf-8")).get("version"))


def install_renderer(on_step: Callable[[str], None] | None = None) -> Path:
    """Copy the renderer into the cache, `npm ci` it and fetch Remotion's headless browser.

    Builds in a sibling directory and renames it into place, so an interrupted install never
    leaves a half-built renderer that looks installed.
    """
    step = on_step or (lambda _msg: None)
    npm = shutil.which("npm")
    if npm is None:
        raise DependencyError("npm not found on PATH", hint="brew install node (Node 22 or newer)")
    source = renderer_source()
    dest = cached_renderer()
    partial = dest.with_name(dest.name + ".partial")
    shutil.rmtree(partial, ignore_errors=True)
    partial.mkdir(parents=True)
    for name in SOURCE_FILES:
        item = source / name
        if item.is_dir():
            shutil.copytree(item, partial / name)
        else:
            shutil.copy2(item, partial / name)
    step("installing the renderer's npm packages")
    _run([npm, "ci", "--no-audit", "--no-fund"], partial)
    step("downloading Remotion's headless browser (about 570 MB, once)")
    _run([str(remotion_bin(partial)), "browser", "ensure"], partial)
    (partial / MARKER).write_text(__version__ + "\n", encoding="utf-8")
    shutil.rmtree(dest, ignore_errors=True)
    partial.rename(dest)
    return dest


def _run(argv: list[str], cwd: Path) -> None:
    try:
        result = subprocess.run(
            argv,
            cwd=cwd,
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
