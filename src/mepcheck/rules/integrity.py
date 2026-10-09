"""Model integrity rules: MEP-007."""

from __future__ import annotations

from mepcheck.config import Config
from mepcheck.issues import Issue, Severity
from mepcheck.model import ModelView
from mepcheck.rules.base import Rule, register

MEP_007 = Rule(
    id="MEP-007",
    title="Duplicate GlobalId",
    rationale=(
        "GlobalId identifies an object across IFC exchanges, BCF issues and facility "
        "management handover. Duplicates make viewers select the wrong object, break "
        "model merging and issue tracking, and usually come from copied or merged "
        "elements in the authoring tool."
    ),
    severity=Severity.ERROR,
    applies_to=("IfcRoot",),
)


@register(MEP_007)
def check_duplicate_guids(model: ModelView, config: Config) -> list[Issue]:
    issues = []
    for guid, entities in model.guid_index.items():
        if len(entities) < 2:
            continue
        entities = sorted(entities, key=lambda entity: entity.id())
        classes = ", ".join(sorted({entity.is_a() for entity in entities}))
        issues.append(
            MEP_007.issue(
                model,
                entities[0],
                message=f"GlobalId {guid} is used by {len(entities)} entities ({classes}).",
                evidence={
                    "count": len(entities),
                    "entities": [
                        {
                            "step_id": entity.id(),
                            "ifc_class": entity.is_a(),
                            "name": getattr(entity, "Name", None),
                        }
                        for entity in entities
                    ],
                },
                guids=[guid],
            )
        )
    return issues
