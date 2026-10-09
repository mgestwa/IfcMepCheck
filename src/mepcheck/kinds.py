"""Element kinds: one vocabulary for IFC2x3, IFC4 and IFC4X3 classes.

IFC4 has dedicated occurrence classes (IfcDuctSegment, IfcAirTerminal, ...).
IFC2x3 only has generic ones (IfcFlowSegment, IfcFlowTerminal, ...) and the
kind is carried by the type object (IfcDuctSegmentType, ...). Rules use
element_kind() only, so they never deal with the schema difference.
"""

from __future__ import annotations

from enum import StrEnum

import ifcopenshell
import ifcopenshell.util.element

SUPPORTED_SCHEMAS = ("IFC2X3", "IFC4", "IFC4X3")


class ElementKind(StrEnum):
    AIR_TERMINAL = "air_terminal"
    DUCT_SEGMENT = "duct_segment"
    DUCT_FITTING = "duct_fitting"
    DUCT_ACCESSORY = "duct_accessory"
    HVAC_EQUIPMENT = "hvac_equipment"


# IFC4/IFC4X3 occurrence classes per kind. Other disciplines (piping,
# electrical) are added here without touching the rules.
OCCURRENCE_CLASSES: dict[ElementKind, tuple[str, ...]] = {
    ElementKind.AIR_TERMINAL: ("IfcAirTerminal",),
    ElementKind.DUCT_SEGMENT: ("IfcDuctSegment",),
    ElementKind.DUCT_FITTING: ("IfcDuctFitting",),
    ElementKind.DUCT_ACCESSORY: ("IfcDamper", "IfcDuctSilencer", "IfcAirTerminalBox"),
    ElementKind.HVAC_EQUIPMENT: ("IfcFan", "IfcUnitaryEquipment", "IfcAirToAirHeatRecovery"),
}

# Type classes exist in all supported schemas, so they also cover IFC2x3.
TYPE_CLASSES: dict[ElementKind, tuple[str, ...]] = {
    kind: tuple(f"{name}Type" for name in classes) for kind, classes in OCCURRENCE_CLASSES.items()
}

HVAC_CLASSES: tuple[str, ...] = tuple(
    name for classes in OCCURRENCE_CLASSES.values() for name in classes
)

_KIND_BY_CLASS = {name: kind for kind, names in OCCURRENCE_CLASSES.items() for name in names}
_CLASS_BY_TYPE = {f"{name}Type": name for name in HVAC_CLASSES}

# IfcSystem subclasses that group elements for other purposes than distribution.
_NON_DISTRIBUTION_GROUPS = frozenset(
    {"IfcZone", "IfcStructuralAnalysisModel", "IfcBuildingSystem", "IfcBuiltSystem"}
)


def classify(element: ifcopenshell.entity_instance) -> tuple[ElementKind, str] | None:
    """Kind and IFC4 class of an element, by its class, then by its type; else None.

    The IFC4 class lets configuration name classes once for all schemas: an
    IFC2x3 IfcFlowTerminal typed by IfcAirTerminalType is an "IfcAirTerminal".
    """
    ifc_class = element.is_a()
    if ifc_class not in _KIND_BY_CLASS:
        element_type = ifcopenshell.util.element.get_type(element)
        ifc_class = _CLASS_BY_TYPE.get(element_type.is_a()) if element_type is not None else None
        if ifc_class is None:
            return None
    return _KIND_BY_CLASS[ifc_class], ifc_class


def element_kind(element: ifcopenshell.entity_instance) -> ElementKind | None:
    """Return the kind of an element by its class, then by its type, else None."""
    result = classify(element)
    return result[0] if result is not None else None


def is_distribution_system(group: ifcopenshell.entity_instance) -> bool:
    """True for IfcSystem / IfcDistributionSystem, False for zones and other groups."""
    return group.is_a("IfcSystem") and group.is_a() not in _NON_DISTRIBUTION_GROUPS
