"""Language data: one `<code>.toml` per language, holding everything language-specific.

Adding a language means adding a file here; no code names a language.
"""

import tomllib
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from motion_studio.errors import UserError
from motion_studio.text import normalise_words

LANG_DIR = Path(__file__).resolve().parent


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Asr(_Section):
    initial_prompt: str = Field(
        description="Prompt full of fillers that biases the transcriber towards verbatim output."
    )


def _normalise_phrases(phrases: list[str]) -> list[str]:
    return [" ".join(normalise_words(p)) for p in phrases if normalise_words(p)]


class Fillers(_Section):
    hard: list[str] = Field(description="Removed by the draft. Single words or phrases.")
    soft: list[str] = Field(default_factory=list, description="Marked anywhere in an utterance.")
    soft_at_start: list[str] = Field(
        default_factory=list,
        description="Marked only at the start of an utterance, after any other fillers.",
    )

    _norm = field_validator("hard", "soft", "soft_at_start")(_normalise_phrases)


class Utterances(_Section):
    incomplete_endings: list[str] = Field(
        default_factory=list,
        description="Words a finished sentence does not end on (articles, prepositions, "
        "conjunctions, auxiliaries). An utterance ending on one before a long pause is "
        "incomplete even when the transcriber put a full stop after it.",
    )

    _norm = field_validator("incomplete_endings")(_normalise_phrases)


class Captions(_Section):
    max_chars_per_page: int = Field(
        default=20, gt=0, description="Most characters on one caption page, spaces included."
    )
    keep_with_next: list[str] = Field(
        default_factory=list,
        description="Short words that never end a caption page (they join the next word).",
    )

    _norm = field_validator("keep_with_next")(_normalise_phrases)


class Language(_Section):
    code: str
    name: str
    asr: Asr
    fillers: Fillers
    utterances: Utterances = Field(default_factory=Utterances)
    captions: Captions = Field(default_factory=Captions)


def _dirs(dirs: Sequence[Path] | None) -> Sequence[Path]:
    return (LANG_DIR,) if dirs is None else dirs


def available_languages(dirs: Sequence[Path] | None = None) -> list[str]:
    """Codes of every language with a data file, sorted."""
    return sorted({p.stem for d in _dirs(dirs) for p in d.glob("*.toml")})


def load_language(code: str, dirs: Sequence[Path] | None = None) -> Language:
    """Load `<code>.toml` from the first directory that has it (motion-studio's own by default)."""
    for d in _dirs(dirs):
        path = d / f"{code}.toml"
        if path.is_file():
            break
    else:
        known = ", ".join(available_languages(dirs)) or "none"
        raise UserError(
            f"no language data for '{code}' (available: {known})",
            hint=f"add {code}.toml to {LANG_DIR}",
        )
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        language = Language.model_validate(data)
    except (tomllib.TOMLDecodeError, ValidationError) as exc:
        raise UserError(f"invalid language file {path}: {exc}") from exc
    if language.code != code:
        raise UserError(f"{path} declares code '{language.code}'; it must match the file name")
    return language
