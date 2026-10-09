import ifcopenshell.api.spatial
import pytest

from builders import ModelBuilder, ventilation_line
from mepcheck.kinds import ElementKind
from mepcheck.model import ModelLoadError, ModelView


@pytest.mark.parametrize(("length_unit", "scale"), [("m", 1.0), ("mm", 0.001)])
def test_coordinates_are_in_metres(schema, length_unit, scale):
    line = ventilation_line(schema, length_unit)
    view = line.view()
    assert view.length_scale == pytest.approx(scale)
    assert view.location_m(line.terminal) == (2.0, 4.0, 2.6)
    assert [(s.name, s.elevation_m) for s in view.storeys] == [("L0", 0.0), ("L1", 3.5)]


def test_indexes(schema):
    line = ventilation_line(schema)
    view = line.view()
    kinds = {element.Name: kind for element, kind in view.elements}
    assert kinds == {
        "Duct A": ElementKind.DUCT_SEGMENT,
        "Elbow": ElementKind.DUCT_FITTING,
        "Duct B": ElementKind.DUCT_SEGMENT,
        "Supply diffuser": ElementKind.AIR_TERMINAL,
    }
    assert [s.Name for s in view.systems_of(line.fitting)] == ["N1"]
    ports = view.ports_of(line.fitting)
    assert len(ports) == 2
    assert all(view.connected_port(port) is not None for port in ports)
    assert view.storey_of(line.duct_a) == line.l0
    assert all(len(entities) == 1 for entities in view.guid_index.values())


def test_storey_through_space(schema):
    builder = ModelBuilder(schema)
    storey = builder.storey("L0")
    space = builder.space("Room 1", storey)
    element = builder.element(ElementKind.AIR_TERMINAL, "Diffuser")
    with builder._owner():
        ifcopenshell.api.spatial.assign_container(
            builder.file, products=[element], relating_structure=space
        )
    assert builder.view().storey_of(element) == storey


def test_storey_levels_are_per_building():
    builder = ModelBuilder("IFC4")
    a0 = builder.storey("A0", 0.0)
    builder.storey("A1", 4.0)
    other = builder.add_building("Building B")
    b0 = builder.storey("B0", 0.0, building=other)
    builder.storey("B1", 3.0, building=other)
    view = builder.view()
    assert [s.name for s in view.storey_levels(a0)] == ["A0", "A1"]
    assert [s.name for s in view.storey_levels(b0)] == ["B0", "B1"]


def test_ifc2x3_owner_history_does_not_leak_into_other_models():
    ifc2x3 = ventilation_line("IFC2X3")
    assert ifc2x3.duct_a.OwnerHistory is not None
    assert ventilation_line("IFC4").duct_a.OwnerHistory is None


def test_summary(schema):
    summary = ventilation_line(schema).view().summary()
    assert summary["schema"] == schema
    assert summary["elements"] == {"air_terminal": 1, "duct_fitting": 1, "duct_segment": 2}
    assert summary["systems"] == ["N1"]
    assert summary["storeys"] == ["L0", "L1"]


def test_open_round_trip(tmp_path, schema):
    path = ventilation_line(schema).builder.write(tmp_path / "line.ifc")
    view = ModelView.open(path)
    assert view.source == "line.ifc"
    assert len(view.elements) == 4


def test_open_missing_file(tmp_path):
    with pytest.raises(ModelLoadError, match="File not found"):
        ModelView.open(tmp_path / "missing.ifc")


def test_open_invalid_file(tmp_path):
    path = tmp_path / "broken.ifc"
    path.write_text("not an IFC file", encoding="utf-8")
    with pytest.raises(ModelLoadError, match="Cannot read IFC file"):
        ModelView.open(path)
