"""The project language from the clips' detected languages."""

from motion_studio.analysis import (
    ClipAnalysis,
    ClipInfo,
    LanguageGuess,
    Utterance,
    project_language,
)
from motion_studio.analysis.models import Role


def clip(clip_id: str, code: str | None, seconds: float, role: Role = "aroll") -> ClipAnalysis:
    utterances = (
        [
            Utterance(
                id=f"{clip_id}.s0",
                start=0,
                end=seconds,
                first_word=f"{clip_id}.w0",
                last_word=f"{clip_id}.w0",
                text="x",
                complete=True,
            )
        ]
        if code
        else []
    )
    return ClipAnalysis(
        clip=ClipInfo(id=clip_id, role=role, source=f"raw/{clip_id}.mov", duration_s=60),
        language=LanguageGuess(code=code, confidence=0.9) if code else None,
        utterances=utterances,
    )


def test_the_language_with_most_a_roll_speech_wins_over_the_clip_count() -> None:
    clips = [clip("c1", "en", 10), clip("c2", "en", 10), clip("c3", "it", 30)]
    assert project_language(clips) == "it"


def test_b_roll_speech_does_not_count() -> None:
    clips = [clip("c1", "en", 10), clip("b1", "it", 50, role="broll")]
    assert project_language(clips) == "en"


def test_a_configured_language_overrides_detection() -> None:
    assert project_language([clip("c1", "it", 10)], "en") == "en"


def test_a_project_without_speech_falls_back_to_english() -> None:
    assert project_language([clip("c1", None, 0)]) == "en"


def test_a_tie_goes_to_the_language_heard_first() -> None:
    assert project_language([clip("c1", "it", 10), clip("c2", "en", 10)]) == "it"
