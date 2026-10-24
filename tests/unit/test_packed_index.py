"""The packed index format, pinned by a golden file.

Set REELCUT_UPDATE_GOLDEN=1 to rewrite the golden file after a deliberate format change.
"""

import os
from pathlib import Path

from reelcut.analysis import (
    ClipAnalysis,
    ClipInfo,
    Faces,
    FaceSample,
    Span,
    TranscribedWord,
    analyse_transcript,
    find_retakes,
    pack_project,
)
from reelcut.lang import load_language

GOLDEN = Path(__file__).parent / "golden" / "packed.md"


def words(script: str, start: float) -> list[TranscribedWord]:
    """Words of 250 ms with 50 ms gaps; `|1.2|` inserts that many seconds of silence."""
    out: list[TranscribedWord] = []
    t = start
    for token in script.split():
        if token.startswith("|") and token.endswith("|"):
            t += float(token.strip("|")) - 0.05
            continue
        out.append(TranscribedWord(text=token, start=round(t, 3), end=round(t + 0.25, 3)))
        t += 0.3
    return out


def aroll(
    clip_id: str, source: str, script: str, vad: list[Span], cx: float, tail: float = 1.2
) -> ClipAnalysis:
    transcript = words(script, start=1.0)
    info = ClipInfo(
        id=clip_id,
        role="aroll",
        source=source,
        duration_s=round(transcript[-1].end + tail, 3),
        width=1080,
        height=1920,
        fps=30,
    )
    analysis = analyse_transcript(info, transcript, vad, load_language("it"), confidence=0.97)
    faces = [FaceSample(t=t, cx=cx, cy=0.4, w=0.3, h=0.2, score=0.9) for t in (1.0, 1.5, 2.0)]
    return analysis.model_copy(update={"faces": Faces(samples=faces)})


def project() -> list[ClipAnalysis]:
    c1 = aroll(
        "c1",
        "raw/IMG_0412.MOV",
        "Allora, ehm, oggi vi faccio vedere come ho costruito Pumpkit in due settimane. |1.7| "
        "Il motivo per cui… |3.2| "
        "Il motivo per cui l'ho fatto è semplice: scrivere post, cioè, mi prendeva tre ore. |0.9| "
        "E poi, tipo, |0.45| basta",
        vad=[Span(start=0.9, end=5.5), Span(start=6.0, end=6.4), Span(start=7.2, end=20.0)],
        cx=0.5,
        tail=3.5,
    )
    c1 = c1.model_copy(update={"static": [Span(start=18.6, end=21.3)]})
    c2 = aroll(
        "c2",
        "raw/prova clip è.mov",
        "Ehm, il motivo per cui l'ho fatto è semplice: scrivere post mi prendeva tre ore.",
        vad=[Span(start=0.9, end=6.0)],
        cx=0.3,
    )
    b1 = ClipAnalysis(
        clip=ClipInfo(id="b1", role="broll", source="raw/broll.mp4", duration_s=6.0),
        static=[Span(start=0.0, end=2.5)],
    )
    i1 = ClipAnalysis(clip=ClipInfo(id="i1", role="image", source="raw/image.png", duration_s=0))
    return [c1, c2, b1, i1]


def test_packed_index_matches_the_golden_file() -> None:
    clips = project()
    packed = pack_project("launch-teaser", "it", clips, find_retakes(clips))

    if os.environ.get("REELCUT_UPDATE_GOLDEN"):
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(packed, encoding="utf-8")
    assert packed == GOLDEN.read_text(encoding="utf-8")
