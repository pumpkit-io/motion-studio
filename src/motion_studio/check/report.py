"""Check findings and `check/report.md`: verdict, blocking issues with EDL fixes, then the rest."""

from dataclasses import asdict, dataclass
from typing import Any, Literal

Severity = Literal["blocking", "warning", "info"]
SEVERITIES: tuple[Severity, ...] = ("blocking", "warning", "info")
HEADINGS = {"blocking": "Blocking", "warning": "Warnings", "info": "Info"}


@dataclass(frozen=True)
class Finding:
    severity: Severity
    code: str
    message: str
    fix: str | None = None

    def line(self) -> str:
        return f"{self.message} → {self.fix}" if self.fix else self.message

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


def verdict(findings: list[Finding]) -> str:
    blocking = sum(f.severity == "blocking" for f in findings)
    warnings = sum(f.severity == "warning" for f in findings)
    if blocking:
        return (
            f"BLOCKED: {blocking} blocking issue{'s' * (blocking != 1)}; "
            "fix edl.json, re-render and check again"
        )
    tail = f" ({warnings} warning{'s' * (warnings != 1)})" if warnings else ""
    return f"PASS: ready to deliver{tail}"


def markdown(
    title: str,
    findings: list[Finding],
    metrics: list[tuple[str, str]],
    notes: list[str],
    sections: list[tuple[str, list[str]]] | None = None,
) -> str:
    """`sections` are extra headed lists, after the findings and before the metrics."""
    lines = [verdict(findings), "", f"# Check: {title}", ""]
    for severity in SEVERITIES:
        chosen = [f for f in findings if f.severity == severity]
        lines.append(f"## {HEADINGS[severity]}")
        lines.append("")
        lines += [f"- {f.line()}" for f in chosen] or ["- none"]
        lines.append("")
    for heading, items in sections or []:
        lines += [f"## {heading}", "", *(f"- {item}" for item in items), ""]
    lines += ["## Metrics", "", "| metric | value |", "|---|---|"]
    lines += [f"| {name} | {value} |" for name, value in metrics]
    if notes:
        lines += ["", *notes]
    return "\n".join(lines) + "\n"
