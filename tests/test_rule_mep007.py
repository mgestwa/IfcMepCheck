from builders import ventilation_line
from mepcheck.config import Config
from mepcheck.issues import Severity
from mepcheck.model import ModelView
from mepcheck.rules import run_rules


def check(view):
    return run_rules(view, Config(), ["MEP-007"])


def test_unique_guids(schema):
    assert check(ventilation_line(schema).view()) == []


def test_duplicate_guid_survives_file_round_trip(tmp_path, schema):
    line = ventilation_line(schema)
    guid = line.duct_a.GlobalId
    line.terminal.GlobalId = guid
    view = ModelView.open(line.builder.write(tmp_path / "duplicate.ifc"))

    [issue] = check(view)
    assert issue.rule_id == "MEP-007"
    assert issue.severity is Severity.ERROR
    assert issue.guids == [guid]
    assert issue.element_name == "Duct A"
    assert issue.evidence["count"] == 2
    assert [e["name"] for e in issue.evidence["entities"]] == ["Duct A", "Supply diffuser"]


def test_duplicate_on_relationship(schema):
    line = ventilation_line(schema)
    [relationship] = line.builder.file.by_type("IfcRelContainedInSpatialStructure")
    relationship.GlobalId = line.system.GlobalId

    [issue] = check(line.view())
    assert issue.guids == [line.system.GlobalId]
    classes = {e["ifc_class"] for e in issue.evidence["entities"]}
    assert classes == {line.system.is_a(), "IfcRelContainedInSpatialStructure"}
