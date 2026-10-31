"""`motion-studio check`: judge a render and say what to change in the EDL when it cannot ship.

A talk render is re-transcribed and its cuts diffed; a product render, which has no speech, is
measured and its masks and highlights read off the timeline instead.
"""

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from motion_studio import APP_NAME, lang
from motion_studio.analysis.models import ClipAnalysis, Word
from motion_studio.asr import SpeechJob, resolve_backend, transcribe_clips
from motion_studio.check.diff import CLIP_WINDOW_MS, Miss, WordDiff, diff_words
from motion_studio.check.measure import Measurement, Stretch, measure
from motion_studio.check.product import (
    cursor_findings,
    longest_middle_scenes,
    masked_regions,
    still_scenes,
)
from motion_studio.check.report import Finding, Severity, markdown, verdict
from motion_studio.check.stills import Cut, contact_sheet, cuts_sheet
from motion_studio.config import Config, Edit, load_config
from motion_studio.edl import Timeline
from motion_studio.edl.models import ProductEdl, TalkEdl, TimelineBroll, TimelineImage
from motion_studio.errors import MotionStudioError, UserError
from motion_studio.media.ffmpeg import run_ffmpeg
from motion_studio.paths import ProjectPaths, project_paths
from motion_studio.plan import load_analyses, load_edl, timeline_path
from motion_studio.render import output_path, voice_path
from motion_studio.render.assemble import video_size
from motion_studio.state import (
    load_state,
    mark_done,
    mark_failed,
    project_lock,
    stage_status,
)
from motion_studio.target import RenderTarget

# Guide §8 phase 9: more words per second than this on screen is hard to read.
MAX_WORDS_PER_S = 4.5
DENSITY_WINDOW_MS = 2000
LOUDNESS_TOLERANCE_LU = 1.0
# A preview only warns past this; a final blocks anything over the limit once rounded to 0.1 dB.
TRUE_PEAK_TOLERANCE_DB = 0.5
FINAL_TRUE_PEAK_TOLERANCE_DB = 0.05
# A detected stretch mostly inside an image segment is the still image, not a defect.
INTENTIONAL_SHARE = 0.5
# Laptop and phone speakers barely reproduce the bass, so a mix this bass-heavy sounds empty.
SMALL_SPEAKER_DB = 10.0
# Bass this far under the loudest band is too faint to mask anything, whatever the top does.
AUDIBLE_BASS_DB = 30.0


@dataclass
class CheckReport:
    stage: str
    formats: list[str]
    findings: list[Finding]
    metrics: dict[str, Any]
    cuts_s: list[float]
    report: Path
    report_json: Path
    cuts_sheet: Path
    contact_sheet: Path | None = None
    warnings: list[str] = field(default_factory=lambda: list[str]())

    @property
    def blocked(self) -> bool:
        return any(f.severity == "blocking" for f in self.findings)

    def to_json(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "verdict": "blocked" if self.blocked else "pass",
            "summary": verdict(self.findings),
            "formats": self.formats,
            "issues": [f.to_json() for f in self.findings],
            "metrics": self.metrics,
            "cuts_s": self.cuts_s,
            "report": str(self.report),
            "report_json": str(self.report_json),
            "cuts_sheet": str(self.cuts_sheet),
            "contact_sheet": str(self.contact_sheet) if self.contact_sheet else None,
            "warnings": self.warnings,
        }


def check_project(
    workspace: Path,
    slug: str,
    *,
    target: RenderTarget,
    on_step: Callable[[str], None] | None = None,
    on_warning: Callable[[str], None] | None = None,
) -> CheckReport:
    step = on_step or (lambda _msg: None)
    warn = on_warning or (lambda _msg: None)
    project = project_paths(workspace, slug).require()
    stage = target.stage
    status = stage_status(project, stage)
    if status != "done":
        state = {"pending": "not rendered yet", "stale": "out of date", "failed": "failed"}
        raise UserError(
            f"the {stage} render is {state[status]}",
            hint=f"run `{APP_NAME} render {slug} {target.flag}` first",
        )
    record = target.check_record
    with project_lock(project):
        timeline = Timeline.model_validate_json(timeline_path(project).read_text(encoding="utf-8"))
        outputs = set(load_state(project).stages[stage].outputs)
        formats = [
            f.name
            for f in timeline.formats
            if str(output_path(project, target, f.name).relative_to(project.root)) in outputs
        ]
        edl = load_edl(project)
        policy = edl.policy.model_dump(exclude_none=True) if isinstance(edl, TalkEdl) else None
        config = load_config(workspace, slug, edl_policy=policy)
        config.ensure_supported()
        try:
            if isinstance(edl, TalkEdl):
                report = _check(project, timeline, edl, config, formats, target, step, warn)
            else:
                report = _check_product(project, timeline, edl, config, formats, target, step)
        except MotionStudioError as exc:
            mark_failed(project, record, exc.message)
            raise
        if report.blocked:
            mark_failed(project, record, verdict(report.findings))
        else:
            inputs = [timeline_path(project)]
            inputs += [output_path(project, target, fmt) for fmt in formats]
            mark_done(
                project,
                record,
                inputs,
                outputs=[
                    report.report,
                    report.report_json,
                    report.cuts_sheet,
                    *([report.contact_sheet] if report.contact_sheet else []),
                ],
            )
    return report


def _check(
    project: ProjectPaths,
    timeline: Timeline,
    edl: TalkEdl,
    config: Config,
    formats: list[str],
    target: RenderTarget,
    step: Callable[[str], None],
    warn: Callable[[str], None],
) -> CheckReport:
    stage = target.stage
    fps = timeline.fps
    cuts_ms = [round(run.out_in * 1000 / fps) for run in timeline.runs[1:]]
    project.check.mkdir(parents=True, exist_ok=True)
    findings: list[Finding] = []
    metrics: dict[str, Any] = {"cuts": len(cuts_ms)}

    step("re-transcribing the voice stem")
    diff = _retranscribe(project, timeline, formats[0], cuts_ms, config, warn)
    words = _source_words(load_analyses(project))
    for miss in diff.misses:
        findings.append(_word_finding(miss, timeline, edl, config.edit, words, cuts_ms))
    metrics["words"] = {"expected": diff.expected, "heard": diff.heard, "matched": diff.matched}

    images = [(e.start / fps, e.end / fps) for e in timeline.events if e.type == "image"]
    measured = _measure_formats(
        project, edl, config, formats, target, step, images, findings, music_only=False
    )
    first = measured[formats[0]]
    max_duration = _shared_metrics(measured, first, edl, config, metrics)
    if first.duration_s > max_duration + 1 / fps:
        findings.append(_over_length(first.duration_s, max_duration, timeline))

    peak_wps = _caption_density(timeline, findings)
    metrics["caption_peak_words_per_s"] = peak_wps
    findings += _event_findings(timeline)

    step("drawing the cut stills")
    video = output_path(project, target, formats[0])
    sheet = cuts_sheet(
        video,
        video_size(video),
        first.duration_s,
        fps,
        _cuts(timeline, cuts_ms),
        f"{project.slug} {stage} {formats[0]}: {len(cuts_ms)} cuts",
        project.check / "cuts.png",
    )

    notes = [
        f"Words were re-transcribed from build/voice_{formats[0]}.wav (the voice before music; "
        f"every format shares it). Cut stills come from the {formats[0]} file."
    ]
    result = CheckReport(
        stage=stage,
        formats=formats,
        findings=findings,
        metrics=metrics,
        cuts_s=[round(c / 1000, 3) for c in cuts_ms],
        report=project.check / "report.md",
        report_json=project.check / "report.json",
        cuts_sheet=sheet,
    )
    return _write_report(project, result, _metric_rows(metrics), notes)


def _check_product(
    project: ProjectPaths,
    timeline: Timeline,
    edl: ProductEdl,
    config: Config,
    formats: list[str],
    target: RenderTarget,
    step: Callable[[str], None],
) -> CheckReport:
    stage = target.stage
    fps = timeline.fps
    slug = project.slug
    scenes = timeline.scenes
    project.check.mkdir(parents=True, exist_ok=True)
    findings: list[Finding] = []
    metrics: dict[str, Any] = {"scenes": len(scenes), "cuts": len(scenes) - 1}

    measured = _measure_formats(
        project, edl, config, formats, target, step, still_scenes(timeline), findings,
        music_only=True,
    )  # fmt: skip
    first = measured[formats[0]]
    max_duration = _shared_metrics(measured, first, edl, config, metrics)
    if first.duration_s > max_duration + 1 / fps:
        over = first.duration_s - max_duration
        findings.append(
            Finding(
                "blocking",
                "over_duration",
                f"the video is {first.duration_s:.1f} s, {over:.1f} s over max_duration_s "
                f"{max_duration:g}",
                f"shorten or remove scenes by at least {over:.1f} s (longest in the middle: "
                f"{longest_middle_scenes(timeline)}); keep the intro and the outro",
            )
        )
    masks = masked_regions(timeline)
    metrics["masks"] = [m.to_json() for m in masks]
    cursors = {a.clip.id: a.cursor for a in load_analyses(project) if a.clip.role == "screen"}
    findings += cursor_findings(timeline, cursors, slug)
    findings += _event_findings(timeline)

    video = output_path(project, target, formats[0])
    size = video_size(video)
    title = f"{slug} {stage} {formats[0]}"
    step("drawing the contact sheet")
    contact, warnings = contact_sheet(
        video, size, first.duration_s, title, project.check / "contact.png"
    )
    cuts = [
        Cut(k, scene.start / fps, scenes[k - 1].id, scene.id)
        for k, scene in enumerate(scenes[1:], start=1)
    ]
    sheet = cuts_sheet(
        video, size, first.duration_s, fps, cuts, f"{title}: {len(cuts)} cuts",
        project.check / "cuts.png",
    )  # fmt: skip

    look = f"`{APP_NAME} look {slug} --at <scene | marker | seconds>`"
    notes = [
        f"No speech to re-transcribe: a product video is music only. Stills come from the "
        f"{formats[0]} file. For any moment you are unsure of, run {look}."
    ]
    sections = [("Masked regions", [m.line(slug) for m in masks] or ["none"])]
    result = CheckReport(
        stage=stage,
        formats=formats,
        findings=findings,
        metrics=metrics,
        cuts_s=[c.t for c in cuts],
        report=project.check / "report.md",
        report_json=project.check / "report.json",
        cuts_sheet=sheet,
        contact_sheet=contact,
        warnings=warnings,
    )
    rows = _product_metric_rows(metrics)
    return _write_report(project, result, rows, notes, sections)


def _measure_formats(
    project: ProjectPaths,
    edl: TalkEdl | ProductEdl,
    config: Config,
    formats: list[str],
    target: RenderTarget,
    step: Callable[[str], None],
    still: list[tuple[float, float]],
    findings: list[Finding],
    *,
    music_only: bool,
) -> dict[str, Measurement]:
    measured: dict[str, Measurement] = {}
    for fmt in formats:
        step(f"measuring {fmt}")
        m = measure(output_path(project, target, fmt))
        measured[fmt] = m
        findings += _media_findings(
            fmt, m, config, edl, target, project.slug, still, music_only=music_only
        )
    return measured


def _shared_metrics(
    measured: dict[str, Measurement],
    first: Measurement,
    edl: TalkEdl | ProductEdl,
    config: Config,
    metrics: dict[str, Any],
) -> float:
    """Fill in the duration, loudness and band metrics; return the length limit."""
    max_duration = edl.max_duration_s or config.defaults.max_duration_s
    metrics["duration_s"] = round(first.duration_s, 3)
    metrics["max_duration_s"] = max_duration
    metrics["loudness"] = {
        fmt: {"integrated_lufs": m.integrated_lufs, "true_peak_db": m.true_peak_db, "lra": m.lra}
        for fmt, m in measured.items()
    }
    metrics["bands"] = {fmt: m.bands for fmt, m in measured.items()}
    return max_duration


def _write_report(
    project: ProjectPaths,
    result: CheckReport,
    rows: list[tuple[str, str]],
    notes: list[str],
    sections: list[tuple[str, list[str]]] | None = None,
) -> CheckReport:
    order = {"blocking": 0, "warning": 1, "info": 2}
    result.findings.sort(key=lambda f: order[f.severity])
    title = f"{project.slug} {result.stage}"
    result.report.write_text(
        markdown(title, result.findings, rows, notes, sections or []), encoding="utf-8"
    )
    result.report_json.write_text(
        json.dumps(result.to_json(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return result


def _retranscribe(
    project: ProjectPaths,
    timeline: Timeline,
    fmt: str,
    cuts_ms: list[int],
    config: Config,
    warn: Callable[[str], None],
) -> WordDiff:
    voice = voice_path(project, fmt)
    if not voice.is_file():
        raise UserError(
            f"the voice stem {voice} is missing",
            hint=f"re-render with `{APP_NAME} render {project.slug}`",
        )
    wav = project.check / "voice_16k.wav"
    run_ffmpeg(
        ["-y", "-v", "error", "-i", voice, "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", wav]
    )
    codes = lang.available_languages()
    job = SpeechJob(
        id=f"voice_{fmt}",
        wav=wav,
        language=timeline.language,
        candidates=codes,
        prompts={c: lang.load_language(c).asr.initial_prompt for c in codes},
    )
    backend = resolve_backend(config.asr.backend)
    run = transcribe_clips([job], backend=backend, model=config.asr.model, on_wait=warn)
    return diff_words(timeline.words, run.results[0].words, cuts_ms)


def _source_words(analyses: Sequence[ClipAnalysis]) -> dict[str, tuple[list[Word], int]]:
    """Each source word ID mapped to its clip's word list and its index there."""
    found: dict[str, tuple[list[Word], int]] = {}
    for analysis in analyses:
        for i, word in enumerate(analysis.words):
            found[word.id] = (analysis.words, i)
    return found


def _word_finding(
    miss: Miss,
    timeline: Timeline,
    edl: TalkEdl,
    policy: Edit,
    words: dict[str, tuple[list[Word], int]],
    cuts_ms: list[int],
) -> Finding:
    word = miss.word
    at = f"{word.start_ms / 1000:.2f} s"
    what = f"'{word.text}' ({word.id})"
    heard = f"heard as '{miss.heard}'" if miss.heard else "missing"
    if miss.cut is None:
        return Finding(
            "info",
            "asr_noise",
            f"{what} at {at} {heard} in the re-transcription, not near a cut: likely ASR noise",
        )
    k = miss.cut
    message = f"clipped {what} at cut {k} ({cuts_ms[k - 1] / 1000:.2f} s): {heard}"
    return Finding(
        "blocking", "clipped_cut", message, _clip_fix(miss, timeline, edl, policy, words)
    )


def _clip_fix(
    miss: Miss,
    timeline: Timeline,
    edl: TalkEdl,
    policy: Edit,
    words: dict[str, tuple[list[Word], int]],
) -> str:
    assert miss.cut is not None
    k = miss.cut
    cut_ms = timeline.runs[k].out_in * 1000 / timeline.fps
    ends_run = (miss.word.start_ms + miss.word.end_ms) / 2 <= cut_ms
    run_index = k - 1 if ends_run else k
    segment = timeline.runs[run_index].segment
    if ends_run:
        pad = f"raise policy.pad_out_ms (now {policy.pad_out_ms})"
    else:
        pad = f"raise policy.pad_in_ms (now {policy.pad_in_ms})"
    clip_words, i = words.get(miss.word.id, ([], -1))
    j = i + 1 if ends_run else i - 1
    if i < 0 or not 0 <= j < len(clip_words):
        return pad
    neighbour = clip_words[j]
    if neighbour.id in edl.drop_words:
        other = f"remove {neighbour.id} from drop_words"
    elif neighbour.filler is not None and neighbour.id not in edl.keep_words:
        other = f"add the filler {neighbour.id} to keep_words"
    elif _segment_edge(timeline, run_index, last=ends_run):
        end = "`to`" if ends_run else "`from`"
        other = f"set segment {segment}'s {end} to {neighbour.id} ('{neighbour.text}')"
    else:
        other = f"raise policy.max_pause_ms (now {policy.max_pause_ms})"
    return f"{pad} or {other}"


def _segment_edge(timeline: Timeline, index: int, *, last: bool) -> bool:
    runs = timeline.runs
    other = index + 1 if last else index - 1
    return not 0 <= other < len(runs) or runs[other].segment != runs[index].segment


def _media_findings(
    fmt: str,
    m: Measurement,
    config: Config,
    edl: TalkEdl | ProductEdl,
    target: RenderTarget,
    slug: str,
    still: list[tuple[float, float]],
    *,
    music_only: bool,
) -> list[Finding]:
    """`still` holds the output spans where a black or frozen picture is intended."""
    found: list[Finding] = []
    master = config.master
    final = target is RenderTarget.FINAL
    # Off-target audio may not ship (guide §5.1); a preview is a draft, so it only warns.
    severity: Severity = "blocking" if final else "warning"
    peak_tolerance = FINAL_TRUE_PEAK_TOLERANCE_DB if final else TRUE_PEAK_TOLERANCE_DB
    fix = _loudness_fix(config, edl, target, slug)
    if abs(m.integrated_lufs - master.integrated_lufs) > LOUDNESS_TOLERANCE_LU:
        found.append(
            Finding(
                severity,
                "loudness",
                f"{fmt}: integrated loudness {m.integrated_lufs:.1f} LUFS, "
                f"target {master.integrated_lufs:.1f} ± {LOUDNESS_TOLERANCE_LU:g}",
                fix,
            )
        )
    if m.true_peak_db > master.true_peak_db + peak_tolerance:
        found.append(
            Finding(
                severity,
                "true_peak",
                f"{fmt}: true peak {m.true_peak_db:.1f} dBTP, limit {master.true_peak_db:.1f}",
                fix,
            )
        )
    audible_bass = m.bands["below_150_hz"] >= max(m.bands.values()) - AUDIBLE_BASS_DB
    if audible_bass and m.bass_over_top_db > SMALL_SPEAKER_DB:
        # With no voice to carry it, a bass-heavy music-only mix is near silent on a laptop.
        found.append(
            Finding(
                "blocking" if music_only else "warning",
                "small_speaker",
                f"{fmt}: energy above 1 kHz is {m.bass_over_top_db:.1f} dB below the energy "
                f"under 150 Hz (over {SMALL_SPEAKER_DB:g}): laptop and phone speakers will "
                "make it sound faint",
                _small_speaker_fix(config, edl, target, slug),
            )
        )
    if music_only:
        fix = "check the footage scene's from and to, and the recording around them"
    else:
        fix = "check the B-roll's asset_in_s and duration, and the segments around it"
    for s in m.black:
        if not _intentional(s, still):
            found.append(
                Finding(
                    "blocking",
                    "black_frames",
                    f"{fmt}: black frames {s.start:.2f}-{s.end:.2f} s ({s.duration:.2f} s)",
                    fix,
                )
            )
    for s in m.frozen:
        if not _intentional(s, still):
            found.append(
                Finding(
                    "warning",
                    "frozen_frames",
                    f"{fmt}: frozen picture {s.start:.2f}-{s.end:.2f} s ({s.duration:.2f} s)",
                    fix,
                )
            )
    return found


def _loudness_fix(
    config: Config, edl: TalkEdl | ProductEdl, target: RenderTarget, slug: str
) -> str:
    """Mastering is automatic, so the EDL lever is the music bed's level."""
    rerender = f"re-render with `{APP_NAME} render {slug} {target.flag}`"
    bug = "if it persists, report it as a motion-studio bug"
    if (edl.music.mode or config.music.mode) == "none":
        return f"{rerender}; {bug}"
    gain = edl.music.gain_db if edl.music.gain_db is not None else config.music.gain_db
    return f"lower music.gain_db in edl.json (now {gain:g}) and {rerender}; {bug}"


def _small_speaker_fix(
    config: Config, edl: TalkEdl | ProductEdl, target: RenderTarget, slug: str
) -> str:
    rerender = f"re-render with `{APP_NAME} render {slug} {target.flag}`"
    mode = edl.music.mode or config.music.mode
    if mode == "library":
        return f"pick a brighter library track (music.track) and {rerender}"
    if mode == "generate":
        return f"ask for brighter instruments in music.prompt, run music again and {rerender}"
    if isinstance(edl, ProductEdl):
        return (
            f"give the video a brighter music bed (music.mode generate or library) and {rerender}"
        )
    return "the voice itself is bass-heavy: check the microphone and the source audio"


def _intentional(stretch: Stretch, still: list[tuple[float, float]]) -> bool:
    inside = sum(max(0.0, min(stretch.end, b) - max(stretch.start, a)) for a, b in still)
    return inside >= INTENTIONAL_SHARE * max(stretch.duration, 1e-6)


def _over_length(duration: float, limit: float, timeline: Timeline) -> Finding:
    lengths: dict[str, float] = {}
    for run in timeline.runs:
        lengths[run.segment] = lengths.get(run.segment, 0.0) + (run.out_out - run.out_in)
    order = list(lengths)
    # The first segment is the hook and the last the payoff; suggest cutting from between.
    middle = order[1:-1] or order
    ranked = sorted(middle, key=lambda s: -lengths[s])[:3]
    names = ", ".join(f"{s} ({lengths[s] / timeline.fps:.1f} s)" for s in ranked)
    over = duration - limit
    return Finding(
        "blocking",
        "over_duration",
        f"the video is {duration:.1f} s, {over:.1f} s over max_duration_s {limit:g}",
        f"remove or shorten the weakest supporting segment by at least {over:.1f} s "
        f"(longest in the middle: {names}); keep the hook and payoff",
    )


def _caption_density(timeline: Timeline, findings: list[Finding]) -> float:
    """Peak caption words per second, counted over a sliding window of output time."""
    words = timeline.words
    if not timeline.captions.enabled or not words:
        return 0.0
    peak, at = 0.0, 0
    for i, first in enumerate(words):
        shown = [w for w in words[i:] if w.start_ms < first.start_ms + DENSITY_WINDOW_MS]
        rate = len(shown) * 1000 / DENSITY_WINDOW_MS
        if rate > peak:
            peak, at = rate, first.start_ms
    if peak > MAX_WORDS_PER_S:
        findings.append(
            Finding(
                "warning",
                "caption_density",
                f"captions show {peak:.1f} words/s from {at / 1000:.2f} s (over {MAX_WORDS_PER_S})",
                "give the speech more room there (raise policy.max_pause_ms) or drop a word",
            )
        )
    return round(peak, 2)


def _event_findings(timeline: Timeline) -> list[Finding]:
    found: list[Finding] = []
    fps = timeline.fps
    full = [
        e
        for e in timeline.events
        if isinstance(e, TimelineBroll | TimelineImage) and e.mode == "full"
    ]
    for n, a in enumerate(full):
        for b in full[n + 1 :]:
            if a.start < b.end and b.start < a.end:
                found.append(
                    Finding(
                        "blocking",
                        "overlay_overlap",
                        f"full-frame {a.asset} and {b.asset} overlap at {b.start / fps:.2f} s",
                        f"end {a.asset} earlier or start {b.asset} later",
                    )
                )
    for title in (e for e in timeline.events if e.type == "title"):
        for b in full:
            if title.start < b.end and b.start < title.end:
                found.append(
                    Finding(
                        "warning",
                        "title_over_broll",
                        f"title '{title.text}' plays over full-frame {b.asset} "
                        f"at {max(title.start, b.start) / fps:.2f} s",
                        "move the title or make the B-roll a pip card",
                    )
                )
    for e in timeline.events:
        if e.end > timeline.duration_frames:
            found.append(
                Finding(
                    "warning",
                    "event_past_end",
                    f"{e.type} event ends {(e.end - timeline.duration_frames) / fps:.2f} s "
                    "after the video",
                    "anchor its end to an earlier word",
                )
            )
    return found


def _cuts(timeline: Timeline, cuts_ms: list[int]) -> list[Cut]:
    words = timeline.words
    found: list[Cut] = []
    for k, cut in enumerate(cuts_ms, start=1):
        before = [w.text for w in words if w.start_ms < cut][-2:]
        after = [w.text for w in words if w.start_ms >= cut][:2]
        found.append(Cut(k, cut / 1000, " ".join(before), " ".join(after)))
    return found


def _metric_rows(metrics: dict[str, Any]) -> list[tuple[str, str]]:
    words = metrics["words"]
    rows = [
        ("duration", f"{metrics['duration_s']:.2f} s (max {metrics['max_duration_s']:g} s)"),
        ("cuts", str(metrics["cuts"])),
        (
            "words re-heard",
            f"{words['matched']} of {words['expected']} matched ({words['heard']} heard)",
        ),
        ("caption peak", f"{metrics['caption_peak_words_per_s']:.2f} words/s"),
        *_audio_rows(metrics),
        ("clip window", f"{CLIP_WINDOW_MS} ms either side of a cut"),
    ]
    return rows


def _audio_rows(metrics: dict[str, Any]) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for fmt, m in metrics["loudness"].items():
        rows.append(
            (
                f"loudness {fmt}",
                f"{m['integrated_lufs']:.1f} LUFS, {m['true_peak_db']:.1f} dBTP, "
                f"LRA {m['lra']:.1f} LU",
            )
        )
    for fmt, bands in metrics["bands"].items():
        rows.append(
            (
                f"bands {fmt}",
                f"below 150 Hz {bands['below_150_hz']:.1f} dB, "
                f"150 Hz-1 kHz {bands['150_hz_to_1_khz']:.1f} dB, "
                f"1-5 kHz {bands['1_to_5_khz']:.1f} dB, "
                f"above 5 kHz {bands['above_5_khz']:.1f} dB",
            )
        )
    return rows


def _product_metric_rows(metrics: dict[str, Any]) -> list[tuple[str, str]]:
    rows = [
        ("duration", f"{metrics['duration_s']:.2f} s (max {metrics['max_duration_s']:g} s)"),
        ("scenes", str(metrics["scenes"])),
        ("masked regions", str(len(metrics["masks"]))),
    ]
    return rows + _audio_rows(metrics)
