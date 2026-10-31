"""Generate schemas/*.schema.json from the Pydantic contracts, and the renderer's TS types.

CI reruns this and fails on a diff, so the committed schemas never drift from the models.
"""

import json
import subprocess
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from motion_studio.analysis import ClipAnalysis, ScreenMarkers
from motion_studio.config import Config
from motion_studio.edl import Edl, Timeline
from motion_studio.music.stage import MusicInfo

ROOT = Path(__file__).resolve().parent.parent
SCHEMAS = ROOT / "schemas"

RENDERER = ROOT / "renderer"
TYPES = RENDERER / "src" / "types.gen.ts"

# The key names the file.
CONTRACTS: dict[str, type[BaseModel]] = {
    "analysis": ClipAnalysis,
    "config": Config,
    "edl": Edl,
    "markers": ScreenMarkers,
    "music": MusicInfo,
    "timeline": Timeline,
}


def main() -> None:
    SCHEMAS.mkdir(exist_ok=True)
    for name, model in sorted(CONTRACTS.items()):
        # motion-studio writes the timeline and the renderer reads it: its contract is the output.
        schema = model.model_json_schema(
            mode="serialization" if model is Timeline else "validation"
        )
        text = json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        (SCHEMAS / f"{name}.schema.json").write_text(text, encoding="utf-8")
        print(SCHEMAS / f"{name}.schema.json")
    write_types(SCHEMAS / "timeline.schema.json")


def write_types(schema: Path) -> None:
    """Timeline types for the renderer, via json-schema-to-typescript (a renderer devDependency)."""
    # json2ts turns every property title into a named alias; models keep their titles.
    stripped = _drop_property_titles(json.loads(schema.read_text(encoding="utf-8")))
    banner = (
        "// GENERATED from schemas/timeline.schema.json by scripts/gen_schemas.py. Do not edit."
    )
    result = subprocess.run(
        [
            str(RENDERER / "node_modules" / ".bin" / "json2ts"),
            "--bannerComment",
            banner,
            "--unknownAny",
        ],
        input=json.dumps(stripped),
        capture_output=True,
        text=True,
        check=True,
    )
    TYPES.write_text(result.stdout, encoding="utf-8")
    print(TYPES)


def _drop_property_titles(node: Any) -> Any:
    if isinstance(node, dict):
        cleaned = {k: _drop_property_titles(v) for k, v in node.items()}
        properties = cleaned.get("properties")
        if isinstance(properties, dict):
            for prop in properties.values():
                if isinstance(prop, dict):
                    prop.pop("title", None)
        return cleaned
    if isinstance(node, list):
        return [_drop_property_titles(item) for item in node]
    return node


if __name__ == "__main__":
    main()
