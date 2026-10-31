"""Constructed analyses and EDLs for the EDL tests."""

from typing import Any

from motion_studio.analysis import ClipAnalysis, ClipInfo, Span, TranscribedWord, analyse_transcript
from motion_studio.analysis.models import Role
from motion_studio.edl import Edl
from motion_studio.lang import load_language

WORD_S = 0.3
WORD_GAP_S = 0.1
UTTERANCE_GAP_S = 1.0


def clip(clip_id: str, *utterances: str, start: float = 0.5) -> ClipAnalysis:
    """Words last 0.3 s with 0.1 s between them; utterances are 1.1 s apart; 0.5 s of tail."""
    words: list[TranscribedWord] = []
    t = start
    for utterance in utterances:
        for token in utterance.split():
            words.append(TranscribedWord(text=token, start=round(t, 3), end=round(t + WORD_S, 3)))
            t += WORD_S + WORD_GAP_S
        t += UTTERANCE_GAP_S
    duration = round(t - UTTERANCE_GAP_S - WORD_GAP_S + 0.5, 3)
    info = ClipInfo(id=clip_id, role="aroll", source=f"raw/{clip_id}.mov", duration_s=duration)
    return analyse_transcript(info, words, [Span(start=0.0, end=duration)], load_language("en"))


def timed(clip_id: str, *words: tuple[str, float, float], tail: float = 0.5) -> ClipAnalysis:
    """A clip with exactly these (text, start, end) words."""
    transcribed = [TranscribedWord(text=t, start=s, end=e) for t, s, e in words]
    duration = round(words[-1][2] + tail, 3)
    info = ClipInfo(id=clip_id, role="aroll", source=f"raw/{clip_id}.mov", duration_s=duration)
    return analyse_transcript(
        info, transcribed, [Span(start=0.0, end=duration)], load_language("en")
    )


def edl(*segments: tuple[str, str, str], **extra: Any) -> Edl:
    return Edl.model_validate(
        {"segments": [{"id": i, "from": f, "to": t} for i, f, t in segments], **extra}
    )


def asset(clip_id: str, role: Role, duration: float) -> ClipAnalysis:
    info = ClipInfo(
        id=clip_id,
        role=role,
        source=f"raw/{clip_id}.mov",
        mezzanine=f"media/{clip_id}.mp4",
        duration_s=duration,
    )
    return ClipAnalysis(clip=info)
