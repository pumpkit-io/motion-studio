"""The project language: the configured one, or the language of most A-roll speech."""

from collections import defaultdict
from collections.abc import Sequence

from motion_studio.analysis.models import ClipAnalysis

FALLBACK_LANGUAGE = "en"


def project_language(clips: Sequence[ClipAnalysis], configured: str = "auto") -> str:
    """`configured` unless it is "auto"; then the language with the most A-roll speech time.

    Speech time is the sum of utterance durations. Ties go to the language heard first in clip
    order; a project without A-roll speech falls back to English.
    """
    if configured != "auto":
        return configured
    seconds: dict[str, float] = defaultdict(float)
    for clip in clips:
        if clip.clip.role == "aroll" and clip.language is not None:
            seconds[clip.language.code] += sum(u.end - u.start for u in clip.utterances)
    if not seconds:
        return FALLBACK_LANGUAGE
    return max(seconds, key=lambda code: seconds[code])
