"""The analysis contracts: `analysis/<clip>.json` (guide §6.1), `analysis/retakes.json`, and
the markers sidecar a recorder writes next to a screen recording in raw/.

Times are seconds in source time, measured from the start of the clip's mezzanine.
"""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

Role = Literal["aroll", "broll", "image", "screen"]
FillerKind = Literal["hard", "soft"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Span(_Model):
    """A stretch of source time."""

    start: float = Field(ge=0, description="Start, seconds.")
    end: float = Field(ge=0, description="End, seconds.")


class ClipInfo(_Model):
    id: str = Field(
        description="Stable short clip ID: c1 (A-roll or screen recording), b1 (B-roll), "
        "i1 (image)."
    )
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
    code: str = Field(
        description="Language code with a data file in motion-studio's lang directory."
    )
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


# Marker and element names become IDs such as `c2.m.v1_shown`, so they never hold a dot.
NAME_PATTERN = r"^[A-Za-z0-9_][A-Za-z0-9_-]*$"


class Element(_Model):
    """A named on-screen box at one marker, in the pixels of the frame the sidecar declares."""

    name: str = Field(pattern=NAME_PATTERN, description="Addressed as `<clip>.e.<name>`.")
    x: float = Field(description="Left edge, pixels from the frame's left.")
    y: float = Field(description="Top edge, pixels from the frame's top.")
    w: float = Field(gt=0)
    h: float = Field(gt=0)


class Marker(_Model):
    """A named moment on the clip's clock, with the boxes of the elements captured then."""

    name: str = Field(pattern=NAME_PATTERN, description="Addressed as `<clip>.m.<name>`.")
    t: float = Field(ge=0, description="Seconds from the clip's first frame.")
    elements: list[Element] = Field(default_factory=lambda: list[Element]())

    @model_validator(mode="after")
    def _unique_elements(self) -> Self:
        names = [e.name for e in self.elements]
        twice = sorted({n for n in names if names.count(n) > 1})
        if twice:
            raise ValueError(f"marker {self.name!r} lists element {', '.join(twice)} twice")
        return self


class CursorSample(_Model):
    """Where the recorder's cursor was, in the same pixels as the element boxes."""

    t: float = Field(ge=0)
    x: float
    y: float
    down: bool = Field(default=False, description="True while the button is pressed.")


class ScreenMarkers(_Model):
    """The markers sidecar: `raw/<name>.markers.json` next to `raw/<name>.<ext>`.

    The recorders write it; it can also be written by hand for footage brought in.
    """

    schema_version: Literal[1] = 1
    width: int = Field(gt=0, description="Width of the recorded frame the boxes are in.")
    height: int = Field(gt=0, description="Height of the recorded frame the boxes are in.")
    markers: list[Marker] = Field(default_factory=lambda: list[Marker]())
    cursor: list[CursorSample] = Field(default_factory=lambda: list[CursorSample]())

    @model_validator(mode="after")
    def _unique_markers(self) -> Self:
        names = [m.name for m in self.markers]
        twice = sorted({n for n in names if names.count(n) > 1})
        if twice:
            raise ValueError(f"marker {', '.join(twice)} appears twice")
        return self


class ClipAnalysis(_Model):
    """Everything motion-studio knows about one clip: `analysis/<clip>.json`."""

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
    markers_source: str | None = Field(
        default=None,
        description="The screen recording's markers sidecar, relative to the project; null "
        "when it has none and can only be addressed in source seconds.",
    )
    markers: list[Marker] = Field(
        default_factory=lambda: list[Marker](),
        description="From the sidecar, in time order, with boxes scaled to the mezzanine's pixels.",
    )
    cursor: list[CursorSample] = Field(
        default_factory=lambda: list[CursorSample](),
        description="The recorded cursor track, in the mezzanine's pixels.",
    )


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
