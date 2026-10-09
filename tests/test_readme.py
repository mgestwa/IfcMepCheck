"""Keep the README in step with the code."""

from pathlib import Path

from mepcheck.cli import app
from mepcheck.rules import get_rules

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")


def test_every_rule_is_in_the_rule_table():
    for rule in get_rules():
        assert f"| {rule.id} | {rule.title} |" in README, rule.id


def test_every_command_is_documented():
    for command in app.registered_commands:
        name = command.name or command.callback.__name__
        assert f"mepcheck {name}" in README, name


def test_linked_files_exist():
    for path in (
        "docs/report.png",
        "examples/rules.yaml",
        "examples/clinic.yaml",
        "LICENSE",
        "CHANGELOG.md",
        "tests/snapshots/samples.json",
        ".env.example",
    ):
        assert (ROOT / path).exists(), path
