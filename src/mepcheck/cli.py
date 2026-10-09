"""Command line interface: mepcheck check | rules."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table
from rich.text import Text

from mepcheck.config import Config, ConfigError, load_config
from mepcheck.issues import Severity
from mepcheck.model import ModelLoadError, ModelView
from mepcheck.report.console import print_report
from mepcheck.report.html_report import write_html
from mepcheck.report.json_report import build_report, write_json
from mepcheck.rules import UnknownRuleError, get_rules, run_rules

app = typer.Typer(
    name="mepcheck",
    help="Rule-based quality checks for MEP/HVAC IFC models.",
    no_args_is_help=True,
    add_completion=False,
)


class FailOn(StrEnum):
    ERROR = "error"
    WARNING = "warning"


@app.command()
def check(
    model: Annotated[Path, typer.Argument(help="IFC file to check.")],
    rules: Annotated[
        str | None,
        typer.Option(help="Comma-separated rule ids, e.g. MEP-001,MEP-004. Default: all rules."),
    ] = None,
    config_path: Annotated[
        Path | None,
        typer.Option("--config", help="YAML configuration, see examples/rules.yaml."),
    ] = None,
    json_path: Annotated[
        Path | None, typer.Option("--json", help="Write the JSON report to this file.")
    ] = None,
    html_path: Annotated[
        Path | None, typer.Option("--html", help="Write the HTML report to this file.")
    ] = None,
    fail_on: Annotated[
        FailOn | None,
        typer.Option(help="Exit with code 1 if any issue has at least this severity."),
    ] = None,
    limit: Annotated[
        int, typer.Option(min=0, help="Issues listed per rule in the console (0 = all).")
    ] = 20,
) -> None:
    """Check an IFC model and print the issues."""
    console = Console()
    try:
        selected = get_rules(rules.split(",") if rules is not None else None)
        config = (
            load_config(config_path, rule_ids=[rule.id for rule in get_rules()])
            if config_path is not None
            else Config()
        )
        view = ModelView.open(model)
        issues = run_rules(view, config, [rule.id for rule in selected])
    except (UnknownRuleError, ConfigError, ModelLoadError) as exc:
        Console(stderr=True).print(Text(f"Error: {exc}", style="red"))
        raise typer.Exit(code=2) from exc

    report = build_report(view, config, selected, issues)
    print_report(report, console, limit=limit)
    if json_path is not None:
        console.print(Text(f"JSON report: {write_json(report, json_path)}"))
    if html_path is not None:
        console.print(Text(f"HTML report: {write_html(report, html_path)}"))

    if fail_on is not None:
        threshold = Severity(fail_on.value).rank
        if any(issue.severity.rank >= threshold for issue in issues):
            raise typer.Exit(code=1)


@app.command("rules")
def list_rules() -> None:
    """List the available rules."""
    table = Table(show_lines=True)
    table.add_column("Rule", no_wrap=True)
    table.add_column("Severity", no_wrap=True)
    table.add_column("What it checks and why it matters at handover")
    table.add_column("Applies to")
    table.add_column("Needs config")
    for rule in get_rules():
        description = Text(rule.title, style="bold")
        description.append(f"\n{rule.rationale}", style="")
        table.add_row(
            rule.id,
            rule.severity.value,
            description,
            ", ".join(rule.applies_to),
            rule.requires or "-",
        )
    Console().print(table)
