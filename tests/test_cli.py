import os
import subprocess
import sys
import zipfile

import pytest
from typer.testing import CliRunner

from builders import ventilation_line
from fake_llm import FakeLLM
from mepcheck.cli import app
from mepcheck.kinds import ElementKind
from mepcheck.llm.client import LLMError
from mepcheck.report.json_report import read_json

runner = CliRunner()
WIDE = {"COLUMNS": "200"}  # keep rich from wrapping long lines in assertions
ALL_RULES = ["MEP-001", "MEP-003", "MEP-004", "MEP-005", "MEP-006", "MEP-007", "MEP-008"]
# MEP-003 and MEP-005 need a configuration section and are skipped without one.
DEFAULT_RULES = ["MEP-001", "MEP-004", "MEP-006", "MEP-007", "MEP-008"]

CONFIG = """\
required_properties:
  IfcAirTerminal:
    - name: AirFlowRate
      any_of:
        - pset: Pset_AirTerminalOccurrence
          property: AirFlowRate
insulation:
  required_for_system_names: ['^N']
"""


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
    assert report.meta.rules == DEFAULT_RULES
    assert set(report.meta.skipped_rules) == {"MEP-003", "MEP-005"}
    assert "Skipped: MEP-003" in result.output
    assert report.meta.config["storey_tolerance_m"] == 0.5


def test_config_enables_rules_and_html_report(tmp_path, model_with_issues):
    config = tmp_path / "rules.yaml"
    config.write_text(CONFIG, encoding="utf-8")
    html = tmp_path / "out" / "report.html"
    json_path = tmp_path / "out" / "report.json"
    args = ["--config", str(config), "--html", str(html), "--json", str(json_path)]
    result = runner.invoke(app, ["check", str(model_with_issues), *args])

    assert result.exit_code == 0, result.output
    report = read_json(json_path)
    assert report.meta.rules == ALL_RULES
    assert report.meta.skipped_rules == {}
    # The terminal has no airflow, the N1 ducts and the elbow have no insulation.
    assert {issue.rule_id for issue in report.issues} >= {"MEP-003", "MEP-005"}
    content = html.read_text(encoding="utf-8")
    assert content.startswith("<!doctype html>")
    assert all(issue.guids[0] in content for issue in report.issues)


def test_bcf_export(tmp_path, model_with_issues):
    bcf = tmp_path / "out" / "issues.bcf"
    result = runner.invoke(app, ["check", str(model_with_issues), "--bcf", str(bcf)])
    assert result.exit_code == 0, result.output
    assert "BCF file:" in result.output
    with zipfile.ZipFile(bcf) as archive:
        markups = [name for name in archive.namelist() if name.endswith("markup.bcf")]
    assert len(markups) == 2


@pytest.fixture
def report_json(tmp_path, model_with_issues):
    path = tmp_path / "report.json"
    result = runner.invoke(app, ["check", str(model_with_issues), "--json", str(path)])
    assert result.exit_code == 0, result.output
    return path


def test_explain_writes_explanations_to_json_and_html(tmp_path, report_json, monkeypatch):
    llm = FakeLLM()
    monkeypatch.setattr("mepcheck.cli.client_from_env", lambda: llm)
    monkeypatch.setenv("MEPCHECK_CACHE_DIR", str(tmp_path / "cache"))
    html = tmp_path / "explained.html"
    args = ["--lang", "pl", "--html", str(html), "--ifc", str(tmp_path / "model.ifc")]
    result = runner.invoke(app, ["explain", str(report_json), *args], env=WIDE)

    assert result.exit_code == 0, result.output
    assert "fake/fake-1: 2 explained, 0 from cache" in result.output
    report = read_json(report_json)
    assert all(issue.explanation and issue.suggested_fix for issue in report.issues)
    assert "Write in Polish." in llm.calls[0][0]
    assert "property_sets" in llm.calls[0][1][0]["element"]
    content = html.read_text(encoding="utf-8")
    assert "Suggested fix" in content
    assert report.issues[0].suggested_fix in content

    # Same language and context: answered from the cache. Another language is a new request.
    again = runner.invoke(app, ["explain", str(report_json), *args, "--force"], env=WIDE)
    assert "0 explained, 2 from cache" in again.output
    english = runner.invoke(app, ["explain", str(report_json), "--force"], env=WIDE)
    assert "2 explained, 0 from cache" in english.output


def test_explain_without_llm_keeps_report(tmp_path, report_json, monkeypatch):
    def unavailable():
        raise LLMError("Set MEPCHECK_LLM_MODEL to an OpenAI model name")

    monkeypatch.setattr("mepcheck.cli.client_from_env", unavailable)
    out = tmp_path / "copy.json"
    result = runner.invoke(app, ["explain", str(report_json), "--out", str(out)], env=WIDE)
    assert result.exit_code == 0, result.output
    assert "left without explanations" in result.output
    assert read_json(out).issues == read_json(report_json).issues


def test_explain_invalid_report(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{}", encoding="utf-8")
    result = runner.invoke(app, ["explain", str(path)])
    assert result.exit_code == 2


def test_invalid_config(tmp_path, model_with_issues):
    config = tmp_path / "rules.yaml"
    config.write_text("storey_tolerance_m: -1\nseverity_overrides:\n  MEP-999: info\n")
    result = runner.invoke(app, ["check", str(model_with_issues), "--config", str(config)])
    assert result.exit_code == 2
    assert "rules.yaml:1: storey_tolerance_m" in result.output


def test_console_limit(tmp_path):
    line = ventilation_line()
    for number in range(3):
        line.builder.element(ElementKind.DUCT_SEGMENT, f"Stray {number}", storey=line.l0)
    path = line.builder.write(tmp_path / "strays.ifc")

    result = runner.invoke(app, ["check", str(path), "--limit", "1"])
    assert result.exit_code == 0, result.output
    assert "... 2 more MEP-001 issues" in result.output
    assert runner.invoke(app, ["check", str(path), "--limit", "0"]).output.count("Stray") == 3


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
