"""The EDL reference doc that `motion-studio docs edl` prints stays in step with the EDL models."""

import re
from importlib import resources
from pathlib import Path
from typing import get_args

from pydantic import BaseModel

from motion_studio.edl.models import Edl, EdlCaptions, EdlMusic, Event, Policy

REFERENCE = resources.files("motion_studio") / "reference" / "edl.md"
REPO_DOC = Path(__file__).resolve().parents[2] / "docs" / "edl.md"


def field_names(model: type[BaseModel]) -> set[str]:
    return {f.alias or name for name, f in model.model_fields.items()}


def test_every_edl_field_is_documented() -> None:
    text = REFERENCE.read_text(encoding="utf-8")
    event_models: tuple[type[BaseModel], ...] = get_args(get_args(Event)[0])
    models = (Edl, Policy, EdlCaptions, EdlMusic, *event_models)

    missing = sorted(
        f"{m.__name__}.{name}" for m in models for name in field_names(m) if f"`{name}`" not in text
    )

    assert not missing


def test_the_repo_docs_copy_is_the_packaged_reference() -> None:
    assert REPO_DOC.read_text(encoding="utf-8") == REFERENCE.read_text(encoding="utf-8")


def test_every_issue_code_the_resolver_raises_is_documented() -> None:
    text = REFERENCE.read_text(encoding="utf-8")
    sources = Path(__file__).resolve().parents[2] / "src" / "motion_studio" / "edl"
    raised = re.compile(r"problems\.(?:error|warn)\(\s*\"([a-z_]+)\"")
    codes = {c for path in sources.glob("*.py") for c in raised.findall(path.read_text("utf-8"))}

    assert len(codes) >= 15
    assert {c for c in codes if f"`{c}`" not in text} == set()
