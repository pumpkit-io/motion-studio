"""`reelcut check`: QA a preview or final render before it is delivered."""

import typer

from reelcut import APP_NAME
from reelcut.check import check_project
from reelcut.cli._output import FinalOption, JsonOption, PreviewOption, Reporter, emit, pick_target
from reelcut.cli.workspace import Slug
from reelcut.errors import UserError
from reelcut.paths import find_workspace
from reelcut.target import RenderTarget

SHOWN_ISSUES = 10


def check(
    slug: Slug,
    preview: PreviewOption = False,
    final: FinalOption = False,
    as_json: JsonOption = False,
) -> None:
    """Re-transcribe, measure and look at a render; exit 1 when anything blocks delivery."""
    target = pick_target(preview=preview, final=final)
    with Reporter(as_json) as reporter:
        report = check_project(
            find_workspace(), slug, target=target, on_step=reporter.step, on_warning=reporter.warn
        )
    body = report.to_json()
    lines = [body["summary"]]
    blocking = [f for f in report.findings if f.severity == "blocking"]
    lines += [f"  ✗ {f.line()}" for f in blocking[:SHOWN_ISSUES]]
    if len(blocking) > SHOWN_ISSUES:
        lines.append(f"  (and {len(blocking) - SHOWN_ISSUES} more in the report)")
    warnings = sum(f.severity == "warning" for f in report.findings)
    infos = sum(f.severity == "info" for f in report.findings)
    lines.append(f"{warnings} warnings, {infos} notes; metrics in the report")
    lines.append(f"wrote {report.report}")
    lines.append(f"wrote {report.cuts_sheet} (look at it once per loop)")
    if report.blocked:
        lines.append(
            f"next: edit edl.json, then `{APP_NAME} plan validate {slug}` and render again"
        )
    elif target is RenderTarget.PREVIEW:
        lines.append(f"next: `{APP_NAME} render {slug} {RenderTarget.FINAL.flag}`")
    emit(as_json, body, lines, ok=not report.blocked)
    if report.blocked:
        raise typer.Exit(UserError.exit_code)


def register(app: typer.Typer) -> None:
    app.command()(check)
