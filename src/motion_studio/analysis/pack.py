"""The packed index (`analysis/packed.md`, guide §6.3): a whole project in a few thousand tokens."""

import statistics
from collections.abc import Sequence
from pathlib import PurePosixPath

from motion_studio.analysis.models import ClipAnalysis, Retakes, Utterance, Word
from motion_studio.text import strip_punctuation

LEGEND = (
    "Legend: {ehm#c1.w1}=hard filler (id) · ~tipo~=soft filler · ‖1.7s‖=pause ≥0.7s · "
    "⟂0.4s=unaligned voice · ✗=incomplete utterance"
)
PAUSE_MIN_S = 0.7
DASH = "\u2013"  # en dash between the two ends of a time range


def pack_project(title: str, language: str, clips: Sequence[ClipAnalysis], retakes: Retakes) -> str:
    """Render the packed index. Only A-roll gets utterance lines; assets are in assets.md."""
    aroll = [c for c in clips if c.clip.role == "aroll"]
    lines = [_header(title, language, clips, aroll), LEGEND]
    complete = {u.id: u.complete for c in aroll for u in c.utterances}

    for analysis in aroll:
        lines.append("")
        lines.append(_clip_heading(analysis, language))
        lines.extend(_utterance_lines(analysis))

    if retakes.clusters:
        lines.append("")
        lines.append(f"## Retake clusters (similarity ≥ {retakes.threshold:.2f}; winner first)")
        for cluster in retakes.clusters:
            others = ", ".join(
                f"{_mark(m, complete)} ({cluster.similarity[m]:.2f})" for m in cluster.members[1:]
            )
            winner = _mark(cluster.winner, complete)
            lines.append(f"- {cluster.id}: {winner} ≈ {others} → draft keeps {cluster.winner}")

    static = [(c.clip.id, s) for c in clips for s in c.static]
    if static:
        lines.append("")
        lines.append("## Static / no-speech stretches ≥ 2s")
        lines.extend(
            f"- {clip_id} [{_ts(s.start)}{DASH}{_ts(s.end)}] static, no speech"
            for clip_id, s in static
        )
    return "\n".join(lines) + "\n"


def _header(
    title: str, language: str, clips: Sequence[ClipAnalysis], aroll: Sequence[ClipAnalysis]
) -> str:
    speaking = [c.clip.id for c in aroll if c.language and c.language.code == language]
    speech_s = sum(u.end - u.start for c in aroll for u in c.utterances)
    broll = sum(1 for c in clips if c.clip.role == "broll")
    images = sum(1 for c in clips if c.clip.role == "image")
    return (
        f"# Project: {title} · language: {language} ({', '.join(speaking)}) · "
        f"A-roll {len(aroll)} clips, {_duration(speech_s)} speech · B-roll {broll} · "
        f"images {images}"
    )


def _clip_heading(analysis: ClipAnalysis, project_language: str) -> str:
    clip = analysis.clip
    parts = [clip.id, PurePosixPath(clip.source).name, _duration(clip.duration_s)]
    if clip.width and clip.height:
        parts.append(f"{clip.width}x{clip.height}")
    if analysis.language and analysis.language.code != project_language:
        parts.append(f"language {analysis.language.code}")
    samples = analysis.faces.samples
    if samples:
        cx = statistics.median(s.cx for s in samples)
        parts.append("face left" if cx < 0.4 else "face right" if cx > 0.6 else "face centred")
    return "## " + " · ".join(parts)


def _utterance_lines(analysis: ClipAnalysis) -> list[str]:
    after: dict[str | None, list[str]] = {}
    for pause in analysis.pauses:
        if pause.after_word is not None and pause.dur >= PAUSE_MIN_S:
            after.setdefault(pause.after_word, []).append(f"‖{pause.dur:.1f}s‖")
    for span in analysis.unaligned_voice:
        before = [w.id for w in analysis.words if w.start < span.start]
        after.setdefault(before[-1] if before else None, []).append(
            f"⟂{span.end - span.start:.1f}s"
        )

    by_utt: dict[str, list[Word]] = {}
    for word in analysis.words:
        by_utt.setdefault(word.utt, []).append(word)

    lines: list[str] = []
    for index, utterance in enumerate(analysis.utterances):
        tokens = after.get(None, []) if index == 0 else []
        tokens = [*tokens, *_tokens(by_utt.get(utterance.id, []), after)]
        lines.append(_utterance_line(utterance, tokens))
    return lines


def _utterance_line(utterance: Utterance, tokens: Sequence[str]) -> str:
    mark = "" if utterance.complete else "✗ "
    span = f"[{_ts(utterance.start)}{DASH}{_ts(utterance.end)}]"
    return f"{utterance.id}  {span} {mark}{' '.join(tokens)}"


def _tokens(words: Sequence[Word], after: dict[str | None, list[str]]) -> list[str]:
    tokens: list[str] = []
    soft_run: list[str] = []

    def flush() -> None:
        if soft_run:
            tokens.append(f"~{' '.join(soft_run)}~")
            soft_run.clear()

    for word in words:
        if word.filler == "soft":
            soft_run.append(strip_punctuation(word.text))
        else:
            flush()
            tokens.append(
                f"{{{strip_punctuation(word.text)}#{word.id}}}" if word.filler else word.text
            )
        if word.id in after:
            flush()
            tokens.extend(after[word.id])
    flush()
    return tokens


def _ts(seconds: float) -> str:
    tenths = round(seconds * 10)
    return f"{tenths // 600:02d}:{(tenths % 600) / 10:04.1f}"


def _duration(seconds: float) -> str:
    total = round(seconds)
    return f"{total}s" if total < 60 else f"{total // 60}m{total % 60:02d}s"


def _mark(utt_id: str, complete: dict[str, bool]) -> str:
    return utt_id if complete.get(utt_id, True) else f"{utt_id} ✗"
