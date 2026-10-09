import math
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest
import xmlschema

from builders import ventilation_line
from mepcheck.config import Config
from mepcheck.kinds import ElementKind
from mepcheck.report.bcf_export import (
    CAMERA_DISTANCE_M,
    camera,
    topics_from_report,
    write_bcf,
)
from mepcheck.report.json_report import build_report
from mepcheck.rules import get_rules, run_rules

SCHEMAS = Path(__file__).parent / "data" / "bcf21"
STRAY = "Stray <duct> & co"


@pytest.fixture(scope="module")
def xsd():
    return {name: xmlschema.XMLSchema(SCHEMAS / f"{name}.xsd") for name in ("markup", "visinfo")}


def model_with_issues(schema="IFC4"):
    """MEP-001 (stray duct), MEP-004 (open port), MEP-006 (N1 to W1), MEP-007 (no location)."""
    line = ventilation_line(schema)
    builder = line.builder
    builder.element(ElementKind.DUCT_SEGMENT, STRAY, storey=line.l0, at=(8, 0, 2.8))
    builder.add_port(line.fitting)
    w1 = builder.system("W1")
    grille = builder.element(
        ElementKind.AIR_TERMINAL, "Exhaust grille", storey=line.l0, system=w1, at=(2, 8, 2.6)
    )
    builder.connect(line.duct_b, grille)
    [relationship] = builder.file.by_type("IfcRelContainedInSpatialStructure")
    relationship.GlobalId = line.system.GlobalId
    return line


def report_for(line):
    view = line.view()
    config = Config()
    return build_report(view, config, get_rules(), run_rules(view, config))


def read_bcf(path):
    with zipfile.ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def by_rule(report, rule_id):
    return next(issue for issue in report.issues if issue.rule_id == rule_id)


def vector(element, name):
    node = element.find(name)
    return tuple(float(node.find(axis).text) for axis in "XYZ")


def test_valid_against_bcf21_schemas(tmp_path, xsd, schema):
    report = report_for(model_with_issues(schema))
    files = read_bcf(write_bcf(report, tmp_path / "issues.bcf"))

    assert ET.fromstring(files["bcf.version"]).get("VersionId") == "2.1"
    for name, data in files.items():
        if name.endswith("markup.bcf"):
            xsd["markup"].validate(ET.fromstring(data))
        elif name.endswith("viewpoint.bcfv"):
            xsd["visinfo"].validate(ET.fromstring(data))
    assert len(files) == 1 + 2 * len(report.issues)


def test_one_topic_per_issue(tmp_path):
    report = report_for(model_with_issues())
    files = read_bcf(write_bcf(report, tmp_path / "issues.bcf"))
    assert {issue.rule_id for issue in report.issues} == {
        "MEP-001",
        "MEP-004",
        "MEP-006",
        "MEP-007",
    }

    for index, issue in enumerate(report.issues, start=1):
        markup = ET.fromstring(files[f"{issue.id}/markup.bcf"])
        topic = markup.find("Topic")
        assert topic.get("Guid") == issue.id
        assert topic.findtext("Title") == (
            f"[{issue.rule_id}] {issue.title}: {issue.element_name or issue.ifc_class}"
        )
        assert topic.findtext("Description") == issue.message
        assert [label.text for label in topic.findall("Labels")] == [
            issue.rule_id,
            issue.severity.value,
        ]
        assert topic.findtext("Index") == str(index)
        assert markup.find("Header/File").get("IfcProject") == report.meta.ifc_project
        assert markup.findtext("Header/File/Filename") == "builder.ifc"


def test_viewpoint_selects_and_colours_issue_elements(tmp_path):
    report = report_for(model_with_issues())
    files = read_bcf(write_bcf(report, tmp_path / "issues.bcf"))

    for issue in report.issues:
        viewpoint = ET.fromstring(files[f"{issue.id}/viewpoint.bcfv"])
        selected = [c.get("IfcGuid") for c in viewpoint.findall("Components/Selection/Component")]
        assert selected == issue.guids
        coloured = viewpoint.findall("Components/Coloring/Color/Component")
        assert [c.get("IfcGuid") for c in coloured] == issue.guids
        assert viewpoint.find("Components/Visibility").get("DefaultVisibility") == "true"
    assert len(by_rule(report, "MEP-006").guids) == 2


def test_camera_looks_at_issue_location(tmp_path):
    report = report_for(model_with_issues())
    issue = by_rule(report, "MEP-001")
    files = read_bcf(write_bcf(report, tmp_path / "issues.bcf"))
    perspective = ET.fromstring(files[f"{issue.id}/viewpoint.bcfv"]).find("PerspectiveCamera")

    viewpoint = vector(perspective, "CameraViewPoint")
    direction = vector(perspective, "CameraDirection")
    up = vector(perspective, "CameraUpVector")
    target = [v + CAMERA_DISTANCE_M * d for v, d in zip(viewpoint, direction, strict=True)]
    assert target == pytest.approx(issue.location, abs=1e-5)
    assert math.dist(direction, (0, 0, 0)) == pytest.approx(1)
    assert sum(u * d for u, d in zip(up, direction, strict=True)) == pytest.approx(0, abs=1e-6)
    assert up[2] > 0
    assert viewpoint[2] > issue.location[2]
    assert 45 <= float(perspective.findtext("FieldOfView")) <= 60


def test_issue_without_location_has_no_camera(tmp_path):
    report = report_for(model_with_issues())
    issue = by_rule(report, "MEP-007")
    assert issue.location is None
    files = read_bcf(write_bcf(report, tmp_path / "issues.bcf"))
    assert ET.fromstring(files[f"{issue.id}/viewpoint.bcfv"]).find("PerspectiveCamera") is None


def test_camera_up_vector_is_perpendicular():
    viewpoint, direction, up = camera((10.0, 20.0, 3.0), distance=4.0)
    assert math.dist(viewpoint, (10.0, 20.0, 3.0)) == pytest.approx(4.0)
    assert sum(u * d for u, d in zip(up, direction, strict=True)) == pytest.approx(0, abs=1e-12)
    assert math.dist(up, (0, 0, 0)) == pytest.approx(1)


def test_same_report_gives_identical_file(tmp_path):
    report = report_for(model_with_issues())
    first = write_bcf(report, tmp_path / "a.bcf").read_bytes()
    assert write_bcf(report, tmp_path / "b.bcf").read_bytes() == first


def test_topics_keep_guids_after_a_fix(tmp_path):
    line = model_with_issues()
    before = {topic.guid: topic.viewpoint_guid for topic in topics_from_report(report_for(line))}

    # Fix MEP-001: put the stray duct into N1.
    [stray] = [e for e in line.builder.file.by_type("IfcElement") if e.Name == STRAY]
    line.builder.assign_system(stray, line.system)
    after = {topic.guid: topic.viewpoint_guid for topic in topics_from_report(report_for(line))}

    assert len(after) == len(before) - 1
    assert after.items() <= before.items()


def test_names_are_escaped(tmp_path):
    report = report_for(model_with_issues())
    issue = by_rule(report, "MEP-001")
    files = read_bcf(write_bcf(report, tmp_path / "issues.bcf"))
    raw = files[f"{issue.id}/markup.bcf"]
    assert STRAY.encode() not in raw
    assert ET.fromstring(raw).findtext("Topic/Title").endswith(STRAY)


def test_description_includes_llm_explanation():
    report = report_for(model_with_issues())
    report.issues[0].explanation = "Drawn outside any system."
    report.issues[0].suggested_fix = "Assign it to N1."
    [topic, *_] = topics_from_report(report)
    assert topic.description.endswith(
        "\n\nExplanation: Drawn outside any system.\n\nSuggested fix: Assign it to N1."
    )
