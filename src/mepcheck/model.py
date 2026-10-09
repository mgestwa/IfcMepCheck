"""Load an IFC model and build the indexes shared by all rules."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any

import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.placement
import ifcopenshell.util.system
import ifcopenshell.util.unit

from mepcheck.kinds import SUPPORTED_SCHEMAS, ElementKind, element_kind, is_distribution_system

Entity = ifcopenshell.entity_instance


class ModelLoadError(Exception):
    """The file cannot be read or uses an unsupported IFC schema."""


@dataclass(frozen=True)
class Storey:
    entity: Entity
    name: str | None
    elevation_m: float
    building_id: int | None


class ModelView:
    """Read-only view of an IFC model.

    Indexes are built lazily, once per model, so rules never repeat a full
    scan. All lengths and coordinates returned here are in metres.
    """

    def __init__(self, ifc_file: ifcopenshell.file, source: str | None = None) -> None:
        if ifc_file.schema not in SUPPORTED_SCHEMAS:
            supported = ", ".join(SUPPORTED_SCHEMAS)
            raise ModelLoadError(
                f"Unsupported IFC schema {ifc_file.schema} (supported: {supported})"
            )
        self.file = ifc_file
        self.source = source
        self.schema: str = ifc_file.schema
        self.length_scale: float = float(ifcopenshell.util.unit.calculate_unit_scale(ifc_file))
        self._systems: dict[int, list[Entity]] = {}
        self._ports: dict[int, list[Entity]] = {}
        self._connected: dict[int, Entity | None] = {}

    @classmethod
    def open(cls, path: str | Path) -> ModelView:
        path = Path(path)
        try:
            ifc_file = ifcopenshell.open(str(path))
        except FileNotFoundError as exc:
            raise ModelLoadError(f"File not found: {path}") from exc
        except (ifcopenshell.Error, OSError) as exc:
            raise ModelLoadError(f"Cannot read IFC file {path}: {exc}") from exc
        return cls(ifc_file, source=path.name)

    @cached_property
    def elements(self) -> list[tuple[Entity, ElementKind]]:
        """Elements recognised by element_kind(), in file order."""
        result = []
        for element in self.file.by_type("IfcElement"):
            kind = element_kind(element)
            if kind is not None:
                result.append((element, kind))
        return result

    @cached_property
    def guid_index(self) -> dict[str, list[Entity]]:
        """GlobalId -> entities using it, for every IfcRoot."""
        index: dict[str, list[Entity]] = defaultdict(list)
        for entity in self.file.by_type("IfcRoot"):
            if entity.GlobalId:
                index[entity.GlobalId].append(entity)
        return dict(index)

    def systems_of(self, element: Entity) -> list[Entity]:
        """Distribution systems the element is assigned to, sorted by name."""
        key = element.id()
        if key not in self._systems:
            systems: list[Entity] = []
            if element.is_a("IfcObjectDefinition"):
                systems = [
                    group
                    for group in ifcopenshell.util.system.get_element_systems(element)
                    if is_distribution_system(group)
                ]
                systems.sort(key=lambda system: (system.Name or "", system.id()))
            self._systems[key] = systems
        return self._systems[key]

    def ports_of(self, element: Entity) -> list[Entity]:
        """Ports of the element in file order (the api order is not stable in IFC4X3)."""
        key = element.id()
        if key not in self._ports:
            ports = ifcopenshell.util.system.get_ports(element)
            self._ports[key] = sorted(ports, key=lambda port: port.id())
        return self._ports[key]

    def connected_port(self, port: Entity) -> Entity | None:
        key = port.id()
        if key not in self._connected:
            self._connected[key] = ifcopenshell.util.system.get_connected_port(port)
        return self._connected[key]

    @cached_property
    def storeys(self) -> list[Storey]:
        """All building storeys, sorted by elevation."""
        result = []
        for entity in self.file.by_type("IfcBuildingStorey"):
            elevation = ifcopenshell.util.placement.get_storey_elevation(entity)
            building = ifcopenshell.util.element.get_aggregate(entity)
            result.append(
                Storey(
                    entity=entity,
                    name=entity.Name,
                    elevation_m=round(float(elevation) * self.length_scale, 3),
                    building_id=building.id() if building is not None else None,
                )
            )
        result.sort(key=lambda storey: (storey.elevation_m, storey.name or ""))
        return result

    @cached_property
    def _storey_levels(self) -> dict[int, list[Storey]]:
        by_building: dict[int | None, list[Storey]] = defaultdict(list)
        for storey in self.storeys:
            by_building[storey.building_id].append(storey)
        return {storey.entity.id(): by_building[storey.building_id] for storey in self.storeys}

    def storey_levels(self, storey: Entity) -> list[Storey]:
        """Storeys of the same building as ``storey``, sorted by elevation."""
        return self._storey_levels[storey.id()]

    def storey_of(self, element: Entity) -> Entity | None:
        """Building storey containing the element, also through spaces or aggregates."""
        if not element.is_a("IfcProduct"):
            return None
        return ifcopenshell.util.element.get_container(element, ifc_class="IfcBuildingStorey")

    def location_m(self, element: Entity) -> tuple[float, float, float] | None:
        """Absolute insertion point in metres, rounded to millimetres."""
        placement = getattr(element, "ObjectPlacement", None)
        if placement is None or not placement.is_a("IfcLocalPlacement"):
            return None
        matrix = ifcopenshell.util.placement.get_local_placement(placement)
        x, y, z = (round(float(value) * self.length_scale, 3) for value in matrix[:3, 3])
        return (x, y, z)

    def summary(self) -> dict[str, Any]:
        kinds = Counter(str(kind) for _, kind in self.elements)
        systems = sorted(
            system.Name or f"#{system.id()}"
            for system in self.file.by_type("IfcSystem")
            if is_distribution_system(system)
        )
        return {
            "source": self.source,
            "schema": self.schema,
            "length_scale": self.length_scale,
            "elements": dict(sorted(kinds.items())),
            "systems": systems,
            "storeys": [storey.name for storey in self.storeys],
        }
