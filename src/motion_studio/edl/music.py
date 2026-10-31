"""Checks on the EDL's music block that need the rest of the EDL: where `align` lands."""

from motion_studio.config import Config
from motion_studio.edl.issues import Problems
from motion_studio.edl.models import Edl, ProductEdl


def check_music(edl: Edl, config: Config, problems: Problems) -> None:
    align = edl.music.align
    if align is None:
        return
    if not isinstance(edl, ProductEdl):
        problems.error(
            "align_kind",
            "music.align is for product EDLs: a talk bed starts under the speech",
            hint="remove music.align",
        )
        return
    mode = edl.music.mode or config.music.mode
    if mode != "generate":
        problems.error(
            "align_mode",
            f"music.align needs a generated bed, and the mode is {mode}",
            hint='set "mode": "generate", or remove music.align',
        )
    ids = [s.id for s in edl.scenes]
    if align.at not in ids:
        problems.error(
            "align_scene",
            f"music.align.at: no scene is called '{align.at}'",
            hint="use one of the scene IDs: " + ", ".join(ids),
        )
