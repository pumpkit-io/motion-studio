"""`motion-studio music`: generate or pick the music bed for a project."""

from typing import Annotated

import typer

from motion_studio.cli._output import JsonOption, Reporter, emit
from motion_studio.cli.workspace import Slug
from motion_studio.paths import find_workspace


def music(
    slug: Slug,
    candidates: Annotated[
        int | None,
        typer.Option(
            "--candidates",
            min=1,
            max=4,
            help="Generate this many seeds, from the EDL's seed up, in one model load.",
        ),
    ] = None,
    as_json: JsonOption = False,
) -> None:
    """Generate (ACE-Step) or pick (library) the music bed: build/music.wav and music.json."""
    from motion_studio.music.stage import next_hint, run_music

    with Reporter(as_json) as reporter:

        def waiting(holder: str) -> None:
            reporter.step(f"waiting for another heavy model to finish ({holder})")

        report = run_music(
            find_workspace(),
            slug,
            candidates=candidates,
            on_step=reporter.step,
            on_wait=waiting,
        )
    info = report.info
    lines = [f"warning: {w}" for w in report.warnings]
    if info.mode == "none":
        lines.append("music: none (voice only)")
    elif info.mode == "generate":
        tries = len(info.attempts)
        lines.append(
            f"music: generated {info.duration_s:.1f} s in {info.elapsed_s:.0f} s, "
            f'seed {info.seed}, "{info.prompt}"'
            + (f" ({tries} attempts, earlier ones had vocals)" if tries > 1 else "")
        )
        lines.append(f"  model {info.model}, licence {info.licence or 'UNVERIFIED'}")
    else:
        lines.append(f"music: library track {info.track} ({info.title}), licence {info.licence}")
    if info.mode != "none":
        corrected = (
            f", corrected from {info.tracker_bpm} by the section period"
            if info.tempo_from == "sections"
            else ""
        )
        lines.append(
            f"  {len(info.beats)} beats, {len(info.bars)} bars, "
            f"about {info.detected_bpm or '?'} bpm{corrected}"
        )
        if info.hits:
            lines.append("  hits: " + ", ".join(f"{h.name} {h.time_s:.2f} s" for h in info.hits))
    if info.align is not None:
        a = info.align
        edits = ", ".join(f"{e.bars:+d} bars at {e.at_s:.2f} s" for e in a.edits) or "no edits"
        lines.append(
            f"  aligned: {a.hit} on scene {a.at} at {a.at_s:.2f} s; starts {a.starts_at_s:.2f} s "
            f"into the bed, {edits}, {a.ending} ending"
        )
    if len(info.candidates) > 1:
        lines.append("  candidates (set music.seed to pick one):")
        for c in info.candidates:
            hits = ", ".join(f"{h.name} {h.time_s:.1f}" for h in c.hits) or "no hits"
            body = f"{c.detected_bpm or '?'} bpm, {hits}" if c.accepted else "vocals, unusable"
            mark = "*" if c.seed == info.seed else " "
            lines.append(f"  {mark} seed {c.seed}: {body}")
    if report.fresh:
        lines.append("  unchanged since the last run")
    for path in (report.wav_path, report.json_path, report.credits_path):
        if path is not None:
            lines.append(f"wrote {path}")
    lines.append(next_hint(slug))
    emit(as_json, report.to_json(), lines)


def register(app: typer.Typer) -> None:
    app.command()(music)
