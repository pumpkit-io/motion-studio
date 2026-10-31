"""Named starting points for the music prompt, with a tempo where the style has one."""

from dataclasses import dataclass

from motion_studio.edl.models import MusicPreset


@dataclass(frozen=True)
class Preset:
    prompt: str
    bpm: int | None = None


PRESETS: dict[MusicPreset, Preset] = {
    "tech": Preset(
        "minimal electronic, warm analog synths, soft punchy drums, confident, optimistic, "
        "instrumental"
    ),
    "story": Preset(
        "lo-fi piano, gentle vinyl texture, soft brushes, warm, reflective, instrumental"
    ),
    "energetic": Preset(
        "upbeat indie electronic, plucky synths, driving four-on-the-floor, energetic, instrumental"
    ),
    "explainer": Preset("ambient cinematic pads, subtle pulse, focused, calm, instrumental"),
    # The Pumpkit launch video's bed: a clear build into a drop that a logo can land on.
    "launch": Preset(
        "fast future house, punchy claps, 16th-note hats, bright lead synth, rising build, "
        "big drop, energetic, instrumental",
        bpm=124,
    ),
}
