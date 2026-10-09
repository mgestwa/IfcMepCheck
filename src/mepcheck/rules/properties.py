"""Property rules: MEP-003."""

from __future__ import annotations

from mepcheck.config import Config
from mepcheck.issues import Issue, Severity
from mepcheck.kinds import HVAC_CLASSES
from mepcheck.model import ModelView
from mepcheck.rules.base import Rule, element_label, is_empty, property_values, register

MEP_003 = Rule(
    id="MEP-003",
    title="Missing required properties",
    rationale=(
        "Handover, balancing and facility management rely on design parameters such "
        "as airflow being present in the model. Missing or empty values make the "
        "model unusable for schedules and commissioning, and usually come from "
        "parameters that were not mapped on export."
    ),
    severity=Severity.WARNING,
    applies_to=HVAC_CLASSES,
    requires="required_properties",
)


@register(MEP_003)
def check_required_properties(model: ModelView, config: Config) -> list[Issue]:
    issues = []
    for element, kind in model.elements:
        requirements = config.required_properties.get(model.ifc4_class(element) or "")
        if not requirements:
            continue
        missing = [
            requirement
            for requirement in requirements
            if not any(
                not is_empty(value)
                for ref in requirement.sources()
                for value in property_values(model, element, ref)
            )
        ]
        if not missing:
            continue
        names = ", ".join(requirement.name for requirement in missing)
        issues.append(
            MEP_003.issue(
                model,
                config,
                element,
                message=f"{element_label(element)} has no value for: {names}.",
                evidence={
                    "kind": kind,
                    "missing": [
                        {
                            "name": requirement.name,
                            "checked": [str(ref) for ref in requirement.sources()],
                        }
                        for requirement in missing
                    ],
                    "available_psets": sorted(model.psets_of(element)),
                },
            )
        )
    return issues
