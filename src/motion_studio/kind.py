"""The project kind (ADR 0004): set once by `new --kind`, stored in project.toml, never inferred."""

import tomllib
from enum import StrEnum

from motion_studio.errors import UserError
from motion_studio.paths import ProjectPaths


class ProjectKind(StrEnum):
    TALK = "talk"
    PRODUCT = "product"


def project_kind(project: ProjectPaths) -> ProjectKind:
    """`[project] kind` from project.toml; projects made before kinds existed are talk."""
    try:
        data = tomllib.loads(project.project_toml.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise UserError(f"{project.project_toml} is not valid TOML: {exc}") from exc
    value = data.get("project", {}).get("kind", ProjectKind.TALK.value)
    try:
        return ProjectKind(value)
    except ValueError:
        raise UserError(
            f"{project.project_toml}: project.kind is {value!r}",
            hint=f"use one of {', '.join(k.value for k in ProjectKind)}",
        ) from None


def require_kind(project: ProjectPaths, kind: ProjectKind, command: str, hint: str) -> None:
    """Exit 1 when `command` makes no sense for this project's kind."""
    actual = project_kind(project)
    if actual is not kind:
        raise UserError(
            f"`{command}` is for {kind} projects; {project.slug!r} is {actual}", hint=hint
        )
