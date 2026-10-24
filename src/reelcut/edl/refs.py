"""Parse and resolve EDL references: word IDs, utterance IDs and segment IDs (guide §6.4)."""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from reelcut.analysis import ClipAnalysis
from reelcut.edl.issues import Problems
from reelcut.edl.models import DropRange, Segment

_REF = re.compile(r"^(?P<clip>[a-z]+\d+)\.(?P<kind>[ws])(?P<index>\d+)$")


@dataclass(frozen=True)
class ParsedRef:
    clip: str
    kind: str
    index: int


def parse_ref(text: str) -> ParsedRef | None:
    """`c1.w52` or `c1.s4`; None for anything else (a segment ID, or a typo)."""
    match = _REF.match(text)
    if match is None:
        return None
    return ParsedRef(match["clip"], match["kind"], int(match["index"]))


@dataclass(frozen=True)
class WordSpan:
    """Words `first..last` (inclusive indices) of one clip."""

    clip: str
    first: int
    last: int


_IDS_HINT = "utterance IDs are in analysis/packed.md; `reelcut words` lists word IDs"


class RefIndex:
    """Looks up references in a project's analyses."""

    def __init__(self, clips: Sequence[ClipAnalysis]) -> None:
        self.clips = {c.clip.id: c for c in clips}

    def aroll(self) -> list[ClipAnalysis]:
        return [c for c in self.clips.values() if c.clip.role == "aroll"]

    def segment_spans(
        self, segments: Sequence[Segment], problems: Problems
    ) -> list[WordSpan | None]:
        """Each segment's word range, or None where it has an error (recorded in `problems`)."""
        seen: set[str] = set()
        for segment in segments:
            if segment.id in seen:
                problems.error("duplicate_segment", f"segment id '{segment.id}' is used twice")
            seen.add(segment.id)
            if parse_ref(segment.id) is not None:
                problems.error(
                    "bad_segment_id", f"segment id '{segment.id}' looks like a word or utterance ID"
                )
        spans = [self._segment_span(segment, problems) for segment in segments]
        for i, (a, span_a) in enumerate(zip(segments, spans, strict=True)):
            for b, span_b in zip(segments[i + 1 :], spans[i + 1 :], strict=True):
                if span_a is None or span_b is None or span_a.clip != span_b.clip:
                    continue
                lo, hi = max(span_a.first, span_b.first), min(span_a.last, span_b.last)
                if lo <= hi:
                    problems.error(
                        "overlapping_segments",
                        f"segments {a.id} and {b.id} both keep "
                        f"{span_a.clip}.w{lo} to {span_a.clip}.w{hi}",
                        hint="a word can appear only once in the output; trim one segment",
                    )
        return spans

    def _segment_span(self, segment: Segment, problems: Problems) -> WordSpan | None:
        where = f"segment {segment.id}"
        first = self.word_index(segment.from_, where, problems, end="first")
        last = self.word_index(segment.to, where, problems, end="last")
        if first is None or last is None:
            return None
        if first[0] != last[0]:
            problems.error(
                "cross_clip",
                f"{where} goes from {first[0]} to {last[0]}; from and to must be in the same clip",
                hint="split it into one segment per clip",
            )
            return None
        if first[1] > last[1]:
            problems.error(
                "reversed_range",
                f"{where}: from {_show(segment.from_, first)} comes after "
                f"to {_show(segment.to, last)}",
                hint="swap from and to, or reorder segments to change the output order",
            )
            return None
        return WordSpan(first[0], first[1], last[1])

    def word_list(
        self, refs: Sequence[str], field: str, problems: Problems
    ) -> set[tuple[str, int]]:
        """Resolve a list that takes only word IDs, such as drop_words."""
        found: set[tuple[str, int]] = set()
        for ref in refs:
            parsed = parse_ref(ref)
            if parsed is not None and parsed.kind == "s":
                tail = ", or leave it out of the segments" if field == "drop_words" else ""
                problems.error("bad_ref", f"{field}: {ref} is an utterance; list its words{tail}")
                continue
            target = self.word_index(ref, field, problems)
            if target is not None:
                found.add(target)
        return found

    def check_ranges(self, ranges: Sequence[DropRange], problems: Problems) -> None:
        for r in ranges:
            if r.clip not in self.clips:
                aroll = ", ".join(c.clip.id for c in self.aroll()) or "none"
                problems.error(
                    "unknown_ref",
                    f"drop_ranges: clip {r.clip} does not exist; A-roll clips: {aroll}",
                )
            elif r.end <= r.start:
                problems.error(
                    "bad_drop_range",
                    f"drop_ranges: {r.clip} {r.start:.3f}-{r.end:.3f} s ends before it starts",
                )

    def word_index(
        self, ref: str, where: str, problems: Problems, *, end: str = "first"
    ) -> tuple[str, int] | None:
        """The clip and word index a word or utterance ID points at.

        An utterance means its first word, or its last word when `end` is "last".
        """
        parsed = parse_ref(ref)
        if parsed is None:
            problems.error(
                "bad_ref",
                f"{where}: '{ref}' is not a word ID (c1.w52) or an utterance ID (c1.s4)",
                hint=_IDS_HINT,
            )
            return None
        analysis = self._clip_with_words(parsed.clip, where, problems)
        if analysis is None:
            return None
        if parsed.kind == "w":
            count = len(analysis.words)
            if parsed.index >= count:
                self._missing(ref, f"w0-w{count - 1}", where, problems)
                return None
            return parsed.clip, parsed.index
        count = len(analysis.utterances)
        if parsed.index >= count:
            self._missing(ref, f"s0-s{count - 1}", where, problems)
            return None
        utterance = analysis.utterances[parsed.index]
        word = parse_ref(utterance.first_word if end == "first" else utterance.last_word)
        assert word is not None
        return parsed.clip, word.index

    def _clip_with_words(self, clip_id: str, where: str, problems: Problems) -> ClipAnalysis | None:
        analysis = self.clips.get(clip_id)
        aroll = ", ".join(c.clip.id for c in self.aroll() if c.words) or "none"
        if analysis is None:
            problems.error(
                "unknown_ref", f"{where}: clip {clip_id} does not exist; A-roll clips: {aroll}"
            )
            return None
        if not analysis.words:
            role = "" if analysis.clip.role == "aroll" else f" is {analysis.clip.role} and"
            problems.error(
                "unknown_ref", f"{where}: {clip_id}{role} has no words; A-roll clips: {aroll}"
            )
            return None
        return analysis

    def _missing(self, ref: str, available: str, where: str, problems: Problems) -> None:
        clip_id = ref.split(".")[0]
        problems.error(
            "unknown_ref",
            f"{where}: {ref} does not exist; {clip_id} has {available}",
            hint=_IDS_HINT,
        )


def _show(ref: str, target: tuple[str, int]) -> str:
    word = f"{target[0]}.w{target[1]}"
    return ref if ref == word else f"{ref} ({word})"
