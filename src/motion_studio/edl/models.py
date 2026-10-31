"""The EDL (`edl.json`, guide §6.4) and timeline (`build/timeline.json`, guide §6.5) contracts.

The field descriptions become the JSON Schema the host agent reads, so they explain semantics.
"""

from typing import Annotated, Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Discriminator, Field, Tag, TypeAdapter, ValidationError

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


MusicPreset = Literal["tech", "story", "energetic", "explainer", "launch"]
MusicHitName = Literal["intro_end", "build", "drop", "ending"]


class MusicAlign(_Model):
    """Land one of the bed's section hits on the start of a scene (product EDLs)."""

    hit: MusicHitName
    at: str = Field(description="The scene ID the hit lands on.")


class EdlMusic(_Model):
    """The music bed. Unset keys fall back to the config's [music]."""

    mode: Literal["generate", "library", "none"] | None = None
    preset: MusicPreset | None = Field(
        default=None, description="A named prompt and tempo; prompt and bpm override it."
    )
    prompt: str | None = Field(default=None, description="Mood prompt for generation.")
    bpm: int | None = Field(default=None, gt=0)
    seed: int | None = None
    gain_db: float | None = None
    track: str | None = Field(default=None, description="Library track, for mode library.")
    align: MusicAlign | None = Field(
        default=None, description="A section hit to land on a scene start, for generated beds."
    )


class TalkEdl(_Model):
    """A talk edit: which words to keep, in which order, and what to layer on top."""

    schema_version: Literal[1] = 1
    kind: Literal["talk"] = Field(
        default="talk", description="The project kind; an EDL without one is a talk EDL."
    )
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


# Product EDLs (ADR 0005): scenes in output order, footage addressed by marker.

MarkerRef = Annotated[
    str,
    Field(description="A marker of a screen recording: `<clip>.m.<name>`, such as c2.m.v1_shown."),
]


class MarkerPoint(_Model):
    """A marker nudged by an offset, in seconds or in beats of the music's grid."""

    marker: MarkerRef
    offset_s: float | None = Field(
        default=None, description="Seconds after the marker; negative is before."
    )
    offset_beats: float | None = Field(
        default=None, description="Beats after the marker on the music's grid; negative is before."
    )


FootagePoint = Annotated[
    MarkerRef | MarkerPoint | float,
    Field(
        description="A marker ID, a marker with an offset, or source seconds (only for a clip "
        "without markers)."
    ),
]


class _Scene(_Model):
    id: str = Field(description="Unique name: intro, step1, demo.")
    beats: float | None = Field(default=None, gt=0, description="Length in beats of the grid.")
    bars: float | None = Field(default=None, gt=0, description="Length in bars of the grid.")
    seconds: float | None = Field(default=None, gt=0, description="Length in seconds.")
    note: str | None = None


class TitleCardScene(_Scene):
    """A full-frame card that introduces a step of the story."""

    type: Literal["title_card"]
    step: str | None = Field(default=None, description='Step number shown above, such as "01".')
    headline: str = Field(min_length=1)
    accent: list[str] = Field(
        default_factory=lambda: list[str](),
        description="Words of the headline drawn in the brand accent colour.",
    )
    subline: str | None = Field(default=None, description="A smaller line under the headline.")


class FootageScene(_Scene):
    """A stretch of one screen recording, played in a device frame.

    Its length is `from` to `to` at `rate`, rounded to whole beats, unless a length is given;
    then `from` to `to` is played to fill it and `rate` must be left out.
    """

    type: Literal["footage"]
    clip: str = Field(description="Screen recording ID: c1.")
    from_: FootagePoint = Field(alias="from", description="Where the footage starts.")
    to: FootagePoint = Field(description="Where the footage ends.")
    rate: float | None = Field(
        default=None, gt=0, description="Playback speed; default 1. Typing reads well at 2.6-3.2."
    )
    device_frame: Literal["browser"] = Field(
        default="browser", description="The frame drawn around the footage."
    )
    address: str | None = Field(
        default=None, description="Text in the browser frame's address bar, such as example.com."
    )


Scene = Annotated[TitleCardScene | FootageScene, Field(discriminator="type")]


class ProductEdl(_Model):
    """A product video: scenes in output order, with the talk EDL's top-level fields (ADR 0004)."""

    schema_version: Literal[1] = 1
    kind: Literal["product"]
    title: str = ""
    language: str | None = Field(default=None, description="Caption language; default: project's.")
    formats: list[Format] | None = Field(
        default=None, description="Product videos render in 16x9 only, the default."
    )
    max_duration_s: float | None = Field(default=None, gt=0)
    scenes: list[Scene] = Field(min_length=1, description="In output order.")
    captions: EdlCaptions = Field(default_factory=EdlCaptions)
    music: EdlMusic = Field(default_factory=EdlMusic)
    rationale: str = ""


def _edl_kind(value: Any) -> str:
    if isinstance(value, dict):
        return str(cast(dict[str, Any], value).get("kind", "talk"))
    return str(getattr(value, "kind", "talk"))


Edl = Annotated[
    Annotated[TalkEdl, Tag("talk")] | Annotated[ProductEdl, Tag("product")],
    Discriminator(
        _edl_kind,
        custom_error_type="invalid_kind",
        custom_error_message="kind must be talk or product",
    ),
]
EDL_ADAPTER: TypeAdapter[Edl] = TypeAdapter(Edl)


def parse_edl(data: object) -> Edl:
    """Validate decoded edl.json. Schema errors become an EdlError naming each field."""
    try:
        return EDL_ADAPTER.validate_python(data)
    except ValidationError as exc:
        raise EdlError(
            Issue(
                code="invalid_edl",
                message=f"{_field_path(err['loc']) or 'edl'}: {err['msg']}",
                hint="`motion-studio docs edl` prints the EDL reference",
            )
            for err in exc.errors()
        ) from exc


def _field_path(loc: tuple[int | str, ...]) -> str:
    # The union puts the kind's tag first, which is no field of edl.json.
    parts = loc[1:] if loc and loc[0] in ("talk", "product") else loc
    return ".".join(str(part) for part in parts)


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


class TimelineHeadlineWord(_Out):
    text: str
    accent: bool = Field(description="Drawn in the brand accent colour.")


class TimelineTitleCard(_Out):
    type: Literal["title_card"]
    id: str
    start: int = Field(description="First output frame.")
    end: int = Field(description="Output frame after the last one.")
    step: str | None
    headline: list[TimelineHeadlineWord]
    subline: str | None


class TimelineFootage(_Out):
    type: Literal["footage"]
    id: str
    start: int
    end: int
    clip: str
    src: str = Field(description="The recording's mezzanine, relative to the project.")
    width: int = Field(description="Pixel width of the footage.")
    height: int = Field(description="Pixel height of the footage.")
    src_in_s: float = Field(description="Source seconds of the scene's first frame.")
    src_out_s: float = Field(description="Source seconds where the scene ends.")
    rate: float = Field(description="Playback speed that fits src_in_s to src_out_s in the scene.")
    device_frame: Literal["browser"]
    address: str | None


TimelineScene = Annotated[TimelineTitleCard | TimelineFootage, Field(discriminator="type")]


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
    kind: Literal["talk", "product"] = Field(
        default="talk", description="talk: runs of A-roll. product: scenes, and no runs."
    )
    title: str
    language: str | None
    fps: int
    duration_frames: int
    formats: list[FormatSpec]
    runs: list[Run]
    words: list[TimelineWord] = Field(description="Kept words in output order.")
    events: list[TimelineEvent] = Field(description="Overlays and camera moves, by start frame.")
    scenes: list[TimelineScene] = Field(
        default_factory=lambda: list[TimelineScene](),
        description="Product videos: scenes back to back in output order.",
    )
    captions: TimelineCaptions
    brand: TimelineBrand
    music_path: str | None = Field(description="Music bed relative to the project; null for none.")
