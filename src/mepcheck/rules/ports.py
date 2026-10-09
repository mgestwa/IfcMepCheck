"""Port rules: MEP-004."""

from __future__ import annotations

from mepcheck.config import Config
from mepcheck.issues import Issue, Severity
from mepcheck.kinds import HVAC_CLASSES
from mepcheck.model import ModelView
from mepcheck.rules.base import Rule, element_label, register

MEP_004 = Rule(
    id="MEP-004",
    title="Open ports",
    rationale=(
        "An unconnected port usually means a gap in the duct network: the system is "
        "not continuous, flow and pressure calculations and system schedules become "
        "unreliable, and the gap is easy to miss during coordination."
    ),
    severity=Severity.WARNING,
    applies_to=HVAC_CLASSES,
)


@register(MEP_004)
def check_open_ports(model: ModelView, config: Config) -> list[Issue]:
    issues = []
    for element, kind in model.elements:
        ports = model.ports_of(element)
        open_ports = [port for port in ports if model.connected_port(port) is None]
        if not open_ports:
            continue
        issues.append(
            MEP_004.issue(
                model,
                element,
                message=(
                    f"{element_label(element)}: {len(open_ports)} of {len(ports)} "
                    "ports are not connected."
                ),
                evidence={
                    "kind": kind,
                    "total_ports": len(ports),
                    "open_ports": [
                        {"guid": p.GlobalId, "name": p.Name, "flow_direction": p.FlowDirection}
                        for p in open_ports
                    ],
                },
            )
        )
    return issues
