"""The deterministic draft EDL (guide §8 Phase 6): all usable speech in source order."""

from collections.abc import Sequence

from motion_studio.analysis import ClipAnalysis, Retakes, Utterance
from motion_studio.edl.models import Edl, EdlMusic, Policy, Segment
from motion_studio.errors import UserError

RATIONALE = "deterministic draft"
SEED = 1

# Music has no lyrics, so the prompt depends on the pace only, never on the language.
_CALM = "ambient electronic, soft warm pads, gentle pulse, calm, unobtrusive, instrumental"
_STEADY = "minimal electronic, warm synths, soft drums, steady, unobtrusive, instrumental"
_ENERGETIC = (
    "upbeat minimal electronic, plucky synths, light driving drums, energetic, "
    "unobtrusive, instrumental"
)


def draft(
    clips: Sequence[ClipAnalysis],
    retakes: Retakes,
    *,
    title: str = "",
    language: str | None = None,
) -> Edl:
    """One segment per kept A-roll utterance, clips in ID order.

    Retake cluster members other than the winner are left out, which also drops an abandoned
    take whose complete retake won. Utterances made only of hard fillers are left out too.
    """
    losers = {m for cluster in retakes.clusters for m in cluster.members if m != cluster.winner}
    aroll = sorted((c for c in clips if c.clip.role == "aroll"), key=_clip_order)
    kept = [
        (analysis, u)
        for analysis in aroll
        for u in analysis.utterances
        if u.id not in losers and _has_speech(analysis, u)
    ]
    if not kept:
        raise UserError(
            "the project has no A-roll speech to draft from",
            hint="check the clip roles in project.toml, then run analyze again",
        )
    bpm, prompt = _music(kept)
    return Edl(
        title=title,
        language=language,
        policy=Policy(drop_fillers="hard", jumpcut_punch=True),
        segments=[
            Segment.model_validate(
                {
                    "id": u.id.replace(".", "-"),
                    "from": u.first_word,
                    "to": u.last_word,
                    "note": u.text,
                }
            )
            for _, u in kept
        ],
        music=EdlMusic(mode="generate", prompt=prompt, bpm=bpm, seed=SEED),
        rationale=RATIONALE,
    )


def _clip_order(analysis: ClipAnalysis) -> tuple[int, str]:
    digits = "".join(ch for ch in analysis.clip.id if ch.isdigit())
    return int(digits or 0), analysis.clip.id


def _words(analysis: ClipAnalysis, u: Utterance) -> range:
    return range(_index(u.first_word), _index(u.last_word) + 1)


def _index(word_id: str) -> int:
    return int(word_id.rsplit(".w", 1)[1])


def _has_speech(analysis: ClipAnalysis, u: Utterance) -> bool:
    return any(analysis.words[i].filler != "hard" for i in _words(analysis, u))


def _music(kept: Sequence[tuple[ClipAnalysis, Utterance]]) -> tuple[int, str]:
    words = sum(
        1 for analysis, u in kept for i in _words(analysis, u) if analysis.words[i].filler is None
    )
    seconds = sum(u.end - u.start for _, u in kept)
    pace = words / seconds if seconds > 0 else 0.0
    # The middle of the guide's BPM band for this many words per second.
    if pace < 2.3:
        return 90, _CALM
    if pace <= 3.0:
        return 103, _STEADY
    return 118, _ENERGETIC
