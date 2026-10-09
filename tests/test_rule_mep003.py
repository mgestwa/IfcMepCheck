import pytest

from builders import ventilation_line
from mepcheck.config import Config
from mepcheck.issues import Severity
from mepcheck.kinds import ElementKind
from mepcheck.rules import run_rules

CONFIG = Config.model_validate(
    {
        "required_properties": {
            "IfcAirTerminal": [
                {
                    "name": "AirFlowRate",
                    "any_of": [
                        {"pset": "Pset_AirTerminalOccurrence", "property": "AirFlowRate"},
                        {"pset": "Mechanical - Flow", "property": "Flow"},
                    ],
                },
                {"name": "Manufacturer"},  # any property set
            ]
        }
    }
)


def check(view, config=CONFIG):
    return run_rules(view, config, ["MEP-003"])


def complete(line):
    builder = line.builder
    builder.pset(line.terminal, "Pset_AirTerminalOccurrence", {"AirFlowRate": 0.12})
    builder.pset(line.terminal, "Pset_ManufacturerTypeInformation", {"Manufacturer": "ACME"})


def test_all_properties_present(schema):
    line = ventilation_line(schema)
    complete(line)
    assert check(line.view()) == []


def test_missing_properties(schema):
    line = ventilation_line(schema)
    line.builder.pset(line.terminal, "Other", {"Note": "x"})

    [issue] = check(line.view())
    assert issue.rule_id == "MEP-003"
    assert issue.severity is Severity.WARNING
    assert issue.guids == [line.terminal.GlobalId]
    assert issue.message.endswith("has no value for: AirFlowRate, Manufacturer.")
    assert issue.evidence["missing"] == [
        {
            "name": "AirFlowRate",
            "checked": ["Pset_AirTerminalOccurrence.AirFlowRate", "Mechanical - Flow.Flow"],
        },
        {"name": "Manufacturer", "checked": ["*.Manufacturer"]},
    ]
    assert "Other" in issue.evidence["available_psets"]


@pytest.mark.parametrize("empty", ["", "   "])
def test_empty_value_counts_as_missing(empty):
    line = ventilation_line()
    complete(line)
    line.builder.pset(line.terminal, "Vendor", {"Manufacturer": empty})
    line.builder.pset(line.terminal, "Pset_ManufacturerTypeInformation", {"Manufacturer": empty})

    [issue] = check(line.view())
    assert [m["name"] for m in issue.evidence["missing"]] == ["Manufacturer"]


def test_revit_alternative_property_set(schema):
    line = ventilation_line(schema)
    line.builder.pset(line.terminal, "Mechanical - Flow", {"Flow": 0.12})
    line.builder.pset(line.terminal, "Identity Data", {"Manufacturer": "ACME"})
    assert check(line.view()) == []


def test_type_property_set_is_inherited(schema):
    line = ventilation_line(schema)
    terminal_type = line.builder.element_type(ElementKind.AIR_TERMINAL, line.terminal)
    line.builder.pset(terminal_type, "Pset_ManufacturerTypeInformation", {"Manufacturer": "ACME"})
    line.builder.pset(line.terminal, "Pset_AirTerminalOccurrence", {"AirFlowRate": 0.12})
    assert check(line.view()) == []


def test_other_classes_are_not_checked(schema):
    line = ventilation_line(schema)
    complete(line)
    config = Config.model_validate({"required_properties": {"IfcDamper": [{"name": "X"}]}})
    assert check(line.view(), config) == []


def test_skipped_without_configuration():
    line = ventilation_line()
    assert check(line.view(), Config()) == []
