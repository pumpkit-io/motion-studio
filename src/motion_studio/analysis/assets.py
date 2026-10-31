"""The asset catalogue (`analysis/assets.md`, guide §6.3): every B-roll clip and image.

The host agent fills in each description after viewing the asset's contact sheet; repacking
reads the old catalogue first, so its descriptions survive a re-analysis.
"""

import re
from collections.abc import Mapping, Sequence
from pathlib import PurePosixPath

from motion_studio.analysis.models import ClipAnalysis

INSTRUCTIONS = (
    "Write one line after `description:` for each asset once you have viewed its contact "
    "sheet; analyze keeps what you write."
)
_HEADING = re.compile(r"^## (\S+) · ")
_DESCRIPTION = "- description:"


def pack_assets(
    title: str,
    clips: Sequence[ClipAnalysis],
    *,
    descriptions: Mapping[str, str],
    sheets: Mapping[str, str],
) -> str:
    """Render the catalogue; `sheets` maps an asset ID to its contact sheet's project path."""
    assets = [c for c in clips if c.clip.role in ("broll", "image")]
    broll = sum(1 for c in assets if c.clip.role == "broll")
    lines = [
        f"# Assets: {title} · B-roll {broll} · images {len(assets) - broll}",
        INSTRUCTIONS,
    ]
    if not assets:
        lines += ["", "No B-roll or images in this project."]
    for analysis in assets:
        clip = analysis.clip
        description = descriptions.get(clip.id, "")
        lines += [
            "",
            f"## {clip.id} · {PurePosixPath(clip.source).name}",
            f"- file: {' · '.join(_facts(analysis))}",
            f"- contact sheet: {sheets.get(clip.id, 'none')}",
            f"{_DESCRIPTION} {description}".rstrip(),
        ]
    return "\n".join(lines) + "\n"


def read_descriptions(text: str) -> dict[str, str]:
    """The non-blank descriptions in a catalogue, by asset ID."""
    found: dict[str, str] = {}
    current: str | None = None
    for line in text.splitlines():
        heading = _HEADING.match(line)
        if heading:
            current = heading.group(1)
        elif current and line.startswith(_DESCRIPTION):
            description = line.removeprefix(_DESCRIPTION).strip()
            if description:
                found[current] = description
    return found


def _facts(analysis: ClipAnalysis) -> list[str]:
    clip = analysis.clip
    facts = [clip.source]
    if clip.role == "image":
        facts.append("still image")
    else:
        facts.append(f"{clip.duration_s:.1f}s")
    if clip.width and clip.height:
        facts.append(f"{clip.width}x{clip.height}")
    shots = 1 if clip.role == "image" else max(1, len(analysis.shots))
    facts.append(f"{shots} shot" if shots == 1 else f"{shots} shots")
    return facts
