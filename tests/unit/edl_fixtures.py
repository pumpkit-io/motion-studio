"""Constructed analyses and EDLs for the EDL tests."""

from typing import Any

from motion_studio.analysis import ClipAnalysis, ClipInfo, Span, TranscribedWord, analyse_transcript
from motion_studio.analysis.models import Marker, Role
from motion_studio.edl.models import ProductEdl, TalkEdl
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


def edl(*segments: tuple[str, str, str], **extra: Any) -> TalkEdl:
    return TalkEdl.model_validate(
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


def screen(clip_id: str, duration: float, markers: dict[str, float] | None = None) -> ClipAnalysis:
    """A 1600x900 screen recording with these named markers (seconds on its clock)."""
    info = ClipInfo(
        id=clip_id,
        role="screen",
        source=f"raw/{clip_id}.mp4",
        mezzanine=f"media/{clip_id}.mp4",
        duration_s=duration,
        fps=30,
        width=1600,
        height=900,
    )
    marks = [Marker(name=n, t=t) for n, t in (markers or {}).items()]
    return ClipAnalysis(
        clip=info,
        markers_source=f"raw/{clip_id}.markers.json" if markers else None,
        markers=marks,
    )


def product(*scenes: dict[str, Any], **extra: Any) -> ProductEdl:
    return ProductEdl.model_validate({"kind": "product", "scenes": list(scenes), **extra})
