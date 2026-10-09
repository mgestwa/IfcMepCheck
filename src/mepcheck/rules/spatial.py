"""Spatial rules: MEP-008."""

from __future__ import annotations

from mepcheck.config import Config
from mepcheck.issues import Issue, Severity
from mepcheck.kinds import HVAC_CLASSES
from mepcheck.model import ModelView, Storey
from mepcheck.rules.base import Rule, element_label, register

MEP_008 = Rule(
    id="MEP-008",
    title="Missing or wrong storey",
    rationale=(
        "Elements have to be contained in the storey they physically sit on: quantity "
        "take-off, filtering and handover by floor all depend on it. A wrong storey is "
        "a common Revit export problem, because elements keep the storey of their "
        "reference level instead of the one matching their position."
    ),
    severity=Severity.WARNING,
    applies_to=HVAC_CLASSES,
)


@register(MEP_008)
def check_storey(model: ModelView, config: Config) -> list[Issue]:
    tolerance = config.storey_tolerance_m
    issues = []
    for element, kind in model.elements:
        storey = model.storey_of(element)
        if storey is None:
            issues.append(
                MEP_008.issue(
                    model,
                    element,
                    message=f"{element_label(element)} is not contained in any building storey.",
                    evidence={"check": "no_storey", "kind": kind},
                )
            )
            continue

        location = model.location_m(element)
        if location is None:
            continue
        z = location[2]
        levels = model.storey_levels(storey)
        elevation = next(level.elevation_m for level in levels if level.entity.id() == storey.id())
        next_elevation = min(
            (level.elevation_m for level in levels if level.elevation_m > elevation), default=None
        )
        lower = round(elevation - tolerance, 3)
        upper = None if next_elevation is None else round(next_elevation + tolerance, 3)
        if lower <= z and (upper is None or z < upper):
            continue

        expected = _storey_at(levels, z)
        allowed = f"{lower:.2f} m and above" if upper is None else f"{lower:.2f} to {upper:.2f} m"
        message = (
            f"{element_label(element)} is at elevation {z:.2f} m, outside storey "
            f"'{storey.Name}' ({allowed} including tolerance)."
        )
        if expected is not None:
            message += f" Expected storey: '{expected.name}'."
        issues.append(
            MEP_008.issue(
                model,
                element,
                message=message,
                evidence={
                    "check": "elevation",
                    "kind": kind,
                    "element_z_m": z,
                    "storey_elevation_m": elevation,
                    "next_storey_elevation_m": next_elevation,
                    "tolerance_m": tolerance,
                    "expected_storey": expected.name if expected is not None else None,
                },
            )
        )
    return issues


def _storey_at(levels: list[Storey], z: float) -> Storey | None:
    """The highest storey at or below ``z``; None below the lowest storey."""
    below = [level for level in levels if level.elevation_m <= z]
    return below[-1] if below else None
