import pytest

from builders import ventilation_line
from mepcheck.config import Config
from mepcheck.issues import Severity
from mepcheck.kinds import ElementKind
from mepcheck.rules import run_rules


def check(view, config=None):
    return run_rules(view, config or Config(), ["MEP-008"])


def add_terminal(line, *, z, storey="l0"):
    """A connected diffuser in N1, so only MEP-008 can report it."""
    terminal = line.builder.element(
        ElementKind.AIR_TERMINAL,
        "Test diffuser",
        storey=getattr(line, storey) if storey else None,
        system=line.system,
        at=(2, 6, z),
    )
    line.builder.connect(line.duct_b, terminal)
    return terminal


def test_elements_on_their_storey(schema):
    assert check(ventilation_line(schema).view()) == []


def test_element_without_storey(schema):
    line = ventilation_line(schema)
    terminal = add_terminal(line, z=2.6, storey=None)

    [issue] = check(line.view())
    assert issue.rule_id == "MEP-008"
    assert issue.severity is Severity.WARNING
    assert issue.guids == [terminal.GlobalId]
    assert issue.storey is None
    assert issue.evidence == {"check": "no_storey", "kind": "air_terminal"}


@pytest.mark.parametrize("length_unit", ["m", "mm"])
def test_element_above_its_storey(schema, length_unit):
    line = ventilation_line(schema, length_unit)
    terminal = add_terminal(line, z=5.0)

    [issue] = check(line.view())
    assert issue.guids == [terminal.GlobalId]
    assert issue.storey == "L0"
    assert issue.location == (2.0, 6.0, 5.0)
    assert issue.evidence == {
        "check": "elevation",
        "kind": "air_terminal",
        "element_z_m": 5.0,
        "storey_elevation_m": 0.0,
        "next_storey_elevation_m": 3.5,
        "tolerance_m": 0.5,
        "expected_storey": "L1",
    }
    assert "Expected storey: 'L1'" in issue.message


def test_element_below_its_storey(schema):
    line = ventilation_line(schema)
    add_terminal(line, z=2.6, storey="l1")

    [issue] = check(line.view())
    assert issue.storey == "L1"
    assert issue.evidence["expected_storey"] == "L0"
    assert issue.evidence["next_storey_elevation_m"] is None


def test_element_below_lowest_storey():
    line = ventilation_line()
    add_terminal(line, z=-1.0)

    [issue] = check(line.view())
    assert issue.evidence["expected_storey"] is None
    assert "Expected storey" not in issue.message


@pytest.mark.parametrize(
    ("z", "tolerance", "reported"),
    [(3.9, 0.5, False), (4.1, 0.5, True), (3.6, 0.0, True), (-0.4, 0.5, False)],
)
def test_tolerance(z, tolerance, reported):
    line = ventilation_line()
    add_terminal(line, z=z)
    issues = check(line.view(), Config(storey_tolerance_m=tolerance))
    assert bool(issues) is reported


def test_top_storey_has_no_upper_limit():
    line = ventilation_line()
    add_terminal(line, z=40.0, storey="l1")
    assert check(line.view()) == []
