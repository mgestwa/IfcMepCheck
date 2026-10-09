"""MCP server that exposes the checker to AI agents over stdio: ``mepcheck mcp``.

Issues always come from the rules; the tools only load, run, describe and export.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from mepcheck import __version__
from mepcheck.config import Config, ConfigError, load_config
from mepcheck.issues import Issue, Report, Severity
from mepcheck.llm.explain import trim_psets
from mepcheck.model import ModelLoadError, ModelView
from mepcheck.report.bcf_export import write_bcf
from mepcheck.report.html_report import write_html
from mepcheck.report.json_report import build_report
from mepcheck.rules import UnknownRuleError, get_rules, run_rules
from mepcheck.rules.base import system_names

INSTRUCTIONS = """\
mepcheck checks HVAC/MEP IFC models with deterministic handover rules.
Typical flow: load_model(path) -> run_checks() -> get_issue(id) or get_element(guid)
for details -> export_bcf(path) or export_html(path).
Issues come only from the rules: describe and prioritise them, never invent new ones.
Relative paths are resolved against the server's working directory."""


@dataclass
class _Session:
    model: ModelView | None = None
    config: Config = field(default_factory=Config)
    issues: list[Issue] = field(default_factory=list)
    rule_ids: list[str] | None = None
    checked: bool = False


def create_server() -> MCPServer:
    server = MCPServer(name="mepcheck", version=__version__, instructions=INSTRUCTIONS)
    session = _Session()

    def loaded_model() -> ModelView:
        if session.model is None:
            raise ToolError("No model loaded: call load_model(path) first")
        return session.model

    def current_report() -> Report:
        model = loaded_model()
        if not session.checked:
            session.issues = run_rules(model, session.config)
            session.rule_ids, session.checked = None, True
        return build_report(model, session.config, get_rules(session.rule_ids), session.issues)

    @server.tool()
    def load_model(path: str, config_path: str | None = None) -> dict[str, Any]:
        """Load an IFC model, optionally with a YAML configuration, and summarise it:
        schema, element counts per kind, systems and storeys."""
        try:
            config = (
                load_config(config_path, rule_ids=[rule.id for rule in get_rules()])
                if config_path
                else Config()
            )
            model = ModelView.open(path)
        except (ConfigError, ModelLoadError) as exc:
            raise ToolError(str(exc)) from exc
        session.model, session.config = model, config
        session.issues, session.rule_ids, session.checked = [], None, False
        return model.summary() | {
            "configured_rules": [rule.id for rule in get_rules() if rule.is_configured(config)]
        }

    @server.tool()
    def list_rules() -> dict[str, Any]:
        """List the rules: id, title, default severity, why it matters at handover,
        IFC classes and the configuration section a rule needs (if any)."""
        return {
            "rules": [
                {
                    "id": rule.id,
                    "title": rule.title,
                    "severity": rule.severity.value,
                    "rationale": rule.rationale,
                    "applies_to": list(rule.applies_to),
                    "requires_config": rule.requires,
                }
                for rule in get_rules()
            ]
        }

    @server.tool()
    def run_checks(
        rule_ids: list[str] | None = None,
        severity: str | None = None,
        system: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Run the rules on the loaded model. Returns counts per rule and severity and
        a compact list of issues (use get_issue for evidence). Optional filters for the
        list: severity (minimum level: error, warning or info), system (part of the
        system name, case-insensitive) and limit."""
        model = loaded_model()
        try:
            issues = run_rules(model, session.config, rule_ids)
            threshold = Severity(severity.lower()).rank if severity else None
        except UnknownRuleError as exc:
            raise ToolError(str(exc)) from exc
        except ValueError as exc:
            raise ToolError(f"Unknown severity {severity!r}: use error, warning or info") from exc
        session.issues, session.rule_ids, session.checked = issues, rule_ids, True

        selected = issues
        if threshold is not None:
            selected = [issue for issue in selected if issue.severity.rank >= threshold]
        if system:
            needle = system.lower()
            selected = [issue for issue in selected if needle in (issue.system or "").lower()]
        counts: dict[str, dict[str, int]] = {}
        for issue in issues:
            per_rule = counts.setdefault(issue.rule_id, {})
            per_rule[issue.severity.value] = per_rule.get(issue.severity.value, 0) + 1
        limit = max(limit, 0)
        return {
            "total": len(issues),
            "counts": counts,
            "skipped_rules": {
                rule.id: f"not configured: {rule.requires}"
                for rule in get_rules(rule_ids)
                if not rule.is_configured(session.config)
            },
            "matching": len(selected),
            "truncated": len(selected) > limit,
            "issues": [_compact(issue) for issue in selected[:limit]],
        }

    @server.tool()
    def get_issue(issue_id: str) -> dict[str, Any]:
        """Full details of one issue from the last run_checks, including its evidence."""
        for issue in session.issues:
            if issue.id == issue_id:
                return issue.model_dump(mode="json")
        raise ToolError(f"Unknown issue id {issue_id}: call run_checks first")

    @server.tool()
    def get_element(guid: str) -> dict[str, Any]:
        """Details of an element by IFC GlobalId: class, kind, trimmed property sets,
        systems, storey, location, port connections and the issues that mention it."""
        model = loaded_model()
        entities = model.guid_index.get(guid)
        if not entities:
            raise ToolError(f"No entity with GlobalId {guid}")
        element = entities[0]
        storey = model.storey_of(element)
        ports = []
        if element.is_a("IfcElement"):
            for port in model.ports_of(element):
                other_port = model.connected_port(port)
                other = model.port_element(other_port) if other_port is not None else None
                ports.append(
                    {
                        "port": port.GlobalId,
                        "name": port.Name,
                        "flow_direction": port.FlowDirection,
                        "connected_to": None
                        if other is None
                        else {
                            "guid": other.GlobalId,
                            "ifc_class": other.is_a(),
                            "name": other.Name,
                        },
                    }
                )
        return {
            "guid": guid,
            "ifc_class": element.is_a(),
            "ifc4_class": model.ifc4_class(element),
            "kind": model.kind_of(element),
            "name": getattr(element, "Name", None),
            "storey": storey.Name if storey is not None else None,
            "systems": system_names(model, session.config, element),
            "location_m": model.location_m(element),
            "property_sets": trim_psets(model.psets_of(element))
            if element.is_a("IfcObjectDefinition")
            else {},
            "ports": ports,
            "issues": [issue.id for issue in session.issues if guid in issue.guids],
            "entities_with_this_guid": len(entities),
        }

    @server.tool()
    def export_bcf(path: str) -> dict[str, Any]:
        """Write the issues of the last run_checks (or of all rules) to a BCF 2.1 file
        (.bcf or .bcfzip) with one topic per issue."""
        if not path.lower().endswith((".bcf", ".bcfzip")):
            raise ToolError("The BCF path must end with .bcf or .bcfzip")
        report = current_report()
        return {"path": str(write_bcf(report, path).resolve()), "topics": len(report.issues)}

    @server.tool()
    def export_html(path: str) -> dict[str, Any]:
        """Write the issues of the last run_checks (or of all rules) to a self-contained
        HTML report (.html)."""
        if not path.lower().endswith((".html", ".htm")):
            raise ToolError("The HTML path must end with .html")
        report = current_report()
        return {"path": str(write_html(report, path).resolve()), "issues": len(report.issues)}

    return server


def _compact(issue: Issue) -> dict[str, Any]:
    return {
        "id": issue.id,
        "rule_id": issue.rule_id,
        "severity": issue.severity.value,
        "message": issue.message,
        "guids": issue.guids,
        "element_name": issue.element_name,
        "system": issue.system,
        "storey": issue.storey,
    }


def main() -> None:
    create_server().run("stdio")


if __name__ == "__main__":
    main()
