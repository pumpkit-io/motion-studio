"""Text normalisation shared by filler matching, retake comparison and language data."""

import unicodedata

SENTENCE_END = ".!?"
TRAILING_OFF = ("…", "...")
# Closing quotes and brackets that may follow the sentence-final mark.
CLOSERS = "\"')]\u00bb\u201d\u2019"


def normalise_token(text: str) -> str:
    """Case-folded, with every punctuation character removed: `"Ehm,"` -> `"ehm"`."""
    composed = unicodedata.normalize("NFC", text)
    kept = (ch for ch in composed if not unicodedata.category(ch).startswith("P"))
    return "".join(kept).casefold().strip()


def strip_punctuation(text: str) -> str:
    """`text` without leading or trailing punctuation or spaces, case kept."""
    chars = list(unicodedata.normalize("NFC", text.strip()))
    while chars and unicodedata.category(chars[0]).startswith("P"):
        chars.pop(0)
    while chars and unicodedata.category(chars[-1]).startswith("P"):
        chars.pop()
    return "".join(chars)


def normalise_words(text: str) -> list[str]:
    """Whitespace-split tokens of `text`, each normalised, empty ones dropped."""
    return [t for t in (normalise_token(raw) for raw in text.split()) if t]


def ends_sentence(text: str) -> bool:
    """Whether a word closes a sentence; an ellipsis trails off instead."""
    stripped = text.rstrip().rstrip(CLOSERS)
    if stripped.endswith(TRAILING_OFF):
        return False
    return stripped.endswith(tuple(SENTENCE_END))


def trails_off(text: str) -> bool:
    return text.rstrip().rstrip(CLOSERS).endswith(TRAILING_OFF)
