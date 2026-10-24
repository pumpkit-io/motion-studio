"""Typed errors whose exit code the CLI passes straight to the shell.

Exit codes: 0 OK, 1 fixable EDL or user error, 2 missing dependency, 3 internal error.
"""


class ReelcutError(Exception):
    """Base error. `hint` is one line telling the host agent what to do next."""

    exit_code = 3

    def __init__(self, message: str, *, hint: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint


class UserError(ReelcutError):
    """Something the creator or host agent can fix: a bad EDL, a typo in config, a wrong slug."""

    exit_code = 1


class DependencyError(ReelcutError):
    """A missing tool, model, filter or resource (including low free disk)."""

    exit_code = 2


class InternalError(ReelcutError):
    """A bug in reelcut or an unexpected failure of a tool it drives."""

    exit_code = 3
