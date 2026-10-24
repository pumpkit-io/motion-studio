"""Generate schemas/*.schema.json from the Pydantic contracts.

CI reruns this and fails on a diff, so the committed schemas never drift from the models.
"""

import json
from pathlib import Path

from pydantic import BaseModel

from reelcut.analysis import ClipAnalysis
from reelcut.config import Config

ROOT = Path(__file__).resolve().parent.parent
SCHEMAS = ROOT / "schemas"

# The key names the file; edl and timeline join as their tickets land.
CONTRACTS: dict[str, type[BaseModel]] = {"analysis": ClipAnalysis, "config": Config}


def main() -> None:
    SCHEMAS.mkdir(exist_ok=True)
    for name, model in sorted(CONTRACTS.items()):
        schema = model.model_json_schema()
        text = json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        (SCHEMAS / f"{name}.schema.json").write_text(text, encoding="utf-8")
        print(SCHEMAS / f"{name}.schema.json")


if __name__ == "__main__":
    main()
