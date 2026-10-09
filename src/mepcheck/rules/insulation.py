"""Insulation rules: MEP-005."""

from __future__ import annotations

import re

import ifcopenshell.util.element

from mepcheck.config import Config
from mepcheck.issues import Issue, Severity
from mepcheck.model import Entity, ModelView
from mepcheck.rules.base import Rule, element_label, register, system_names

MEP_005 = Rule(
    id="MEP-005",
    title="Missing insulation",
    rationale=(
        "Supply and outdoor air ducts have to be insulated against heat loss and "
        "condensation. Insulation missing in the model means missing quantities and "
        "clearances in coordination, and often a gap on site."
    ),
    severity=Severity.WARNING,
    applies_to=("IfcDuctSegment", "IfcDuctFitting"),
    requires="insulation",
)


@register(MEP_005)
def check_insulation(model: ModelView, config: Config) -> list[Issue]:
    settings = config.insulation
    if settings is None:
        return []
    patterns = [re.compile(pattern) for pattern in settings.required_for_system_names]
    accepted = {name.upper() for name in settings.covering_types}
    issues = []
    for element, kind in model.elements:
        if model.ifc4_class(element) not in settings.classes:
            continue
        systems = [
            name
            for name in system_names(model, config, element)
            if any(pattern.search(name) for pattern in patterns)
        ]
        if not systems:
            continue
        coverings = covering_types(element)
        if accepted & set(coverings):
            continue
        label = element_label(element)
        issues.append(
            MEP_005.issue(
                model,
                config,
                element,
                message=f"{label} in system {', '.join(systems)} has no insulation.",
                evidence={
                    "kind": kind,
                    "systems": systems,
                    "patterns": [p.pattern for p in patterns if any(p.search(s) for s in systems)],
                    "coverings": coverings,
                },
            )
        )
    return issues


def covering_types(element: Entity) -> list[str]:
    """Predefined types of the coverings attached via IfcRelCoversBldgElements."""
    result = []
    for rel in getattr(element, "HasCoverings", None) or ():
        for covering in rel.RelatedCoverings or ():
            result.append(ifcopenshell.util.element.get_predefined_type(covering) or "NOTDEFINED")
    return sorted(result)
