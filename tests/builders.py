"""Build small IFC models with deliberate errors through ifcopenshell.api."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import ifcopenshell
import ifcopenshell.api.aggregate
import ifcopenshell.api.context
import ifcopenshell.api.geometry
import ifcopenshell.api.owner
import ifcopenshell.api.owner.settings
import ifcopenshell.api.project
import ifcopenshell.api.root
import ifcopenshell.api.spatial
import ifcopenshell.api.system
import ifcopenshell.api.type
import ifcopenshell.api.unit
import numpy as np

from mepcheck.kinds import ElementKind
from mepcheck.model import ModelView

Entity = ifcopenshell.entity_instance

# Kept independent of mepcheck.kinds on purpose, so the tests check that table.
_IFC4_CLASS = {
    ElementKind.AIR_TERMINAL: "IfcAirTerminal",
    ElementKind.DUCT_SEGMENT: "IfcDuctSegment",
    ElementKind.DUCT_FITTING: "IfcDuctFitting",
    ElementKind.DUCT_ACCESSORY: "IfcDamper",
    ElementKind.HVAC_EQUIPMENT: "IfcFan",
}
_IFC2X3_CLASS_AND_TYPE = {
    ElementKind.AIR_TERMINAL: ("IfcFlowTerminal", "IfcAirTerminalType"),
    ElementKind.DUCT_SEGMENT: ("IfcFlowSegment", "IfcDuctSegmentType"),
    ElementKind.DUCT_FITTING: ("IfcFlowFitting", "IfcDuctFittingType"),
    ElementKind.DUCT_ACCESSORY: ("IfcFlowController", "IfcDamperType"),
    ElementKind.HVAC_EQUIPMENT: ("IfcFlowMovingDevice", "IfcFanType"),
}


class ModelBuilder:
    """Project, site and building, plus helpers for storeys, systems and elements."""

    def __init__(self, schema: str = "IFC4", length_unit: str = "m") -> None:
        if length_unit not in ("m", "mm"):
            raise ValueError(f"length_unit must be 'm' or 'mm', not {length_unit!r}")
        self.schema = schema
        self.scale = 0.001 if length_unit == "mm" else 1.0
        self.file = ifcopenshell.api.project.create_file(version=schema)
        self._user: Entity | None = None
        self._application: Entity | None = None
        self._types: dict[ElementKind, Entity] = {}
        if schema == "IFC2X3":
            person = ifcopenshell.api.owner.add_person(self.file)
            organisation = ifcopenshell.api.owner.add_organisation(self.file)
            self._user = ifcopenshell.api.owner.add_person_and_organisation(
                self.file, person=person, organisation=organisation
            )
            self._application = ifcopenshell.api.owner.add_application(self.file)
        with self._owner():
            self.project = ifcopenshell.api.root.create_entity(
                self.file, ifc_class="IfcProject", name="Test project"
            )
            length = ifcopenshell.api.unit.add_si_unit(
                self.file, unit_type="LENGTHUNIT", prefix="MILLI" if length_unit == "mm" else None
            )
            ifcopenshell.api.unit.assign_unit(self.file, units=[length])
            ifcopenshell.api.context.add_context(self.file, context_type="Model")
            self.site = ifcopenshell.api.root.create_entity(self.file, ifc_class="IfcSite")
            self.building = ifcopenshell.api.root.create_entity(
                self.file, ifc_class="IfcBuilding", name="Building"
            )
            ifcopenshell.api.aggregate.assign_object(
                self.file, products=[self.site], relating_object=self.project
            )
            ifcopenshell.api.aggregate.assign_object(
                self.file, products=[self.building], relating_object=self.site
            )

    @contextmanager
    def _owner(self) -> Iterator[None]:
        """IFC2x3 requires OwnerHistory on every IfcRoot.

        The api reads the user and application from module-level settings, so
        they are patched only while this builder creates entities. A permanent
        patch would leak into every other model built in the same process.
        """
        if self._user is None:
            yield
            return
        settings = ifcopenshell.api.owner.settings
        saved = (settings.get_user, settings.get_application)
        settings.get_user = lambda _file: self._user
        settings.get_application = lambda _file: self._application
        try:
            yield
        finally:
            settings.get_user, settings.get_application = saved

    def _place(self, product: Entity, at: tuple[float, float, float]) -> None:
        matrix = np.eye(4)
        matrix[:3, 3] = at
        ifcopenshell.api.geometry.edit_object_placement(
            self.file, product=product, matrix=matrix, is_si=True
        )

    def storey(self, name: str, elevation_m: float = 0.0, building: Entity | None = None) -> Entity:
        with self._owner():
            storey = ifcopenshell.api.root.create_entity(
                self.file, ifc_class="IfcBuildingStorey", name=name
            )
            ifcopenshell.api.aggregate.assign_object(
                self.file, products=[storey], relating_object=building or self.building
            )
            self._place(storey, (0.0, 0.0, elevation_m))
            storey.Elevation = elevation_m / self.scale
        return storey

    def add_building(self, name: str) -> Entity:
        with self._owner():
            building = ifcopenshell.api.root.create_entity(
                self.file, ifc_class="IfcBuilding", name=name
            )
            ifcopenshell.api.aggregate.assign_object(
                self.file, products=[building], relating_object=self.site
            )
        return building

    def space(self, name: str, storey: Entity) -> Entity:
        with self._owner():
            space = ifcopenshell.api.root.create_entity(self.file, ifc_class="IfcSpace", name=name)
            ifcopenshell.api.aggregate.assign_object(
                self.file, products=[space], relating_object=storey
            )
        return space

    def system(self, name: str) -> Entity:
        ifc_class = "IfcSystem" if self.schema == "IFC2X3" else "IfcDistributionSystem"
        with self._owner():
            system = ifcopenshell.api.system.add_system(self.file, ifc_class=ifc_class)
            system.Name = name
        return system

    def element(
        self,
        kind: ElementKind,
        name: str,
        *,
        storey: Entity | None = None,
        system: Entity | None = None,
        at: tuple[float, float, float] = (0.0, 0.0, 0.0),
    ) -> Entity:
        """IFC4: dedicated class. IFC2x3: generic flow class with a matching type."""
        with self._owner():
            if self.schema == "IFC2X3":
                ifc_class, type_class = _IFC2X3_CLASS_AND_TYPE[kind]
                element = ifcopenshell.api.root.create_entity(
                    self.file, ifc_class=ifc_class, name=name
                )
                if kind not in self._types:
                    self._types[kind] = ifcopenshell.api.root.create_entity(
                        self.file, ifc_class=type_class, name=f"{kind} type"
                    )
                ifcopenshell.api.type.assign_type(
                    self.file, related_objects=[element], relating_type=self._types[kind]
                )
            else:
                element = ifcopenshell.api.root.create_entity(
                    self.file, ifc_class=_IFC4_CLASS[kind], name=name
                )
            if storey is not None:
                ifcopenshell.api.spatial.assign_container(
                    self.file, products=[element], relating_structure=storey
                )
            if system is not None:
                ifcopenshell.api.system.assign_system(self.file, products=[element], system=system)
            self._place(element, at)
        return element

    def add_port(self, element: Entity, name: str | None = None) -> Entity:
        with self._owner():
            port = ifcopenshell.api.system.add_port(self.file, element=element)
            port.Name = name
        return port

    def connect(self, a: Entity, b: Entity) -> tuple[Entity, Entity]:
        """Add one port to each element and connect them."""
        port_a = self.add_port(a, name=f"{a.Name} -> {b.Name}")
        port_b = self.add_port(b, name=f"{b.Name} -> {a.Name}")
        self.connect_ports(port_a, port_b)
        return port_a, port_b

    def connect_ports(self, port_a: Entity, port_b: Entity) -> None:
        with self._owner():
            ifcopenshell.api.system.connect_port(self.file, port1=port_a, port2=port_b)

    def view(self) -> ModelView:
        return ModelView(self.file, source="builder.ifc")

    def write(self, path: Path) -> Path:
        self.file.write(str(path))
        return path


@dataclass
class VentilationLine:
    builder: ModelBuilder
    l0: Entity
    l1: Entity
    system: Entity
    duct_a: Entity
    fitting: Entity
    duct_b: Entity
    terminal: Entity

    def view(self) -> ModelView:
        return self.builder.view()


def ventilation_line(schema: str = "IFC4", length_unit: str = "m") -> VentilationLine:
    """A valid supply line on L0: duct, elbow, duct and diffuser, all connected in system N1.

    No rule reports anything on this model. Tests add one deliberate error.
    """
    b = ModelBuilder(schema, length_unit)
    l0 = b.storey("L0", 0.0)
    l1 = b.storey("L1", 3.5)
    n1 = b.system("N1")
    duct_a = b.element(ElementKind.DUCT_SEGMENT, "Duct A", storey=l0, system=n1, at=(0, 0, 2.8))
    fitting = b.element(ElementKind.DUCT_FITTING, "Elbow", storey=l0, system=n1, at=(2, 0, 2.8))
    duct_b = b.element(ElementKind.DUCT_SEGMENT, "Duct B", storey=l0, system=n1, at=(2, 2, 2.8))
    terminal = b.element(
        ElementKind.AIR_TERMINAL, "Supply diffuser", storey=l0, system=n1, at=(2, 4, 2.6)
    )
    b.connect(duct_a, fitting)
    b.connect(fitting, duct_b)
    b.connect(duct_b, terminal)
    return VentilationLine(b, l0, l1, n1, duct_a, fitting, duct_b, terminal)
