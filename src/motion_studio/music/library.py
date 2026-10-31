"""Library mode: pick a licensed track from `library/music/tags.json` by mood and BPM."""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from motion_studio.errors import UserError
from motion_studio.paths import ProjectPaths

_WORD = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


class Track(BaseModel):
    model_config = ConfigDict(extra="ignore")

    file: str
    title: str = ""
    mood: list[str] = Field(default_factory=lambda: list[str]())
    bpm: float | None = None
    energy: int | None = Field(default=None, ge=1, le=5)
    licence: str | None = None
    source_url: str | None = None
    attribution: str | None = None

    @property
    def licensed(self) -> bool:
        return bool(self.licence and self.licence.strip())


@dataclass
class Pick:
    track: Track
    warnings: list[str]


def tags_path(workspace: Path) -> Path:
    return workspace / "library" / "music" / "tags.json"


def load_tags(workspace: Path) -> list[Track]:
    path = tags_path(workspace)
    if not path.exists():
        raise UserError(
            f"library mode needs {path}",
            hint='add licensed tracks as library/music/README.md describes, or use "generate"',
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise UserError(f"{path} must be a JSON list of track entries")
        return [Track.model_validate(entry) for entry in data]  # pyright: ignore[reportUnknownVariableType]
    except (json.JSONDecodeError, ValidationError) as exc:
        raise UserError(f"{path} is invalid: {exc}") from exc


def pick(tracks: list[Track], *, prompt: str | None, bpm: float | None, track: str | None) -> Pick:
    """The named track, or the licensed track sharing most mood tags with the prompt.

    Ties go to the nearest BPM, then to the file name, so the pick is deterministic.
    Raises UserError for a named track without a licence, or when no track has one.
    """
    if track is not None:
        named = [t for t in tracks if track in (t.file, t.title)]
        if not named:
            raise UserError(f"library has no track {track!r}", hint="use a `file` from tags.json")
        if not named[0].licensed:
            raise UserError(
                f"library track {track!r} has no licence, so it is refused",
                hint="add its `licence` to tags.json if you hold one, or pick another track",
            )
        return Pick(named[0], [])
    licensed = [t for t in tracks if t.licensed]
    if not licensed:
        raise UserError(
            "no library track has a licence, so none can be used",
            hint='record each track\'s `licence` in tags.json, or use "mode": "generate"',
        )
    skipped = len(tracks) - len(licensed)
    warnings = [f"skipped {skipped} library track(s) without a licence"] if skipped else []
    words = set(_WORD.findall((prompt or "").lower()))

    def rank(t: Track) -> tuple[int, float, str]:
        overlap = len(words & {m.lower() for m in t.mood})
        distance = abs(t.bpm - bpm) if bpm is not None and t.bpm is not None else 0.0
        return (-overlap, distance, t.file)

    return Pick(min(licensed, key=rank), warnings)


def write_credits(project: ProjectPaths, track: Track) -> Path | None:
    """`final/<slug>_credits.txt` when the track needs attribution; None otherwise."""
    if not track.attribution:
        return None
    path = project.final / f"{project.slug}_credits.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"Music: {track.attribution}", f"Licence: {track.licence}"]
    if track.source_url:
        lines.append(f"Source: {track.source_url}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
