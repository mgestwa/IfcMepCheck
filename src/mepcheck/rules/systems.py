"""System rules: MEP-001, MEP-006."""

from __future__ import annotations

from mepcheck.config import Config
from mepcheck.issues import Issue, Severity
from mepcheck.kinds import HVAC_CLASSES
from mepcheck.model import ModelView
from mepcheck.rules.base import (
    Rule,
    element_label,
    property_system_names,
    register,
    system_names,
)

MEP_001 = Rule(
    id="MEP-001",
    title="Element not assigned to a system",
    rationale=(
        "Every distribution element has to belong to a system, otherwise airflow, "
        "sizing and system-based schedules for commissioning and handover cannot be "
        "traced. It usually means the element was drawn outside any system or lost "
        "its system on export."
    ),
    severity=Severity.ERROR,
    applies_to=HVAC_CLASSES,
)

MEP_006 = Rule(
    id="MEP-006",
    title="Connection between different systems",
    rationale=(
        "Connected elements should belong to the same system. A connection across "
        "systems usually means a mis-assigned element or two systems joined by "
        "mistake, which breaks system-based flow calculations, schedules and "
        "commissioning by system."
    ),
    severity=Severity.ERROR,
    applies_to=HVAC_CLASSES,
)


@register(MEP_001)
def check_unassigned_system(model: ModelView, config: Config) -> list[Issue]:
    issues = []
    for element, kind in model.elements:
        if model.systems_of(element):
            continue
        message = f"{element_label(element)} is not assigned to any distribution system."
        evidence: dict = {"kind": kind}
        from_properties = property_system_names(model, config, element)
        if from_properties:
            message += (
                f" Its system is stored only as a property ({', '.join(from_properties)}); "
                "export IFC systems from the authoring tool."
            )
            evidence["system_names_from_properties"] = from_properties
        issues.append(MEP_001.issue(model, config, element, message=message, evidence=evidence))
    return issues


@register(MEP_006)
def check_cross_system_connections(model: ModelView, config: Config) -> list[Issue]:
    issues = []
    seen: set[tuple[int, int]] = set()
    for element, _ in model.elements:
        for port in model.ports_of(element):
            other_port = model.connected_port(port)
            other = model.port_element(other_port) if other_port is not None else None
            if other is None or other.id() == element.id() or model.kind_of(other) is None:
                continue
            pair = (min(element.id(), other.id()), max(element.id(), other.id()))
            if pair in seen:
                continue
            seen.add(pair)

            names = system_names(model, config, element)
            other_names = system_names(model, config, other)
            # Elements without any system are reported by MEP-001.
            if not names or not other_names or set(names) & set(other_names):
                continue
            (first, first_names, first_port), (second, second_names, second_port) = sorted(
                [(element, names, port), (other, other_names, other_port)],
                key=lambda entry: entry[0].id(),
            )
            issues.append(
                MEP_006.issue(
                    model,
                    config,
                    first,
                    message=(
                        f"{element_label(first)} ({', '.join(first_names)}) is connected to "
                        f"{element_label(second)} ({', '.join(second_names)}), "
                        "but they share no system."
                    ),
                    evidence={
                        "elements": [
                            {
                                "guid": entity.GlobalId,
                                "ifc_class": entity.is_a(),
                                "name": entity.Name,
                                "systems": entity_names,
                                "port": entity_port.GlobalId,
                            }
                            for entity, entity_names, entity_port in (
                                (first, first_names, first_port),
                                (second, second_names, second_port),
                            )
                        ]
                    },
                    guids=[first.GlobalId, second.GlobalId],
                )
            )
    return issues
