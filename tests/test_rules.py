import pytest

from builders import ventilation_line
from mepcheck.config import Config
from mepcheck.issues import Severity
from mepcheck.kinds import ElementKind
from mepcheck.rules import UnknownRuleError, get_rules, run_rules


def test_valid_model_has_no_issues(schema):
    assert run_rules(ventilation_line(schema).view(), Config()) == []


def test_every_rule_has_metadata():
    for rule in get_rules():
        assert rule.id.startswith("MEP-")
        assert rule.title
        assert len(rule.rationale) > 40
        assert rule.applies_to


def test_rule_ids_are_normalised():
    assert [rule.id for rule in get_rules([" mep-001 ", "MEP-001", ""])] == ["MEP-001"]


def test_unknown_rule_id():
    with pytest.raises(UnknownRuleError, match="MEP-999"):
        get_rules(["MEP-999"])


def test_unknown_rule_in_severity_overrides():
    config = Config(severity_overrides={"MEP-999": Severity.INFO})
    with pytest.raises(UnknownRuleError, match="MEP-999"):
        run_rules(ventilation_line().view(), config)


def test_severity_override():
    line = ventilation_line()
    line.builder.element(ElementKind.DUCT_SEGMENT, "Stray duct", storey=line.l0)
    config = Config(severity_overrides={"MEP-001": Severity.INFO})
    issues = run_rules(line.view(), config, ["MEP-001"])
    assert [issue.severity for issue in issues] == [Severity.INFO]
