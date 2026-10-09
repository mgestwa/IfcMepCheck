from builders import ventilation_line
from mepcheck.config import Config
from mepcheck.issues import Severity
from mepcheck.kinds import ElementKind
from mepcheck.rules import run_rules

CONFIG = Config.model_validate({"insulation": {"required_for_system_names": [r"^N\d*"]}})


def check(view, config=CONFIG):
    return run_rules(view, config, ["MEP-005"])


def insulate_all(line, predefined_type="INSULATION"):
    for element in (line.duct_a, line.fitting, line.duct_b):
        line.builder.insulate(element, predefined_type)


def test_insulated_ducts(schema):
    line = ventilation_line(schema)
    insulate_all(line)
    assert check(line.view()) == []


def test_missing_insulation(schema):
    line = ventilation_line(schema)
    line.builder.insulate(line.duct_a)
    line.builder.insulate(line.fitting)

    [issue] = check(line.view())
    assert issue.rule_id == "MEP-005"
    assert issue.severity is Severity.WARNING
    assert issue.guids == [line.duct_b.GlobalId]
    assert issue.system == "N1"
    assert issue.evidence == {
        "kind": "duct_segment",
        "systems": ["N1"],
        "patterns": [r"^N\d*"],
        "coverings": [],
    }


def test_other_covering_type_is_not_insulation(schema):
    line = ventilation_line(schema)
    insulate_all(line, predefined_type="CLADDING")
    issues = check(line.view())
    assert len(issues) == 3
    assert issues[0].evidence["coverings"] == ["CLADDING"]


def test_custom_covering_types():
    line = ventilation_line()
    insulate_all(line, predefined_type="WRAPPING")
    config = Config.model_validate(
        {"insulation": {"required_for_system_names": ["^N"], "covering_types": ["wrapping"]}}
    )
    assert check(line.view(), config) == []


def test_system_not_matching_pattern(schema):
    line = ventilation_line(schema)
    config = Config.model_validate({"insulation": {"required_for_system_names": ["^W"]}})
    assert check(line.view(), config) == []


def test_terminals_are_not_checked_by_default(schema):
    line = ventilation_line(schema)
    insulate_all(line)
    issues = check(line.view())
    assert line.terminal.GlobalId not in {guid for issue in issues for guid in issue.guids}


def test_system_name_from_property():
    line = ventilation_line()
    stray = line.builder.element(ElementKind.DUCT_SEGMENT, "Stray", storey=line.l0)
    line.builder.pset(stray, "Mechanical", {"System Name": "N7 supply"})
    insulate_all(line)
    config = Config.model_validate(
        {
            "insulation": {"required_for_system_names": [r"^N\d"]},
            "system_name_properties": [{"pset": "Mechanical", "property": "System Name"}],
        }
    )

    [issue] = check(line.view(), config)
    assert issue.guids == [stray.GlobalId]
    assert issue.system == "N7 supply"
