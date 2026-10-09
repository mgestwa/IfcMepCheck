import ifcopenshell.api.group
import ifcopenshell.api.root

from builders import ventilation_line
from mepcheck.config import Config
from mepcheck.issues import Severity
from mepcheck.kinds import ElementKind
from mepcheck.rules import run_rules


def check(view):
    return run_rules(view, Config(), ["MEP-001"])


def test_all_elements_in_system(schema):
    assert check(ventilation_line(schema).view()) == []


def test_element_without_system(schema):
    line = ventilation_line(schema)
    stray = line.builder.element(
        ElementKind.DUCT_SEGMENT, "Stray duct", storey=line.l0, at=(5, 0, 2.8)
    )
    line.builder.connect(line.terminal, stray)

    [issue] = check(line.view())
    assert issue.rule_id == "MEP-001"
    assert issue.severity is Severity.ERROR
    assert issue.guids == [stray.GlobalId]
    assert issue.element_name == "Stray duct"
    assert issue.system is None
    assert issue.storey == "L0"
    assert issue.location == (5.0, 0.0, 2.8)
    assert issue.evidence == {"kind": "duct_segment"}


def test_zone_does_not_count_as_system():
    line = ventilation_line("IFC4")
    element = line.builder.element(ElementKind.AIR_TERMINAL, "Zoned diffuser", storey=line.l0)
    zone = ifcopenshell.api.root.create_entity(line.builder.file, ifc_class="IfcZone", name="Z1")
    ifcopenshell.api.group.assign_group(line.builder.file, products=[element], group=zone)

    [issue] = check(line.view())
    assert issue.guids == [element.GlobalId]
