"""Console output: summary by rule and severity, then the issue list."""

from __future__ import annotations

from collections import Counter

from rich.console import Console
from rich.padding import Padding
from rich.table import Table
from rich.text import Text

from mepcheck.issues import Report, Severity
from mepcheck.rules import get_rules

_STYLE = {Severity.ERROR: "bold red", Severity.WARNING: "yellow", Severity.INFO: "cyan"}


def print_report(report: Report, console: Console) -> None:
    meta = report.meta
    console.print(f"[bold]mepcheck {meta.version}[/bold]", Text(f"{meta.file} ({meta.ifc_schema})"))
    if not report.issues:
        console.print(f"[green]No issues found[/green] ({len(meta.rules)} rules checked).")
        return
    console.print(_summary_table(report))
    _print_issues(report, console)


def _summary_table(report: Report) -> Table:
    counts = Counter((issue.rule_id, issue.severity) for issue in report.issues)
    table = Table(title="Summary", title_justify="left")
    table.add_column("Rule", no_wrap=True)
    table.add_column("Title")
    for severity in Severity:
        table.add_column(severity.value.capitalize(), justify="right", style=_STYLE[severity])
    for rule in get_rules(report.meta.rules):
        table.add_row(rule.id, rule.title, *(str(counts[rule.id, s]) for s in Severity))
    totals = Counter(issue.severity for issue in report.issues)
    table.add_row("", "Total", *(str(totals[s]) for s in Severity), style="bold")
    return table


def _print_issues(report: Report, console: Console) -> None:
    """Two lines per issue (like a linter), readable in an 80-column terminal."""
    console.print(Text("\nIssues", style="italic"))
    for issue in report.issues:
        # Text() keeps names like "Duct [120x80]" from being read as rich markup.
        header = Text()
        header.append(f"{issue.severity.value.upper():<8}", style=_STYLE[issue.severity])
        header.append(f"{issue.rule_id}  {', '.join(issue.guids)}")
        header.append(
            f"  storey: {issue.storey or '-'}  system: {issue.system or '-'}", style="dim"
        )
        console.print(header)
        console.print(Padding(Text(issue.message), (0, 0, 0, 8)))
