"""`motion-studio words`: word IDs and source times for a range, to trim at exact words."""

from typing import Annotated

import typer

from motion_studio.analysis import Word
from motion_studio.cli._output import JsonOption, emit
from motion_studio.cli.workspace import Slug
from motion_studio.paths import find_workspace
from motion_studio.plan import word_range

MAX_LINES = 30
WORDS_PER_LINE = 5


def words(
    slug: Slug,
    start: Annotated[str, typer.Argument(help="First word or utterance ID, e.g. c1.s4.")],
    end: Annotated[
        str | None, typer.Argument(help="Last word or utterance ID; default: same as start.")
    ] = None,
    as_json: JsonOption = False,
) -> None:
    """Print the words from START to END with their IDs, source times and filler marks."""
    found, utterances = word_range(find_workspace(), slug, start, end)
    body: list[tuple[str, int]] = []
    for u in utterances:
        body.append((f"{u.id}{' ✗' if not u.complete else ''} [{u.start:.2f}-{u.end:.2f}]", 0))
        mine = [w for w in found if w.utt == u.id]
        for i in range(0, len(mine), WORDS_PER_LINE):
            chunk = mine[i : i + WORDS_PER_LINE]
            body.append(("  " + "  ".join(_token(w) for w in chunk), len(chunk)))
    header = f"{found[0].id} to {found[-1].id}: {len(found)} words, source seconds"
    if len(body) > MAX_LINES - 1:
        body = body[: MAX_LINES - 2]
        hidden = len(found) - sum(n for _, n in body)
        body.append((f"… {hidden} more words; narrow the range, or pass --json for all", 0))
    emit(
        as_json,
        {"words": [w.model_dump() for w in found]},
        [header, *(line for line, _ in body)],
    )


def _token(word: Word) -> str:
    text = {"hard": f"{{{word.text}}}", "soft": f"~{word.text}~"}.get(word.filler or "", word.text)
    return f"{word.id} {text} {word.start:.2f}-{word.end:.2f}"


def register(app: typer.Typer) -> None:
    app.command()(words)
