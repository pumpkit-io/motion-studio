"""`reelcut setup`: one-time downloads into the machine-wide cache, so later stages run offline.

Every step is idempotent: what is already in the cache is reported as present, not fetched.
"""

from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from reelcut.asr import (
    ensure_backend_installed,
    install_model,
    model_path,
    model_ref,
    resolve_backend,
)
from reelcut.asr.vad import SILERO_VERSION, install_vad_model, vad_model_path
from reelcut.audio.enhance import DEEP_FILTER_VERSION, deep_filter_binary, install_deep_filter
from reelcut.config import load_config
from reelcut.errors import DependencyError, UserError
from reelcut.music import acestep
from reelcut.paths import cache_dir, find_workspace
from reelcut.state import ensure_free_disk


@dataclass(frozen=True)
class Item:
    name: str
    status: Literal["installed", "present"]
    path: str
    licence: str | None = None


@dataclass(frozen=True)
class SetupReport:
    items: list[Item]

    def to_json(self) -> dict[str, Any]:
        return {"items": [asdict(i) for i in self.items]}


def run_setup(
    *,
    music: bool = False,
    crisper: bool = False,
    workdir: Path | None = None,
    on_step: Callable[[str], None] | None = None,
) -> SetupReport:
    if crisper:
        raise DependencyError(
            "the crisper fillers backend is not implemented in v0.1.0",
            hint='keep asr.fillers_backend = "prompted"',
        )
    step = on_step or (lambda _msg: None)
    items: list[Item] = []

    existing = deep_filter_binary()
    if existing is None:
        step(f"downloading DeepFilterNet {DEEP_FILTER_VERSION}")
        items.append(Item("deepfilternet", "installed", str(install_deep_filter())))
    else:
        items.append(Item("deepfilternet", "present", str(existing)))

    if vad_model_path().is_file():
        items.append(Item(f"silero-vad {SILERO_VERSION}", "present", str(vad_model_path())))
    else:
        step(f"downloading Silero VAD {SILERO_VERSION}")
        items.append(Item(f"silero-vad {SILERO_VERSION}", "installed", str(install_vad_model())))

    backend, configured_model = _asr_settings(workdir or Path.cwd())
    ref = model_ref(backend, configured_model)
    ensure_backend_installed(ref)
    found = model_path(ref)
    if found is not None:
        items.append(Item(f"{backend} {ref.repo}", "present", str(found)))
    else:
        step(f"downloading {ref.repo} for {backend} (about 1.6 GB)")
        items.append(Item(f"{backend} {ref.repo}", "installed", str(install_model(ref))))
    if music:
        items.append(_install_music(step))
    return SetupReport(items)


def _install_music(step: Callable[[str], None]) -> Item:
    if acestep.installed() is None:
        ensure_free_disk(cache_dir())
    record, fetched = acestep.install(step)
    # Licence of the exact weights downloaded; UNVERIFIED when they declare none.
    return Item(
        f"ace-step {record.weights}",
        "installed" if fetched else "present",
        str(acestep.env_root()),
        record.licence or "UNVERIFIED",
    )


def _asr_settings(workdir: Path) -> tuple[Any, str]:
    """The workspace's speech-to-text settings when run inside one, else the platform default."""
    try:
        config = load_config(find_workspace(workdir))
    except UserError:
        return resolve_backend("auto"), "auto"
    return resolve_backend(config.asr.backend), config.asr.model
