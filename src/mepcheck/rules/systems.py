"""System rules: MEP-001."""

from __future__ import annotations

from mepcheck.config import Config
from mepcheck.issues import Issue, Severity
from mepcheck.kinds import HVAC_CLASSES
from mepcheck.model import ModelView
from mepcheck.rules.base import Rule, element_label, register

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


@register(MEP_001)
def check_unassigned_system(model: ModelView, config: Config) -> list[Issue]:
    return [
        MEP_001.issue(
            model,
            element,
            message=f"{element_label(element)} is not assigned to any distribution system.",
            evidence={"kind": kind},
        )
        for element, kind in model.elements
        if not model.systems_of(element)
    ]
