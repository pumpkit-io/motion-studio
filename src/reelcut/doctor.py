"""Check the machine for every tool, filter, model and resource reelcut needs."""

import importlib.util
import os
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from reelcut import APP_NAME, __version__
from reelcut.asr import DEFAULT_MODELS, default_backend, hf_cache, model_path
from reelcut.asr.vad import SILERO_VERSION, vad_model_path
from reelcut.audio.enhance import DEEP_FILTER_VERSION, deep_filter_binary
from reelcut.errors import DependencyError
from reelcut.media.ffmpeg import ffmpeg_caps
from reelcut.paths import cache_dir, envs_dir, renderer_dir
from reelcut.state import free_disk_gb, min_free_gb
from reelcut.vision import mediapipe_model_path, yunet_model_path

REQUIRED_FILTERS = (
    "tonemap",
    "loudnorm",
    "sidechaincompress",
    "ebur128",
    "blackdetect",
    "freezedetect",
    "arnndn",
    "colorspace",
)
# HDR tone-mapping per ADR 0003: scale_vt on macOS, zscale where present, else colorspace.
OPTIONAL_FILTERS = ("zscale", "scale_vt", "libplacebo")

MIN_NODE_MAJOR = 20
LOW_RAM_GB = 16

Status = Literal["ok", "warn", "missing"]


@dataclass(frozen=True)
class Check:
    name: str
    status: Status
    required: bool
    detail: str
    fix: str | None = None


@dataclass(frozen=True)
class Report:
    checks: list[Check]
    ffmpeg: dict[str, Any]
    disk: dict[str, Any]
    ram_gb: float

    @property
    def ok(self) -> bool:
        return not any(c.required and c.status == "missing" for c in self.checks)

    def to_json(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "checks": [asdict(c) for c in self.checks],
            "ffmpeg": self.ffmpeg,
            "disk": self.disk,
            "ram_gb": self.ram_gb,
        }


def run_doctor(workdir: Path) -> Report:
    checks, ffmpeg = _ffmpeg_checks()
    checks += _node_checks()
    checks.append(_asr_check())
    checks += _speech_model_checks()
    checks.append(_face_model_check())
    checks += _cache_checks()
    disk_check, disk = _disk_check(workdir)
    checks.append(disk_check)
    ram = _ram_gb()
    checks.append(
        Check(
            "ram",
            "ok" if ram >= LOW_RAM_GB else "warn",
            False,
            f"{ram:.0f} GB",
            None if ram >= LOW_RAM_GB else "heavy models run one at a time; expect slow stages",
        )
    )
    return Report(checks, ffmpeg, disk, round(ram, 1))


def _ffmpeg_checks() -> tuple[list[Check], dict[str, Any]]:
    fix = "brew install ffmpeg (macOS) or install ffmpeg 7+ with your package manager"
    try:
        caps = ffmpeg_caps()
    except DependencyError:
        return (
            [Check("ffmpeg", "missing", True, "not found on PATH", fix)],
            {"version": None, "filters": {}},
        )
    checks = [Check("ffmpeg", "ok", True, f"{caps.version} at {caps.path}")]
    if shutil.which("ffprobe"):
        checks.append(Check("ffprobe", "ok", True, shutil.which("ffprobe") or ""))
    else:
        checks.append(Check("ffprobe", "missing", True, "not found on PATH", fix))
    filters = {name: caps.has_filter(name) for name in (*REQUIRED_FILTERS, *OPTIONAL_FILTERS)}
    missing = [name for name in REQUIRED_FILTERS if not filters[name]]
    if missing:
        checks.append(
            Check("ffmpeg filters", "missing", True, f"missing {', '.join(missing)}", fix)
        )
    else:
        checks.append(Check("ffmpeg filters", "ok", True, f"all {len(REQUIRED_FILTERS)} present"))
    hdr = "scale_vt" if filters["scale_vt"] else "zscale" if filters["zscale"] else None
    checks.append(
        Check(
            "hdr tonemap",
            "ok" if hdr else "warn",
            False,
            f"uses {hdr}" if hdr else "neither scale_vt nor zscale; falls back to colorspace",
        )
    )
    if caps.filter_script_option is None:
        checks.append(
            Check("filter scripts", "missing", True, "no -/filter_complex", "install ffmpeg 7+")
        )
    else:
        checks.append(Check("filter scripts", "ok", True, caps.filter_script_option))
    info = {
        "version": caps.version,
        "path": caps.path,
        "filters": filters,
        "filter_script_option": caps.filter_script_option,
        "fps_mode_option": caps.fps_mode_option,
    }
    return checks, info


def _node_checks() -> list[Check]:
    fix = f"brew install node (Node {MIN_NODE_MAJOR} or newer)"
    checks: list[Check] = []
    version = _version_of("node")
    if version is None:
        checks.append(Check("node", "missing", True, "not found on PATH", fix))
    else:
        match = re.search(r"(\d+)\.", version)
        major = int(match.group(1)) if match else 0
        if major < MIN_NODE_MAJOR:
            checks.append(
                Check("node", "missing", True, f"{version} is older than {MIN_NODE_MAJOR}", fix)
            )
        else:
            checks.append(Check("node", "ok", True, version))
    npm = _version_of("npm")
    checks.append(
        Check("npm", "ok", True, npm) if npm else Check("npm", "missing", True, "not found", fix)
    )
    return checks


def _version_of(tool: str) -> str | None:
    path = shutil.which(tool)
    if path is None:
        return None
    try:
        result = subprocess.run(
            [path, "--version"], capture_output=True, text=True, timeout=20, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() or None


def _asr_check() -> Check:
    ref = DEFAULT_MODELS[default_backend()]
    module, extra = ref.python_module, ref.extra
    if importlib.util.find_spec(module) is None:
        return Check(
            "asr backend",
            "missing",
            True,
            f"{module} is not installed",
            f"reinstall with the `{extra}` extra: uv tool install '{APP_NAME}[{extra}]'",
        )
    return Check("asr backend", "ok", True, module)


def _speech_model_checks() -> list[Check]:
    # Missing models only fail `analyze`; they stay warnings so doctor passes before `setup`.
    setup = f"run `{APP_NAME} setup` once while online"
    vad = vad_model_path()
    ref = DEFAULT_MODELS[default_backend()]
    found = model_path(ref)
    return [
        Check(
            "vad model",
            "ok" if vad.is_file() else "warn",
            False,
            str(vad) if vad.is_file() else f"Silero VAD {SILERO_VERSION} not in {vad.parent}",
            None if vad.is_file() else setup,
        ),
        Check(
            "asr model",
            "ok" if found else "warn",
            False,
            str(found) if found else f"{ref.repo} not in {hf_cache()}",
            None if found else setup,
        ),
    ]


def _face_model_check() -> Check:
    mediapipe, yunet = mediapipe_model_path(), yunet_model_path()
    setup = f"run `{APP_NAME} setup` once while online"
    if mediapipe.is_file():
        return Check("face model", "ok", False, str(mediapipe))
    if yunet.is_file():
        return Check(
            "face model", "warn", False, f"YuNet fallback only: {mediapipe.name} missing", setup
        )
    return Check("face model", "warn", False, f"no face model in {mediapipe.parent}", setup)


def _cache_checks() -> list[Check]:
    # `setup` fills these; until it has run they are warnings, not failures.
    setup = f"run `{APP_NAME} setup`"
    setup_music = f"run `{APP_NAME} setup --music`"
    renderer = renderer_dir() / __version__
    ace = envs_dir() / "ace-step"
    deep_filter = deep_filter_binary()
    return [
        Check(
            "renderer",
            "ok" if renderer.is_dir() else "warn",
            False,
            str(renderer),
            None if renderer.is_dir() else setup,
        ),
        Check(
            "ace-step env",
            "ok" if ace.is_dir() else "warn",
            False,
            str(ace),
            None if ace.is_dir() else setup_music,
        ),
        Check(
            "deepfilternet",
            "ok" if deep_filter else "warn",
            False,
            str(deep_filter) if deep_filter else "not found; ingest falls back to ffmpeg arnndn",
            None if deep_filter else f"{setup}, or put deep-filter {DEEP_FILTER_VERSION} on PATH",
        ),
    ]


def _disk_check(workdir: Path) -> tuple[Check, dict[str, Any]]:
    threshold = min_free_gb()
    places = {"workdir": workdir, "cache": cache_dir()}
    free = {name: round(free_disk_gb(path), 1) for name, path in places.items()}
    lowest = min(free.values())
    status: Status = "ok" if lowest >= threshold else "warn"
    detail = ", ".join(f"{name} {gb:.0f} GB free" for name, gb in free.items())
    fix = (
        None
        if status == "ok"
        else f"free disk: long stages refuse to start below {threshold:.0f} GB"
    )
    disk = {"free_gb": lowest, "threshold_gb": threshold, "by_location": free}
    return Check("disk", status, False, detail, fix), disk


def _ram_gb() -> float:
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1e9
    except (ValueError, OSError):
        return 0.0
