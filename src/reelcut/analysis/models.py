"""The analysis contracts: `analysis/<clip>.json` (guide §6.1) and `analysis/retakes.json`.

Times are seconds in source time, measured from the start of the clip's mezzanine.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Role = Literal["aroll", "broll", "image"]
FillerKind = Literal["hard", "soft"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Span(_Model):
    """A stretch of source time."""

    start: float = Field(ge=0, description="Start, seconds.")
    end: float = Field(ge=0, description="End, seconds.")


class ClipInfo(_Model):
    id: str = Field(description="Stable short clip ID: c1 (A-roll), b1 (B-roll), i1 (image).")
    role: Role
    source: str = Field(description="Original file, relative to the project: raw/IMG_0412.MOV.")
    mezzanine: str | None = Field(
        default=None, description="Normalised video, relative to the project."
    )
    audio: str | None = Field(default=None, description="Enhanced voice, relative to the project.")
    duration_s: float = Field(ge=0)
    fps: float | None = Field(default=None, gt=0)
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    input_hash: str | None = None


class LanguageGuess(_Model):
    code: str = Field(description="Language code with a data file in reelcut's lang directory.")
    confidence: float = Field(ge=0, le=1)


class TranscribedWord(_Model):
    """A word as a speech-to-text backend returns it, before analysis."""

    text: str
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    conf: float = Field(default=1.0, ge=0, le=1)


class Word(_Model):
    id: str = Field(description="`<clip>.w<index>`, zero-based, stable for a given transcript.")
    text: str = Field(description="As transcribed, punctuation included.")
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    conf: float = Field(ge=0, le=1)
    filler: FillerKind | None = Field(
        default=None,
        description="hard: removed by default. soft: only marked; the host agent decides.",
    )
    utt: str = Field(description="ID of the utterance that holds this word.")


class Utterance(_Model):
    id: str = Field(description="`<clip>.s<index>`, zero-based.")
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    first_word: str
    last_word: str
    text: str
    complete: bool = Field(
        description="False when the speaker stops mid-sentence before a long pause or the clip "
        "end: usually an abandoned take."
    )


class Pause(_Model):
    """Silence between two consecutive words, or before the first or after the last word."""

    start: float = Field(ge=0)
    end: float = Field(ge=0)
    dur: float = Field(ge=0)
    after_word: str | None = Field(description="Word before the pause; null at the clip start.")


class FaceSample(_Model):
    """Largest face in one sampled frame, normalised 0-1 to the mezzanine frame."""

    t: float = Field(ge=0)
    cx: float
    cy: float
    w: float
    h: float
    score: float = Field(ge=0, le=1)


class Faces(_Model):
    sample_fps: float = Field(default=2, gt=0)
    samples: list[FaceSample] = Field(default_factory=lambda: list[FaceSample]())


class ClipAnalysis(_Model):
    """Everything reelcut knows about one clip: `analysis/<clip>.json`."""

    schema_version: Literal[1] = 1
    clip: ClipInfo
    language: LanguageGuess | None = Field(default=None, description="Null for silent clips.")
    words: list[Word] = Field(default_factory=lambda: list[Word]())
    utterances: list[Utterance] = Field(default_factory=lambda: list[Utterance]())
    pauses: list[Pause] = Field(default_factory=lambda: list[Pause]())
    unaligned_voice: list[Span] = Field(
        default_factory=lambda: list[Span](),
        description="Voice-activity regions >= 150 ms that overlap no word: likely mumbles, "
        "breaths or fillers the transcriber skipped. Cut them with EDL drop_ranges.",
    )
    vad: list[Span] = Field(default_factory=lambda: list[Span]())
    shots: list[Span] = Field(default_factory=lambda: list[Span]())
    static: list[Span] = Field(
        default_factory=lambda: list[Span](),
        description="Stretches >= 2 s with no speech and almost no motion.",
    )
    faces: Faces = Field(default_factory=Faces)


class RetakeCluster(_Model):
    id: str = Field(description="R1, R2, ... in order of the winner's position in the footage.")
    winner: str = Field(description="Utterance ID the draft keeps.")
    members: list[str] = Field(description="Utterance IDs, winner first, then in preference order.")
    similarity: dict[str, float] = Field(
        description="Each non-winning member's similarity (0-1) to the winner."
    )


class Retakes(_Model):
    """`analysis/retakes.json`: utterances, within and across A-roll clips, that say the same."""

    schema_version: Literal[1] = 1
    threshold: float = Field(ge=0, le=1)
    clusters: list[RetakeCluster] = Field(default_factory=lambda: list[RetakeCluster]())
