"""Errors and warnings found while resolving an EDL, each with a fix in EDL terms."""

from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict

from reelcut.errors import UserError


class Issue(BaseModel):
    """One problem in an EDL. `code` is stable for scripts; `hint` says what to change."""

    model_config = ConfigDict(frozen=True)

    code: str
    message: str
    hint: str | None = None


class EdlError(UserError):
    """The EDL cannot be resolved. Exit code 1: the host agent fixes the EDL and retries."""

    def __init__(self, problems: Iterable[Issue]) -> None:
        self.problems = list(problems)
        first = self.problems[0]
        more = len(self.problems) - 1
        message = first.message + (f" (and {more} more)" if more else "")
        super().__init__(message, hint=first.hint)


class Problems:
    """Collects errors and warnings so one validate run reports all of them."""

    def __init__(self) -> None:
        self.errors: list[Issue] = []
        self.warnings: list[Issue] = []

    def error(self, code: str, message: str, hint: str | None = None) -> None:
        issue = Issue(code=code, message=message, hint=hint)
        if issue not in self.errors:
            self.errors.append(issue)

    def warn(self, code: str, message: str, hint: str | None = None) -> None:
        self.warnings.append(Issue(code=code, message=message, hint=hint))

    def raise_errors(self) -> None:
        if self.errors:
            raise EdlError(self.errors)
