import re
from html.parser import HTMLParser

from builders import ventilation_line
from mepcheck.config import Config
from mepcheck.kinds import ElementKind
from mepcheck.report.html_report import render_html, write_html
from mepcheck.report.json_report import build_report
from mepcheck.rules import get_rules, run_rules

XSS = "<script>alert(1)</script>"


class Collector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags: list[tuple[str, dict]] = []
        self.scripts = 0

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))
        if tag == "script":
            self.scripts += 1


def report_for(line, config=None):
    config = config or Config()
    view = line.view()
    return build_report(view, config, get_rules(), run_rules(view, config))


def parse(html):
    collector = Collector()
    collector.feed(html)
    return collector


def test_self_contained_and_escaped():
    line = ventilation_line()
    line.builder.element(ElementKind.DUCT_SEGMENT, XSS, storey=line.l0)
    line.builder.add_port(line.fitting)
    report = report_for(line)
    html = render_html(report)
    page = parse(html)

    assert not any(tag == "link" for tag, _ in page.tags)
    for _, attrs in page.tags:
        for name in ("src", "href"):
            assert not re.match(r"\s*(https?:)?//", attrs.get(name) or ""), attrs
    assert page.scripts == 1  # only the inline filter/copy script
    assert XSS not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html

    for issue in report.issues:
        assert f'data-copy="{issue.guids[0]}"' in html
    options = {attrs.get("value") for tag, attrs in page.tags if tag == "option"}
    assert {"MEP-001", "MEP-004", "error", "warning", "info"} <= options
    rows = [attrs for tag, attrs in page.tags if tag == "tr" and "data-severity" in attrs]
    assert len(rows) == len(report.issues)


def test_empty_report():
    html = render_html(report_for(ventilation_line()))
    assert "No issues found." in html
    assert 'id="issues"' not in html


def test_skipped_rules_are_listed():
    html = render_html(report_for(ventilation_line()))
    assert "Skipped: MEP-003 (not configured: required_properties)" in html


def test_llm_columns_only_with_explanations(tmp_path):
    line = ventilation_line()
    line.builder.element(ElementKind.DUCT_SEGMENT, "Stray", storey=line.l0)
    report = report_for(line)
    assert "Suggested fix" not in render_html(report)

    report.issues[0].explanation = "The duct was drawn outside any system."
    report.issues[0].suggested_fix = "Connect it to N1."
    path = write_html(report, tmp_path / "nested" / "report.html")
    html = path.read_text(encoding="utf-8")
    assert "Suggested fix" in html
    assert "Connect it to N1." in html
