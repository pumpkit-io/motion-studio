"""The asset catalogue (`analysis/assets.md`), driven through `pack_assets`."""

from reelcut.analysis import ClipAnalysis, ClipInfo, Span, pack_assets, read_descriptions


def asset(clip_id: str, role: str, source: str, **info: float | int) -> ClipAnalysis:
    clip = ClipInfo(id=clip_id, role=role, source=source, **info)  # pyright: ignore[reportArgumentType]
    return ClipAnalysis(clip=clip)


BROLL = asset("b1", "broll", "raw/street walk.mp4", duration_s=6.0, width=1920, height=1080)
IMAGE = asset("i1", "image", "raw/logo.png", duration_s=0.0, width=1600, height=1200)
AROLL = asset("c1", "aroll", "raw/take.mov", duration_s=20.0, width=1080, height=1920)
SHEETS = {"b1": "contact/b1.png", "i1": "contact/i1.png"}


def test_each_asset_gets_its_id_file_duration_resolution_shots_and_a_blank_description() -> None:
    broll = BROLL.model_copy(update={"shots": [Span(start=0.0, end=2.5), Span(start=2.5, end=6.0)]})

    text = pack_assets("demo", [AROLL, broll, IMAGE], descriptions={}, sheets=SHEETS)

    assert text == (
        "# Assets: demo · B-roll 1 · images 1\n"
        "Write one line after `description:` for each asset once you have viewed its contact "
        "sheet; analyze keeps what you write.\n"
        "\n"
        "## b1 · street walk.mp4\n"
        "- file: raw/street walk.mp4 · 6.0s · 1920x1080 · 2 shots\n"
        "- contact sheet: contact/b1.png\n"
        "- description:\n"
        "\n"
        "## i1 · logo.png\n"
        "- file: raw/logo.png · still image · 1600x1200 · 1 shot\n"
        "- contact sheet: contact/i1.png\n"
        "- description:\n"
    )


def test_descriptions_written_into_the_catalogue_survive_a_repack() -> None:
    first = pack_assets("demo", [BROLL, IMAGE], descriptions={}, sheets=SHEETS)
    edited = first.replace(
        "- description:\n", "- description: Hands typing on a laptop, top-down.\n", 1
    )

    kept = read_descriptions(edited)
    again = pack_assets("demo", [BROLL, IMAGE], descriptions=kept, sheets=SHEETS)

    assert kept == {"b1": "Hands typing on a laptop, top-down."}
    assert again == edited


def test_a_project_without_assets_says_so() -> None:
    text = pack_assets("demo", [AROLL], descriptions={}, sheets={})

    assert text.splitlines()[0] == "# Assets: demo · B-roll 0 · images 0"
    assert "No B-roll or images in this project." in text
