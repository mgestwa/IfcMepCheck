from pathlib import Path

import pytest

from mepcheck.config import Config, ConfigError, PropertyRef, load_config
from mepcheck.issues import Severity

ROOT = Path(__file__).resolve().parents[1]

SPEC_EXAMPLE = """\
storey_tolerance_m: 0.5

required_properties:
  IfcAirTerminal:
    - name: AirFlowRate
      any_of:
        - pset: Pset_AirTerminalOccurrence
          property: AirFlowRate
        - pset: Mechanical - Flow
          property: Flow

insulation:
  required_for_system_names: ['^N\\d*', '^CZ\\d*']
  classes: [IfcDuctSegment, IfcDuctFitting]

severity_overrides:
  MEP-004: info
"""


def load(tmp_path, text, **kwargs):
    path = tmp_path / "rules.yaml"
    path.write_text(text, encoding="utf-8")
    return load_config(path, **kwargs)


def error_lines(tmp_path, text, **kwargs):
    with pytest.raises(ConfigError) as info:
        load(tmp_path, text, **kwargs)
    return str(info.value).splitlines()


def test_spec_example(tmp_path):
    config = load(tmp_path, SPEC_EXAMPLE, rule_ids=["MEP-004"])
    [requirement] = config.required_properties["IfcAirTerminal"]
    assert [str(ref) for ref in requirement.sources()] == [
        "Pset_AirTerminalOccurrence.AirFlowRate",
        "Mechanical - Flow.Flow",
    ]
    assert config.insulation is not None
    assert config.insulation.required_for_system_names == [r"^N\d*", r"^CZ\d*"]
    assert config.insulation.covering_types == ["INSULATION"]
    assert config.severity_overrides == {"MEP-004": Severity.INFO}


@pytest.mark.parametrize("name", ["rules.yaml", "clinic.yaml"])
def test_shipped_examples_are_valid(name):
    load_config(ROOT / "examples" / name, rule_ids=[f"MEP-00{n}" for n in range(1, 10)])


def test_empty_file_gives_defaults(tmp_path):
    assert load(tmp_path, "") == Config()


def test_property_without_alternatives_searches_every_pset(tmp_path):
    config = load(tmp_path, "required_properties:\n  IfcAirTerminal:\n    - name: Flow\n")
    [requirement] = config.required_properties["IfcAirTerminal"]
    assert requirement.sources() == [PropertyRef(property="Flow")]


def test_yaml_syntax_error_has_line(tmp_path):
    [message] = error_lines(tmp_path, "storey_tolerance_m: 0.5\ninsulation: [unclosed\n")
    assert "rules.yaml:3: invalid YAML" in message


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("storey_tolerance_m: -1\n", "1: storey_tolerance_m: "),
        ("storey_tolerance_m: high\n", "1: storey_tolerance_m: "),
        ("\nunknown_key: 1\n", "2: unknown_key: Extra inputs are not permitted"),
        (
            "required_properties:\n  IfcWall:\n    - name: X\n",
            "2: required_properties.IfcWall: unknown IFC class 'IfcWall'",
        ),
        (
            "required_properties:\n  IfcAirTerminal:\n    - name: X\n      any_of: []\n",
            "4: required_properties.IfcAirTerminal.0.any_of: ",
        ),
        (
            "insulation:\n  required_for_system_names:\n    - '^N'\n    - '(unclosed'\n",
            "4: insulation.required_for_system_names.1: invalid regular expression",
        ),
        (
            "insulation:\n  required_for_system_names: ['^N']\n  classes: [IfcPipeSegment]\n",
            "3: insulation.classes.0: unknown IFC class 'IfcPipeSegment'",
        ),
        (
            "insulation:\n  classes: [IfcDuctSegment]\n",
            "1: insulation.required_for_system_names: Field required",
        ),
        ("severity_overrides:\n  MEP-004: critical\n", "2: severity_overrides.MEP-004: "),
        ("- a\n- b\n", "1: the configuration must be a mapping"),
    ],
)
def test_validation_errors_have_lines(tmp_path, text, expected):
    lines = error_lines(tmp_path, text)
    prefix = f"{tmp_path / 'rules.yaml'}:{expected}"
    assert any(line.startswith(prefix) for line in lines), lines


def test_all_errors_are_reported(tmp_path):
    lines = error_lines(tmp_path, "storey_tolerance_m: -1\nunknown_key: 1\n")
    assert len(lines) == 2


def test_unknown_rule_in_severity_overrides(tmp_path):
    [message] = error_lines(
        tmp_path, "severity_overrides:\n  MEP-001: info\n  MEP-999: info\n", rule_ids=["MEP-001"]
    )
    assert message.endswith("rules.yaml:3: severity_overrides.MEP-999: unknown rule id")


def test_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="Cannot read configuration"):
        load_config(tmp_path / "missing.yaml")
