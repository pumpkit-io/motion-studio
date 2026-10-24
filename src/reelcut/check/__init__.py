"""QA for a render: re-transcribe and diff, cut stills, loudness, black and frozen frames."""

from reelcut.check.pipeline import CheckReport, check_project

__all__ = ["CheckReport", "check_project"]
