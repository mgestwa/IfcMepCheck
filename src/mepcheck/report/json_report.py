"""JSON report: the issue list plus run metadata."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from mepcheck import __version__
from mepcheck.config import Config
from mepcheck.issues import Issue, Report, ReportMeta
from mepcheck.model import ModelView
from mepcheck.rules import Rule


def build_report(
    model: ModelView, config: Config, rules: list[Rule], issues: list[Issue]
) -> Report:
    return Report(
        meta=ReportMeta(
            version=__version__,
            file=model.source,
            ifc_schema=model.schema,
            ifc_project=model.project_guid,
            generated_at=datetime.now(UTC).replace(microsecond=0),
            config=config.model_dump(mode="json"),
            rules=[rule.id for rule in rules if rule.is_configured(config)],
            skipped_rules={
                rule.id: f"not configured: {rule.requires}"
                for rule in rules
                if not rule.is_configured(config)
            },
        ),
        issues=issues,
    )


def write_json(report: Report, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def read_json(path: str | Path) -> Report:
    return Report.model_validate_json(Path(path).read_text(encoding="utf-8"))
