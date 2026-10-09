from datetime import UTC, datetime

from mepcheck.issues import Issue, Report, ReportMeta, Severity, issue_id


def test_issue_id_is_deterministic_and_order_insensitive():
    a = issue_id("MEP-004", ["guid-b", "guid-a"])
    assert a == issue_id("MEP-004", ["guid-a", "guid-b"])
    assert a == issue_id("MEP-004", ["guid-a", "guid-b", "guid-a"])
    assert a != issue_id("MEP-001", ["guid-a", "guid-b"])
    assert a != issue_id("MEP-004", ["guid-a"])


def test_severity_rank():
    assert Severity.ERROR.rank > Severity.WARNING.rank > Severity.INFO.rank


def test_report_json_round_trip():
    issue = Issue(
        id=issue_id("MEP-001", ["0abc"]),
        rule_id="MEP-001",
        severity=Severity.ERROR,
        title="Element not assigned to a system",
        message="IfcDuctSegment 'Duct A' is not assigned to any distribution system.",
        guids=["0abc"],
        ifc_class="IfcDuctSegment",
        element_name="Duct A",
        storey="L0",
        location=(1.0, 2.0, 2.8),
        evidence={"kind": "duct_segment"},
    )
    report = Report(
        meta=ReportMeta(
            version="0.1.0",
            file="model.ifc",
            ifc_schema="IFC4",
            generated_at=datetime(2026, 10, 9, tzinfo=UTC),
            config={"storey_tolerance_m": 0.5},
            rules=["MEP-001"],
        ),
        issues=[issue],
    )
    assert Report.model_validate_json(report.model_dump_json()) == report
