import asyncio
import json
import sys

import pytest
from mcp.client.client import Client
from mcp.client.stdio import StdioServerParameters

from builders import ventilation_line
from mepcheck.kinds import ElementKind
from mepcheck.mcp_server import create_server

TOOLS = {
    "load_model",
    "list_rules",
    "run_checks",
    "get_issue",
    "get_element",
    "export_bcf",
    "export_html",
}


async def call(client, name, **arguments):
    """(is_error, payload): the JSON result, or the error text."""
    result = await client.call_tool(name, arguments)
    text = result.content[0].text
    return result.is_error, text if result.is_error else json.loads(text)


@pytest.fixture
def model_path(tmp_path):
    """MEP-001 (stray duct, no system) and MEP-004 (open port on the elbow, in N1)."""
    line = ventilation_line()
    line.builder.element(ElementKind.DUCT_SEGMENT, "Stray", storey=line.l0, at=(8, 0, 2.8))
    line.builder.add_port(line.fitting, name="Open branch")
    path = line.builder.write(tmp_path / "model.ifc")
    return path, line.fitting.GlobalId


def test_tools_are_listed():
    async def main():
        async with Client(create_server()) as client:
            return {tool.name for tool in (await client.list_tools()).tools}

    assert asyncio.run(main()) == TOOLS


def test_workflow(tmp_path, model_path):
    path, fitting_guid = model_path

    async def main():
        async with Client(create_server()) as client:
            results = {"load": await call(client, "load_model", path=str(path))}
            results["rules"] = await call(client, "list_rules")
            results["all"] = await call(client, "run_checks")
            results["errors"] = await call(client, "run_checks", severity="error")
            results["n1"] = await call(client, "run_checks", system="n1")
            results["limited"] = await call(client, "run_checks", limit=1)
            first_id = results["all"][1]["issues"][0]["id"]
            results["issue"] = await call(client, "get_issue", issue_id=first_id)
            results["element"] = await call(client, "get_element", guid=fitting_guid)
            results["bcf"] = await call(client, "export_bcf", path=str(tmp_path / "out.bcf"))
            results["html"] = await call(client, "export_html", path=str(tmp_path / "out.html"))
            return results

    results = asyncio.run(main())
    assert not any(is_error for is_error, _ in results.values()), results

    summary = results["load"][1]
    assert summary["schema"] == "IFC4"
    assert summary["systems"] == ["N1"]
    assert summary["elements"]["duct_segment"] == 3
    assert "MEP-003" not in summary["configured_rules"]
    assert {rule["id"] for rule in results["rules"][1]["rules"]} >= {"MEP-001", "MEP-008"}

    checks = results["all"][1]
    assert checks["total"] == 2
    assert checks["counts"] == {"MEP-001": {"error": 1}, "MEP-004": {"warning": 1}}
    assert set(checks["skipped_rules"]) == {"MEP-003", "MEP-005"}
    assert "evidence" not in checks["issues"][0]
    assert [i["rule_id"] for i in results["errors"][1]["issues"]] == ["MEP-001"]
    assert [i["rule_id"] for i in results["n1"][1]["issues"]] == ["MEP-004"]
    assert results["limited"][1]["truncated"] is True
    assert results["issue"][1]["evidence"]

    element = results["element"][1]
    assert element["ifc4_class"] == "IfcDuctFitting"
    assert element["systems"] == ["N1"]
    assert element["storey"] == "L0"
    assert [port["connected_to"] is None for port in element["ports"]] == [False, False, True]
    assert len(element["issues"]) == 1

    assert results["bcf"][1]["topics"] == 2
    assert (tmp_path / "out.bcf").exists()
    assert (tmp_path / "out.html").read_text(encoding="utf-8").startswith("<!doctype html>")


def test_errors(tmp_path, model_path):
    path, _ = model_path
    config = tmp_path / "rules.yaml"
    config.write_text("storey_tolerance_m: -1\n", encoding="utf-8")

    async def main():
        async with Client(create_server()) as client:
            errors = [
                await call(client, "run_checks"),
                await call(client, "load_model", path=str(tmp_path / "missing.ifc")),
                await call(client, "load_model", path=str(path), config_path=str(config)),
            ]
            await call(client, "load_model", path=str(path))
            errors += [
                await call(client, "get_issue", issue_id="unknown"),
                await call(client, "get_element", guid="0000000000000000000000"),
                await call(client, "run_checks", rule_ids=["MEP-999"]),
                await call(client, "run_checks", severity="critical"),
                await call(client, "export_bcf", path=str(tmp_path / "out.txt")),
                await call(client, "export_html", path=str(tmp_path / "out.txt")),
            ]
            return errors

    errors = asyncio.run(main())
    assert all(is_error for is_error, _ in errors), errors
    messages = [text for _, text in errors]
    assert "No model loaded" in messages[0]
    assert "File not found" in messages[1]
    assert "storey_tolerance_m" in messages[2]
    assert "Unknown issue id" in messages[3]
    assert "No entity with GlobalId" in messages[4]
    assert "MEP-999" in messages[5]
    assert "Unknown severity" in messages[6]


def test_export_without_run_checks_runs_all_rules(tmp_path, model_path):
    path, _ = model_path

    async def main():
        async with Client(create_server()) as client:
            await call(client, "load_model", path=str(path))
            return await call(client, "export_bcf", path=str(tmp_path / "all.bcf"))

    is_error, result = asyncio.run(main())
    assert not is_error
    assert result["topics"] == 2


def test_stdio_end_to_end(model_path):
    """A real MCP client talking to `python -m mepcheck mcp` over stdio."""
    path, _ = model_path
    server = StdioServerParameters(command=sys.executable, args=["-m", "mepcheck", "mcp"])

    async def main():
        async with Client(server) as client:
            rules = await call(client, "list_rules")
            loaded = await call(client, "load_model", path=str(path))
            checks = await call(client, "run_checks")
            return rules, loaded, checks

    rules, loaded, checks = asyncio.run(main())
    assert len(rules[1]["rules"]) == 7
    assert loaded[1]["schema"] == "IFC4"
    assert checks[1]["total"] == 2
