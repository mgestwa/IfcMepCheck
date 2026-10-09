import logging

import pytest

from builders import ventilation_line
from fake_llm import FakeLLM, echo_answer
from mepcheck.config import Config
from mepcheck.kinds import ElementKind
from mepcheck.llm.client import ExplanationItem, LLMError, ResponseCache
from mepcheck.llm.explain import MAX_PROPERTIES, MAX_PSETS, MAX_TEXT, explain_report
from mepcheck.report.json_report import build_report
from mepcheck.rules import get_rules, run_rules


def make_report(strays=1, open_ports=1):
    """``strays`` MEP-001 errors and ``open_ports`` MEP-004 warnings."""
    line = ventilation_line()
    for number in range(strays):
        line.builder.element(ElementKind.DUCT_SEGMENT, f"Stray {number}", storey=line.l0)
    for element in [line.fitting, line.duct_a, line.duct_b][:open_ports]:
        line.builder.add_port(element)
    view = line.view()
    return line, build_report(view, Config(), get_rules(), run_rules(view, Config()))


def test_explanations_are_added():
    _, report = make_report()
    llm = FakeLLM()
    stats = explain_report(report, llm)

    assert stats.explained == len(report.issues) == 2
    assert all(issue.explanation and issue.suggested_fix for issue in report.issues)
    [(system, contexts)] = llm.calls
    assert "Write in English." in system
    assert "Never add" in system
    mep001 = next(c for c in contexts if c["rule"]["id"] == "MEP-001")
    assert mep001["rule"]["why_it_matters"].startswith("Every distribution element")
    assert mep001["evidence"] == {"kind": "duct_segment"}
    assert "property_sets" not in mep001["element"]  # no IFC model given


def test_llm_cannot_add_or_drop_issues(caplog):
    _, report = make_report()
    ids = [issue.id for issue in report.issues]

    def bad_answer(contexts):
        first = echo_answer(contexts)[0]
        return [
            first,
            first,  # repeated
            ExplanationItem(
                issue_id="00000000-0000-0000-0000-000000000000", explanation="x", suggested_fix="y"
            ),
        ]

    with caplog.at_level(logging.WARNING):
        stats = explain_report(report, FakeLLM(bad_answer))

    assert [issue.id for issue in report.issues] == ids
    assert (stats.explained, stats.rejected, stats.failed) == (1, 2, 1)
    assert report.issues[1].explanation is None
    assert "Rejected 2 LLM answers" in caplog.text


def test_empty_answers_are_rejected():
    _, report = make_report(open_ports=0)
    llm = FakeLLM(
        lambda contexts: [
            ExplanationItem(issue_id=contexts[0]["issue_id"], explanation=" ", suggested_fix="y")
        ]
    )
    stats = explain_report(report, llm)
    assert (stats.explained, stats.rejected) == (0, 1)
    assert report.issues[0].explanation is None


def test_llm_error_keeps_report_without_explanations(caplog):
    _, report = make_report()
    with caplog.at_level(logging.WARNING):
        stats = explain_report(report, FakeLLM(error=LLMError("quota exceeded")))
    assert stats.failed == 2
    assert all(issue.explanation is None for issue in report.issues)
    assert "quota exceeded" in caplog.text


def test_cache_makes_reruns_free(tmp_path):
    cache = ResponseCache(tmp_path)
    _, report = make_report()
    unexplained = report.model_copy(deep=True)  # what a new check of the same file gives
    explain_report(report, FakeLLM(), cache=cache)

    again = unexplained.model_copy(deep=True)
    llm = FakeLLM()
    stats = explain_report(again, llm, cache=cache)
    assert llm.calls == []
    assert stats.cached == 2
    assert [(i.explanation, i.suggested_fix) for i in again.issues] == [
        (i.explanation, i.suggested_fix) for i in report.issues
    ]

    polish = FakeLLM()
    explain_report(unexplained.model_copy(deep=True), polish, cache=cache, lang="pl")
    assert len(polish.calls) == 1
    assert "Write in Polish." in polish.calls[0][0]


def test_max_issues_and_batches():
    _, report = make_report(strays=3, open_ports=2)
    llm = FakeLLM()
    stats = explain_report(report, llm, max_issues=3, batch_size=2)

    assert (stats.explained, stats.skipped) == (3, 2)
    assert [len(contexts) for _, contexts in llm.calls] == [2, 1]
    explained = [issue for issue in report.issues if issue.explanation]
    assert {issue.rule_id for issue in explained} == {"MEP-001"}  # errors first


def test_explained_issues_are_skipped_unless_forced():
    _, report = make_report()
    report.issues[0].explanation = "kept"
    report.issues[0].suggested_fix = "kept"
    llm = FakeLLM()
    explain_report(report, llm)
    assert len(llm.calls[0][1]) == 1
    assert report.issues[0].explanation == "kept"

    explain_report(report, llm, force=True)
    assert len(llm.calls[1][1]) == 2


def test_ifc_model_adds_trimmed_property_sets():
    line, report = make_report(strays=1, open_ports=0)
    builder = line.builder
    [stray] = [e for e in builder.file.by_type("IfcElement") if e.Name == "Stray 0"]
    builder.pset(stray, "A text", {"Long": "x" * 200})
    builder.pset(stray, "Big", {f"P{n:02}": n for n in range(30)})
    for number in range(10):
        builder.pset(stray, f"Extra {number}", {"Value": number})
    llm = FakeLLM()
    explain_report(report, llm, model=line.view())

    psets = llm.calls[0][1][0]["element"]["property_sets"]
    assert len(psets) == MAX_PSETS
    assert len(psets["Big"]) == MAX_PROPERTIES
    assert psets["A text"] == {"Long": "x" * MAX_TEXT}
    assert all("id" not in properties for properties in psets.values())


def test_unknown_language():
    _, report = make_report()
    with pytest.raises(ValueError, match="Unsupported language"):
        explain_report(report, FakeLLM(), lang="de")
