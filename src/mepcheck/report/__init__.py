"""Report writers."""

from __future__ import annotations

from mepcheck.issues import Report
from mepcheck.rules import get_rules


def rule_titles(report: Report) -> dict[str, str]:
    """Rule id -> title, from the registry, or from the issues for unknown ids."""
    titles = {issue.rule_id: issue.title for issue in report.issues}
    titles.update({rule.id: rule.title for rule in get_rules()})
    return titles
