import ifcopenshell.api.root
import ifcopenshell.ifcopenshell_wrapper as wrapper
import pytest

from builders import ModelBuilder
from mepcheck.kinds import (
    OCCURRENCE_CLASSES,
    SUPPORTED_SCHEMAS,
    TYPE_CLASSES,
    ElementKind,
    element_kind,
    is_distribution_system,
)


@pytest.mark.parametrize("kind", list(ElementKind))
def test_element_kind_by_class_or_type(schema, kind):
    builder = ModelBuilder(schema)
    element = builder.element(kind, "element")
    assert element_kind(element) is kind


def test_unknown_class_has_no_kind(schema):
    builder = ModelBuilder(schema)
    with builder._owner():
        proxy = ifcopenshell.api.root.create_entity(
            builder.file, ifc_class="IfcBuildingElementProxy"
        )
    assert element_kind(proxy) is None


def test_generic_ifc2x3_class_without_type_has_no_kind():
    builder = ModelBuilder("IFC2X3")
    with builder._owner():
        segment = ifcopenshell.api.root.create_entity(builder.file, ifc_class="IfcFlowSegment")
    assert element_kind(segment) is None


@pytest.mark.parametrize("schema_name", SUPPORTED_SCHEMAS)
def test_kind_tables_use_existing_classes(schema_name):
    schema = wrapper.schema_by_name(schema_name)
    names = [n for names in TYPE_CLASSES.values() for n in names]
    if schema_name != "IFC2X3":
        names += [n for names in OCCURRENCE_CLASSES.values() for n in names]
    for name in names:
        assert schema.declaration_by_name(name).name() == name


def test_distribution_system_excludes_zones():
    builder = ModelBuilder("IFC4")
    zone = ifcopenshell.api.root.create_entity(builder.file, ifc_class="IfcZone")
    assert not is_distribution_system(zone)
    assert is_distribution_system(builder.system("N1"))


def test_ifc2x3_generic_system_counts():
    builder = ModelBuilder("IFC2X3")
    assert is_distribution_system(builder.system("N1"))
