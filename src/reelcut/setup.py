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
from reelcut.paths import find_workspace, models_dir
from reelcut.render.renderer import cached_renderer, install_renderer, is_installed
from reelcut.vision import MEDIAPIPE_MODEL, YUNET_MODEL, install_face_model


@dataclass(frozen=True)
class Item:
    name: str
    status: Literal["installed", "present"]
    path: str


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
    if music:
        raise DependencyError(
            "`setup --music` (the ACE-Step environment) is not available in this build yet",
            hint='set music.mode = "library" or "none" in reelcut.toml meanwhile',
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

    for face_model in (MEDIAPIPE_MODEL, YUNET_MODEL):
        path = models_dir() / face_model.name
        if path.is_file():
            items.append(Item(face_model.name, "present", str(path)))
        else:
            step(f"downloading {face_model.name}")
            items.append(Item(face_model.name, "installed", str(install_face_model(face_model))))

    backend, configured_model = _asr_settings(workdir or Path.cwd())
    ref = model_ref(backend, configured_model)
    ensure_backend_installed(ref)
    found = model_path(ref)
    if found is not None:
        items.append(Item(f"{backend} {ref.repo}", "present", str(found)))
    else:
        step(f"downloading {ref.repo} for {backend} (about 1.6 GB)")
        items.append(Item(f"{backend} {ref.repo}", "installed", str(install_model(ref))))

    if is_installed(cached_renderer()):
        items.append(Item("renderer", "present", str(cached_renderer())))
    else:
        items.append(Item("renderer", "installed", str(install_renderer(step))))
    return SetupReport(items)


def _asr_settings(workdir: Path) -> tuple[Any, str]:
    """The workspace's speech-to-text settings when run inside one, else the platform default."""
    try:
        config = load_config(find_workspace(workdir))
    except UserError:
        return resolve_backend("auto"), "auto"
    return resolve_backend(config.asr.backend), config.asr.model
