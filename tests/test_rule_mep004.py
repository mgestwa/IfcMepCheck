from builders import ventilation_line
from mepcheck.config import Config
from mepcheck.issues import Severity
from mepcheck.kinds import ElementKind
from mepcheck.rules import run_rules


def check(view):
    return run_rules(view, Config(), ["MEP-004"])


def test_all_ports_connected(schema):
    assert check(ventilation_line(schema).view()) == []


def test_open_port_reported_once_per_element(schema):
    line = ventilation_line(schema)
    first = line.builder.add_port(line.fitting, name="Branch 1")
    second = line.builder.add_port(line.fitting, name="Branch 2")

    [issue] = check(line.view())
    assert issue.rule_id == "MEP-004"
    assert issue.severity is Severity.WARNING
    assert issue.guids == [line.fitting.GlobalId]
    assert issue.system == "N1"
    assert issue.message == f"{line.fitting.is_a()} 'Elbow': 2 of 4 ports are not connected."
    assert issue.evidence["total_ports"] == 4
    assert [p["guid"] for p in issue.evidence["open_ports"]] == [first.GlobalId, second.GlobalId]


def test_issue_id_survives_fixing_another_issue(schema):
    line = ventilation_line(schema)
    line.builder.add_port(line.fitting)
    terminal_port = line.builder.add_port(line.terminal)
    before = {issue.guids[0]: issue.id for issue in check(line.view())}
    assert set(before) == {line.fitting.GlobalId, line.terminal.GlobalId}

    # Fix the terminal only: connect its open port to a new duct.
    extension = line.builder.element(
        ElementKind.DUCT_SEGMENT, "Extension", storey=line.l0, system=line.system
    )
    line.builder.connect_ports(terminal_port, line.builder.add_port(extension))
    after = {issue.guids[0]: issue.id for issue in check(line.view())}

    assert after == {line.fitting.GlobalId: before[line.fitting.GlobalId]}
