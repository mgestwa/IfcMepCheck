"""Self-contained HTML report: one file, no external resources."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from jinja2 import Environment, PackageLoader

from mepcheck.issues import Report, Severity
from mepcheck.report import rule_titles

# Autoescape on: element names and property values come from the IFC file.
_ENV = Environment(
    loader=PackageLoader("mepcheck.report", "templates"),
    autoescape=True,
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_html(report: Report) -> str:
    severities = [severity.value for severity in Severity]
    counts = Counter((issue.rule_id, issue.severity.value) for issue in report.issues)
    titles = rule_titles(report)
    rule_ids = list(report.meta.rules)
    rule_ids += sorted({issue.rule_id for issue in report.issues} - set(rule_ids))
    rule_rows = [
        {
            "id": rule_id,
            "title": titles.get(rule_id, ""),
            "counts": {severity: counts[rule_id, severity] for severity in severities},
        }
        for rule_id in rule_ids
    ]
    return _ENV.get_template("report.html.j2").render(
        meta=report.meta,
        issues=report.issues,
        severities=severities,
        totals=Counter(issue.severity.value for issue in report.issues),
        rule_rows=rule_rows,
        has_llm=any(issue.explanation or issue.suggested_fix for issue in report.issues),
        generated=report.meta.generated_at.strftime("%Y-%m-%d %H:%M UTC"),
    )


def write_html(report: Report, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html(report), encoding="utf-8")
    return path
