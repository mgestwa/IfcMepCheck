"""Smoke tests on the open sample models from scripts/get_samples.py.

Skipped when a model has not been downloaded (as in CI). Snapshot counts per
rule are added together with the regression test.
"""

from pathlib import Path

import pytest

from mepcheck.config import load_config
from mepcheck.model import ModelView
from mepcheck.report.html_report import render_html
from mepcheck.report.json_report import build_report
from mepcheck.rules import get_rules, run_rules

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"
CASES = [
    ("Building-Hvac_IFC2X3.ifc", "rules.yaml"),
    ("Building-Hvac_IFC4.ifc", "rules.yaml"),
    ("Building-Hvac_IFC4X3.ifc", "rules.yaml"),
    ("Duplex_MEP_20110907.ifc", "rules.yaml"),
    ("Clinic_HVAC.ifc", "clinic.yaml"),
]

pytestmark = pytest.mark.sample


def check_sample(filename, config_name):
    path = SAMPLES / filename
    if not path.exists():
        pytest.skip(f"{filename} not downloaded (python scripts/get_samples.py)")
    config = load_config(ROOT / "examples" / config_name)
    view = ModelView.open(path)
    issues = run_rules(view, config)
    return build_report(view, config, get_rules(), issues)


@pytest.mark.parametrize(("filename", "config_name"), CASES)
def test_sample_model(filename, config_name):
    report = check_sample(filename, config_name)
    assert report.meta.skipped_rules == {}
    assert len({issue.id for issue in report.issues}) == len(report.issues)
    assert render_html(report).count("data-severity=") == len(report.issues)


def test_same_issues_in_every_schema():
    """Building-Hvac is exported in IFC2x3, IFC4 and IFC4X3 with the same GlobalIds."""
    ids = [
        {issue.id for issue in check_sample(filename, "rules.yaml").issues}
        for filename, _ in CASES[:3]
    ]
    assert ids[0] == ids[1] == ids[2]
