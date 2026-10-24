"""Preview or final: the two things `render` and `check` can be pointed at."""

from enum import StrEnum


class RenderTarget(StrEnum):
    """Each value is also the `state.json` stage that renders it."""

    PREVIEW = "preview"
    FINAL = "final"

    @classmethod
    def from_flags(cls, *, final: bool) -> "RenderTarget":
        return cls.FINAL if final else cls.PREVIEW

    @property
    def stage(self) -> str:
        return self.value

    @property
    def flag(self) -> str:
        return f"--{self.value}"

    @property
    def check_record(self) -> str:
        """`check` is a pipeline stage for previews; a final's check records as `check.final`."""
        return "check" if self is RenderTarget.PREVIEW else "check.final"
