"""The EDL (`edl.json`, guide §6.4) and timeline (`build/timeline.json`, guide §6.5) contracts.

The field descriptions become the JSON Schema the host agent reads, so they explain semantics.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from motion_studio.config import Format, HexColor
from motion_studio.edl.issues import EdlError, Issue


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


Ref = Annotated[
    str,
    Field(
        description="A word ID (c1.w52), an utterance ID (c1.s4) or, for event anchors, "
        "a segment ID (hook)."
    ),
]


class Policy(_Model):
    """Trimming rules for this EDL. Every key is optional and overrides the config's [edit]."""

    pad_in_ms: int | None = Field(default=None, ge=0, description="Kept before a run's first word.")
    pad_out_ms: int | None = Field(default=None, ge=0, description="Kept after a run's last word.")
    max_pause_ms: int | None = Field(
        default=None, ge=0, description="Longer pauses between kept words are cut down to this."
    )
    min_segment_ms: int | None = Field(
        default=None, ge=0, description="Shorter runs are dropped, with a warning."
    )
    drop_fillers: Literal["none", "hard", "hard+soft"] | None = Field(
        default=None, description="Which tagged fillers are removed automatically."
    )
    jumpcut_punch: bool | None = Field(
        default=None, description="Alternate the base zoom at jump cuts so they read as deliberate."
    )
    jumpcut_punch_scale: float | None = Field(
        default=None, ge=1, description="Scale of the punched-in runs."
    )


class Segment(_Model):
    """A range of words from one clip. Segment order is output order."""

    id: str = Field(description="Unique name, usable as an event anchor: hook, body1, cta.")
    from_: Ref = Field(
        alias="from",
        description="First word kept: a word ID, or an utterance ID meaning its first word.",
    )
    to: Ref = Field(
        description="Last word kept: a word ID, or an utterance ID meaning its last word."
    )
    note: str | None = None


class DropRange(_Model):
    """Source time to cut out, for audio no word points at (unaligned voice)."""

    clip: str
    start: float = Field(ge=0, description="Source seconds.")
    end: float = Field(ge=0, description="Source seconds.")


class ZoomEvent(_Model):
    type: Literal["zoom"]
    at: Ref = Field(description="Zoom starts at the start of this anchor.")
    scale: float = Field(default=1.15, ge=1)
    hold_until: Ref | None = Field(
        default=None, description="Zoom holds until the end of this anchor; default: end of `at`."
    )
    ease: Literal["snap", "smooth"] = "snap"


class PushEvent(_Model):
    type: Literal["push"]
    from_: str = Field(
        alias="from", description="Segment ID; the push-in runs across the whole segment."
    )
    scale: float = Field(default=1.06, ge=1, description="Scale reached at the segment's end.")


class BrollEvent(_Model):
    type: Literal["broll"]
    asset: str = Field(description="B-roll clip ID: b1.")
    start: Ref = Field(description="Shown from the start of this anchor.")
    end: Ref = Field(description="Shown until the end of this anchor.")
    asset_in_s: float = Field(default=0, ge=0, description="Where in the B-roll clip to start.")
    mode: Literal["full", "pip"] = Field(
        default="full", description="full: full-frame cutaway. pip: card over the speaker."
    )


class ImageEvent(_Model):
    type: Literal["image"]
    asset: str = Field(description="Image clip ID: i1.")
    start: Ref
    end: Ref
    mode: Literal["full", "pip"] = "full"
    motion: Literal["kenburns", "none"] = "kenburns"


class TitleEvent(_Model):
    type: Literal["title"]
    text: str = Field(min_length=1)
    start: Ref
    end: Ref


class EmphasisEvent(_Model):
    type: Literal["emphasis"]
    words: list[str] = Field(min_length=1, description="Word IDs drawn in the accent colour.")


Event = Annotated[
    ZoomEvent | PushEvent | BrollEvent | ImageEvent | TitleEvent | EmphasisEvent,
    Field(discriminator="type"),
]


class EdlCaptions(_Model):
    """Overrides of the config's [captions] for this video."""

    enabled: bool | None = None
    style: Literal["pop", "clean", "karaoke"] | None = None
    max_words_per_page: int | None = Field(default=None, ge=1)
    uppercase: bool | None = None
    hide_during_broll: bool | None = Field(
        default=None,
        description="Hide captions while a full-frame B-roll clip or image is on screen.",
    )


class EdlMusic(_Model):
    """The music bed. Unset keys fall back to the config's [music]."""

    mode: Literal["generate", "library", "none"] | None = None
    prompt: str | None = Field(default=None, description="Mood prompt for generation.")
    bpm: int | None = Field(default=None, gt=0)
    seed: int | None = None
    gain_db: float | None = None
    track: str | None = Field(default=None, description="Library track, for mode library.")


class Edl(_Model):
    """The edit: which words to keep, in which order, and what to layer on top."""

    schema_version: Literal[1] = 1
    title: str = ""
    language: str | None = Field(default=None, description="Caption language; default: project's.")
    formats: list[Format] | None = Field(default=None, description="Default: config formats.")
    max_duration_s: float | None = Field(default=None, gt=0)
    policy: Policy = Field(default_factory=Policy)
    segments: list[Segment] = Field(min_length=1)
    drop_words: list[str] = Field(
        default_factory=lambda: list[str](), description="Word IDs cut out of their segments."
    )
    drop_ranges: list[DropRange] = Field(default_factory=lambda: list[DropRange]())
    keep_words: list[str] = Field(
        default_factory=lambda: list[str](),
        description="Word IDs kept although the policy drops them as fillers.",
    )
    events: list[Event] = Field(default_factory=lambda: list[Event]())
    captions: EdlCaptions = Field(default_factory=EdlCaptions)
    music: EdlMusic = Field(default_factory=EdlMusic)
    rationale: str = ""


def parse_edl(data: object) -> Edl:
    """Validate decoded edl.json. Schema errors become an EdlError naming each field."""
    try:
        return Edl.model_validate(data)
    except ValidationError as exc:
        raise EdlError(
            Issue(
                code="invalid_edl",
                message=f"{'.'.join(str(part) for part in err['loc']) or 'edl'}: {err['msg']}",
                hint="`motion-studio docs edl` prints the EDL reference",
            )
            for err in exc.errors()
        ) from exc


# Timeline: what the renderer reads. Frames are output frames at `fps`; end frames are exclusive.


class _Out(BaseModel):
    # The resolver writes every field, so the renderer's types mark defaults as present.
    model_config = ConfigDict(extra="forbid", json_schema_serialization_defaults_required=True)


class SafeZone(_Out):
    """Fractions of the frame kept clear of platform UI on each side."""

    top: float
    right: float
    bottom: float
    left: float


class FormatSpec(_Out):
    name: Format
    width: int
    height: int
    safe_zone: SafeZone


class Crop(_Out):
    cx: float = Field(description="Face centre x, 0-1 of the mezzanine frame.")
    cy: float = Field(description="Face centre y, 0-1 of the mezzanine frame.")


class Run(_Out):
    """A continuous stretch of one clip. Runs follow each other with no gap in output time."""

    segment: str
    clip: str
    src_in_s: float = Field(description="Source seconds, on the frame grid.")
    src_out_s: float
    out_in: int = Field(description="First output frame.")
    out_out: int = Field(description="Output frame after the last one.")
    crop: Crop
    face: bool = Field(description="False when no face was seen; crop is then the frame centre.")
    base_scale: float = Field(
        description="1.0, or the jump-cut punch scale. A zoom event replaces it while active."
    )


class TimelineBrand(_Out):
    primary: HexColor
    accent: HexColor
    logo: str = Field(description="Relative to the workspace.")


class TimelineWord(_Out):
    id: str
    text: str
    start_ms: int = Field(description="Output time.")
    end_ms: int
    emphasis: bool = False


class TimelineZoom(_Out):
    type: Literal["zoom"]
    start: int
    end: int
    scale: float
    ease: Literal["snap", "smooth"]


class TimelinePush(_Out):
    type: Literal["push"]
    start: int
    end: int
    scale: float = Field(description="Linear from 1.0 at start to this at end.")


class TimelineBroll(_Out):
    type: Literal["broll"]
    asset: str
    src: str = Field(description="Asset file, relative to the project.")
    start: int
    end: int
    asset_in_s: float
    mode: Literal["full", "pip"]


class TimelineImage(_Out):
    type: Literal["image"]
    asset: str
    src: str
    start: int
    end: int
    mode: Literal["full", "pip"]
    motion: Literal["kenburns", "none"]


class TimelineTitle(_Out):
    type: Literal["title"]
    text: str
    start: int
    end: int


TimelineEvent = Annotated[
    TimelineZoom | TimelinePush | TimelineBroll | TimelineImage | TimelineTitle,
    Field(discriminator="type"),
]


class TimelineCaptions(_Out):
    enabled: bool
    style: Literal["pop", "clean", "karaoke"]
    font: str
    max_words_per_page: int
    uppercase: bool
    hide_during_broll: bool = Field(
        description="Hide captions while a full-frame B-roll clip or image is on screen."
    )
    highlight_color: HexColor
    text_color: HexColor
    stroke_color: HexColor
    max_chars_per_page: int | None = Field(
        default=None, description="From the language's caption rules."
    )
    keep_with_next: list[str] = Field(
        default_factory=lambda: list[str](), description="Words that never end a caption page."
    )


class Timeline(_Out):
    """The resolved edit: `build/timeline.json`, the renderer's props."""

    schema_version: Literal[1] = 1
    title: str
    language: str | None
    fps: int
    duration_frames: int
    formats: list[FormatSpec]
    runs: list[Run]
    words: list[TimelineWord] = Field(description="Kept words in output order.")
    events: list[TimelineEvent] = Field(description="Overlays and camera moves, by start frame.")
    captions: TimelineCaptions
    brand: TimelineBrand
    music_path: str | None = Field(description="Music bed relative to the project; null for none.")
