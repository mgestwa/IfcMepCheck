from builders import ventilation_line
from mepcheck.config import Config
from mepcheck.issues import Severity
from mepcheck.kinds import ElementKind
from mepcheck.rules import run_rules


def check(view, config=None):
    return run_rules(view, config or Config(), ["MEP-006"])


def test_connected_elements_share_a_system(schema):
    assert check(ventilation_line(schema).view()) == []


def test_connection_to_another_system(schema):
    line = ventilation_line(schema)
    w1 = line.builder.system("W1")
    grille = line.builder.element(
        ElementKind.AIR_TERMINAL, "Exhaust grille", storey=line.l0, system=w1
    )
    port, _ = line.builder.connect(line.duct_b, grille)

    [issue] = check(line.view())
    assert issue.rule_id == "MEP-006"
    assert issue.severity is Severity.ERROR
    assert issue.guids == [line.duct_b.GlobalId, grille.GlobalId]
    assert issue.element_name == "Duct B"
    assert "(N1) is connected to" in issue.message
    assert [e["systems"] for e in issue.evidence["elements"]] == [["N1"], ["W1"]]
    assert issue.evidence["elements"][0]["port"] == port.GlobalId


def test_element_in_both_systems(schema):
    line = ventilation_line(schema)
    w1 = line.builder.system("W1")
    unit = line.builder.element(ElementKind.HVAC_EQUIPMENT, "AHU", storey=line.l0, system=w1)
    line.builder.assign_system(unit, line.system)
    line.builder.connect(line.duct_a, unit)
    assert check(line.view()) == []


def test_element_without_system_is_left_to_mep001(schema):
    line = ventilation_line(schema)
    stray = line.builder.element(ElementKind.DUCT_SEGMENT, "Stray", storey=line.l0)
    line.builder.connect(line.duct_b, stray)
    assert check(line.view()) == []


def test_system_names_from_properties():
    line = ventilation_line()
    builder = line.builder
    a = builder.element(ElementKind.DUCT_SEGMENT, "Supply duct", storey=line.l0)
    b = builder.element(ElementKind.DUCT_SEGMENT, "Exhaust duct", storey=line.l0)
    builder.pset(a, "Mechanical", {"System Name": "Mechanical Supply Air 1"})
    builder.pset(b, "Mechanical", {"System Name": "Mechanical Exhaust Air 1"})
    builder.connect(a, b)
    config = Config.model_validate(
        {"system_name_properties": [{"pset": "Mechanical", "property": "System Name"}]}
    )

    [issue] = check(line.view(), config)
    assert issue.guids == [a.GlobalId, b.GlobalId]
    assert issue.system == "Mechanical Supply Air 1"


def test_revit_multi_system_property_is_split():
    """Revit writes an AHU in several systems as one comma-separated value."""
    line = ventilation_line()
    builder = line.builder
    unit = builder.element(ElementKind.HVAC_EQUIPMENT, "AHU", storey=line.l0)
    duct = builder.element(ElementKind.DUCT_SEGMENT, "Supply duct", storey=line.l0)
    builder.pset(unit, "Mechanical", {"System Name": "Hydronic Supply 1,Mechanical Supply Air 2"})
    builder.pset(duct, "Mechanical", {"System Name": "Mechanical Supply Air 2"})
    builder.connect(unit, duct)
    config = Config.model_validate(
        {"system_name_properties": [{"pset": "Mechanical", "property": "System Name"}]}
    )
    assert check(line.view(), config) == []
