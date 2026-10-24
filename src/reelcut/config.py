"""Load and merge reelcut.toml, project.toml and EDL policy into the effective config.

Merge order, lowest first: built-in defaults < workspace < project < EDL policy.
"""

import re
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
)

from reelcut import lang
from reelcut.errors import DependencyError, UserError
from reelcut.paths import WORKSPACE_FILE, project_paths

Format = Literal["9x16", "16x9", "4x5"]

_HEX = re.compile(r"#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})")


def _hex_colour(value: object) -> object:
    if not isinstance(value, str):
        return value
    match = _HEX.fullmatch(value.strip())
    if match is None:
        raise ValueError(f"{value!r} is not a hex colour: use #RRGGBB or #RGB")
    digits = match.group(1)
    if len(digits) == 3:
        digits = "".join(c * 2 for c in digits)
    return "#" + digits.upper()


HexColor = Annotated[
    str,
    BeforeValidator(_hex_colour),
    Field(pattern=r"^#[0-9A-F]{6}$", description="#RRGGBB; #RGB is accepted and expanded."),
]

# Sections of project.toml that describe the project itself rather than override config.
PROJECT_ONLY_SECTIONS = ("project", "clips")


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Defaults(_Section):
    formats: list[Format] = Field(default_factory=lambda: ["9x16"])
    fps: int = Field(default=30, gt=0)
    max_duration_s: float = Field(default=60, gt=0)
    language: str = Field(
        default="auto", description="auto, or the code of a language with a data file (en, it)."
    )

    @field_validator("language")
    @classmethod
    def _known_language(cls, value: str) -> str:
        known = lang.available_languages()
        if value != "auto" and value not in known:
            raise ValueError(f"no language data for '{value}' (available: {', '.join(known)})")
        return value


class Review(_Section):
    plan: bool = False
    preview: bool = False


class Asr(_Section):
    backend: Literal["auto", "mlx-whisper", "faster-whisper"] = "auto"
    model: str = "auto"
    fillers_backend: Literal["prompted", "crisper"] = "prompted"


class Edit(_Section):
    """The trimming policy; an EDL's `policy` object overrides these keys."""

    pad_in_ms: int = Field(default=80, ge=0)
    pad_out_ms: int = Field(default=120, ge=0)
    max_pause_ms: int = Field(default=350, ge=0)
    min_segment_ms: int = Field(default=400, ge=0)
    drop_fillers: Literal["none", "hard", "hard+soft"] = "hard"
    jumpcut_punch: bool = True
    jumpcut_punch_scale: float = Field(default=1.08, ge=1)
    look_budget: int = Field(default=8, ge=0)


class Captions(_Section):
    enabled: bool = True
    style: Literal["pop", "clean", "karaoke"] = "pop"
    font: str = "Inter"
    max_words_per_page: int = Field(default=3, ge=1)
    uppercase: bool = False
    highlight_color: HexColor = "#FFD400"
    text_color: HexColor = "#FFFFFF"
    stroke_color: HexColor = "#000000"


class Music(_Section):
    mode: Literal["generate", "library", "none"] = "generate"
    gain_db: float = -20
    duck_threshold: float = Field(default=0.03, gt=0)
    duck_ratio: float = Field(default=8, ge=1)


class Master(_Section):
    integrated_lufs: float = -14
    true_peak_db: float = -1.5
    lra: float = 11


class Brand(_Section):
    primary: HexColor = "#111111"
    accent: HexColor = "#FFD400"
    logo: str = "library/brand/logo.png"


class Config(_Section):
    """The effective config; every key in reelcut.toml can be overridden in project.toml."""

    schema_version: Literal[1] = 1
    defaults: Defaults = Field(default_factory=Defaults)
    review: Review = Field(default_factory=Review)
    asr: Asr = Field(default_factory=Asr)
    edit: Edit = Field(default_factory=Edit)
    captions: Captions = Field(default_factory=Captions)
    music: Music = Field(default_factory=Music)
    master: Master = Field(default_factory=Master)
    brand: Brand = Field(default_factory=Brand)

    def ensure_supported(self) -> None:
        """Reject values the schema accepts but this release cannot run. Stages call this first."""
        if self.asr.fillers_backend == "crisper":
            raise DependencyError(
                'asr.fillers_backend = "crisper" is not implemented in v0.1.0',
                hint='set fillers_backend = "prompted" in reelcut.toml or project.toml',
            )


def load_config(
    workspace: Path,
    slug: str | None = None,
    *,
    edl_policy: Mapping[str, Any] | None = None,
) -> Config:
    """Merge the workspace, project and EDL policy levels over the built-in defaults."""
    merged: dict[str, Any] = {}
    sources = [workspace / WORKSPACE_FILE]
    _deep_merge(merged, _read_toml(workspace / WORKSPACE_FILE))
    if slug is not None:
        project = project_paths(workspace, slug)
        project.require()
        if project.project_toml.exists():
            data = _read_toml(project.project_toml)
            for key in PROJECT_ONLY_SECTIONS:
                data.pop(key, None)
            _deep_merge(merged, data)
            sources.append(project.project_toml)
    try:
        config = Config.model_validate(merged)
    except ValidationError as exc:
        names = " or ".join(str(p) for p in sources)
        raise UserError(f"invalid config in {names}: {_describe(exc)}") from exc
    if edl_policy:
        try:
            edit = Edit.model_validate({**config.edit.model_dump(), **edl_policy})
        except ValidationError as exc:
            raise UserError(f"invalid EDL policy: {_describe(exc)}") from exc
        config = config.model_copy(update={"edit": edit})
    return config


def _read_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise UserError(f"{path} is not valid TOML: {exc}") from exc


def _deep_merge(base: dict[str, Any], override: Mapping[str, Any]) -> None:
    for key, value in override.items():
        current = base.get(key)
        if isinstance(current, dict) and isinstance(value, Mapping):
            _deep_merge(current, value)
        else:
            base[key] = dict(value) if isinstance(value, Mapping) else value


def _describe(exc: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(part) for part in err['loc'])}: {err['msg']}" for err in exc.errors()
    )
