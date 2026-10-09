"""Regression tests on the open sample models from scripts/get_samples.py.

Skipped when a model has not been downloaded. The issue counts per rule and a
hash of the issue ids are compared with tests/snapshots/samples.json; after an
intended change, refresh it with:

    MEPCHECK_UPDATE_SNAPSHOTS=1 pytest -m sample
"""

import hashlib
import json
import os
from functools import cache
from pathlib import Path

import pytest

from mepcheck.config import load_config
from mepcheck.issues import Report
from mepcheck.model import ModelView
from mepcheck.report.html_report import render_html
from mepcheck.report.json_report import build_report
from mepcheck.rules import get_rules, run_rules

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"
SNAPSHOT = Path(__file__).parent / "snapshots" / "samples.json"
CASES = [
    ("Building-Hvac_IFC2X3.ifc", "rules.yaml"),
    ("Building-Hvac_IFC4.ifc", "rules.yaml"),
    ("Building-Hvac_IFC4X3.ifc", "rules.yaml"),
    ("Duplex_MEP_20110907.ifc", "rules.yaml"),
    ("Clinic_HVAC.ifc", "clinic.yaml"),
]

pytestmark = pytest.mark.sample


@cache
def _report(filename: str, config_name: str) -> Report:
    config = load_config(ROOT / "examples" / config_name)
    view = ModelView.open(SAMPLES / filename)
    return build_report(view, config, get_rules(), run_rules(view, config))


def check_sample(filename: str, config_name: str) -> Report:
    if not (SAMPLES / filename).exists():
        pytest.skip(f"{filename} not downloaded (python scripts/get_samples.py)")
    return _report(filename, config_name)


def summarize(report: Report, config_name: str) -> dict:
    counts: dict[str, dict[str, int]] = {}
    for issue in report.issues:
        per_rule = counts.setdefault(issue.rule_id, {})
        per_rule[issue.severity.value] = per_rule.get(issue.severity.value, 0) + 1
    ids = "\n".join(sorted(issue.id for issue in report.issues))
    return {
        "config": config_name,
        "issues": len(report.issues),
        "counts": {rule_id: dict(sorted(c.items())) for rule_id, c in sorted(counts.items())},
        "ids_sha256": hashlib.sha256(ids.encode("utf-8")).hexdigest(),
    }


@pytest.mark.parametrize(("filename", "config_name"), CASES)
def test_snapshot(filename, config_name):
    current = summarize(check_sample(filename, config_name), config_name)
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8")) if SNAPSHOT.exists() else {}
    if os.environ.get("MEPCHECK_UPDATE_SNAPSHOTS") == "1":
        snapshot[filename] = current
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", "utf-8")
        return
    if filename not in snapshot:
        pytest.fail(f"No snapshot for {filename}: run MEPCHECK_UPDATE_SNAPSHOTS=1 pytest -m sample")
    assert current == snapshot[filename]


@pytest.mark.parametrize(("filename", "config_name"), CASES)
def test_reports_are_consistent(filename, config_name):
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
