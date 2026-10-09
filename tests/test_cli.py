import os
import subprocess
import sys

import pytest
from typer.testing import CliRunner

from builders import ventilation_line
from mepcheck.cli import app
from mepcheck.kinds import ElementKind
from mepcheck.report.json_report import read_json

runner = CliRunner()
ALL_RULES = ["MEP-001", "MEP-004", "MEP-007", "MEP-008"]


@pytest.fixture
def model_with_issues(tmp_path):
    """One error (MEP-001) and one warning (MEP-004)."""
    line = ventilation_line()
    line.builder.element(ElementKind.DUCT_SEGMENT, "Stray [120x80]", storey=line.l0)
    line.builder.add_port(line.fitting)
    return line.builder.write(tmp_path / "model.ifc")


def test_check_prints_summary_and_writes_json(tmp_path, model_with_issues):
    out = tmp_path / "reports" / "report.json"
    result = runner.invoke(app, ["check", str(model_with_issues), "--json", str(out)])

    assert result.exit_code == 0, result.output
    assert "Summary" in result.output
    assert "Stray [120x80]" in result.output
    report = read_json(out)
    assert [issue.rule_id for issue in report.issues] == ["MEP-001", "MEP-004"]
    assert report.meta.file == "model.ifc"
    assert report.meta.ifc_schema == "IFC4"
    assert report.meta.rules == ALL_RULES
    assert report.meta.config["storey_tolerance_m"] == 0.5


def test_rule_selection(model_with_issues):
    result = runner.invoke(app, ["check", str(model_with_issues), "--rules", "mep-004"])
    assert result.exit_code == 0, result.output
    assert "MEP-004" in result.output
    assert "MEP-001" not in result.output


@pytest.mark.parametrize(
    ("args", "exit_code"),
    [
        ([], 0),
        (["--fail-on", "error"], 1),
        (["--fail-on", "warning"], 1),
        (["--rules", "MEP-004", "--fail-on", "error"], 0),
        (["--rules", "MEP-004", "--fail-on", "warning"], 1),
    ],
)
def test_fail_on_sets_exit_code(model_with_issues, args, exit_code):
    result = runner.invoke(app, ["check", str(model_with_issues), *args])
    assert result.exit_code == exit_code, result.output


def test_clean_model(tmp_path, schema):
    path = ventilation_line(schema).builder.write(tmp_path / "clean.ifc")
    result = runner.invoke(app, ["check", str(path), "--fail-on", "warning"])
    assert result.exit_code == 0, result.output
    assert "No issues found" in result.output


def test_unknown_rule(model_with_issues):
    result = runner.invoke(app, ["check", str(model_with_issues), "--rules", "MEP-999"])
    assert result.exit_code == 2
    assert "Unknown rule id(s): MEP-999" in result.output


def test_missing_file(tmp_path):
    result = runner.invoke(app, ["check", str(tmp_path / "missing.ifc")])
    assert result.exit_code == 2
    assert "File not found" in result.output


def test_rules_command():
    result = runner.invoke(app, ["rules"])
    assert result.exit_code == 0, result.output
    for rule_id in ALL_RULES:
        assert rule_id in result.output


def test_python_m_entry_point():
    result = subprocess.run(
        [sys.executable, "-m", "mepcheck", "rules"],
        capture_output=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "MEP-001" in result.stdout
