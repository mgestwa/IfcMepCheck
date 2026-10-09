"""BCF 2.1 export: one topic per issue, with a viewpoint that selects the elements.

The topic GUID is the issue id, so exporting a corrected model again updates the
existing topics in a BCF tool instead of creating duplicates.
"""

from __future__ import annotations

import math
import re
import uuid
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from mepcheck.issues import Report, ReportMeta, Severity

AUTHOR = "mepcheck"
CAMERA_DISTANCE_M = 6.0
FIELD_OF_VIEW_DEG = 60.0  # BCF 2.1 allows 45 to 60 degrees
_CAMERA_OFFSET = (-1.0, -1.0, 1.0)  # look at the element from south-west, above
_COLORS = {Severity.ERROR: "E5484D", Severity.WARNING: "F59E0B", Severity.INFO: "3B82F6"}
# Characters that XML 1.0 does not allow, even escaped.
_INVALID_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

Vector = tuple[float, float, float]


@dataclass(frozen=True)
class Topic:
    guid: str
    title: str
    description: str
    labels: tuple[str, ...]
    guids: tuple[str, ...]  # IFC GlobalIds to select
    location: Vector | None  # metres; the camera looks at it
    severity: Severity
    index: int

    @property
    def viewpoint_guid(self) -> str:
        return str(uuid.uuid5(uuid.UUID(self.guid), "viewpoint"))


def topics_from_report(report: Report) -> list[Topic]:
    """One topic per issue, in report order."""
    topics = []
    for index, issue in enumerate(report.issues, start=1):
        description = issue.message
        if issue.explanation:
            description += f"\n\nExplanation: {issue.explanation}"
        if issue.suggested_fix:
            description += f"\n\nSuggested fix: {issue.suggested_fix}"
        topics.append(
            Topic(
                guid=issue.id,
                title=f"[{issue.rule_id}] {issue.title}: {issue.element_name or issue.ifc_class}",
                description=description,
                labels=(issue.rule_id, issue.severity.value),
                guids=tuple(issue.guids),
                location=issue.location,
                severity=issue.severity,
                index=index,
            )
        )
    return topics


def write_bcf(report: Report, path: str | Path, topics: list[Topic] | None = None) -> Path:
    """Write a BCF 2.1 zip. The same report always gives the same file."""
    topics = topics_from_report(report) if topics is None else topics
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = report.meta.generated_at
    date_time = (max(stamp.year, 1980), stamp.month, stamp.day, stamp.hour, stamp.minute, 0)

    with zipfile.ZipFile(path, "w") as archive:

        def add(name: str, data: bytes) -> None:
            info = zipfile.ZipInfo(name, date_time=date_time)
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)

        add("bcf.version", version_xml())
        for topic in topics:
            add(f"{topic.guid}/markup.bcf", markup_xml(topic, report.meta))
            add(f"{topic.guid}/viewpoint.bcfv", viewpoint_xml(topic))
    return path


def version_xml() -> bytes:
    root = ET.Element("Version", VersionId="2.1")
    ET.SubElement(root, "DetailedVersion").text = "2.1"
    return _to_bytes(root)


def markup_xml(topic: Topic, meta: ReportMeta) -> bytes:
    """markup.bcf; elements are written in the order the XSD sequence requires."""
    created = _datetime(meta.generated_at)
    root = ET.Element("Markup")
    header = ET.SubElement(root, "Header")
    file = ET.SubElement(header, "File", {"isExternal": "true"})
    if meta.ifc_project:
        file.set("IfcProject", meta.ifc_project)
    if meta.file:
        ET.SubElement(file, "Filename").text = _text(meta.file)
    ET.SubElement(file, "Date").text = created

    element = ET.SubElement(
        root, "Topic", {"Guid": topic.guid, "TopicType": "Issue", "TopicStatus": "Open"}
    )
    ET.SubElement(element, "Title").text = _text(topic.title)
    ET.SubElement(element, "Index").text = str(topic.index)
    for label in topic.labels:
        ET.SubElement(element, "Labels").text = _text(label)
    ET.SubElement(element, "CreationDate").text = created
    ET.SubElement(element, "CreationAuthor").text = AUTHOR
    ET.SubElement(element, "Description").text = _text(topic.description)

    viewpoints = ET.SubElement(root, "Viewpoints", {"Guid": topic.viewpoint_guid})
    ET.SubElement(viewpoints, "Viewpoint").text = "viewpoint.bcfv"
    return _to_bytes(root)


def viewpoint_xml(topic: Topic) -> bytes:
    """viewpoint.bcfv: selected and coloured elements, and a camera when the location is known."""
    root = ET.Element("VisualizationInfo", {"Guid": topic.viewpoint_guid})
    components = ET.SubElement(root, "Components")
    selection = ET.SubElement(components, "Selection")
    for guid in topic.guids:
        ET.SubElement(selection, "Component", {"IfcGuid": guid})
    ET.SubElement(components, "Visibility", {"DefaultVisibility": "true"})
    color = ET.SubElement(
        ET.SubElement(components, "Coloring"), "Color", {"Color": _COLORS[topic.severity]}
    )
    for guid in topic.guids:
        ET.SubElement(color, "Component", {"IfcGuid": guid})

    if topic.location is not None:
        viewpoint, direction, up = camera(topic.location)
        perspective = ET.SubElement(root, "PerspectiveCamera")
        _vector(perspective, "CameraViewPoint", viewpoint)
        _vector(perspective, "CameraDirection", direction)
        _vector(perspective, "CameraUpVector", up)
        ET.SubElement(perspective, "FieldOfView").text = _number(FIELD_OF_VIEW_DEG)
    return _to_bytes(root)


def camera(target: Vector, distance: float = CAMERA_DISTANCE_M) -> tuple[Vector, Vector, Vector]:
    """Camera position, unit view direction and up vector (perpendicular to the direction)."""
    offset = _normalize(_CAMERA_OFFSET)
    viewpoint = (
        target[0] + distance * offset[0],
        target[1] + distance * offset[1],
        target[2] + distance * offset[2],
    )
    direction = (-offset[0], -offset[1], -offset[2])
    # World Z projected onto the plane perpendicular to the view direction.
    up = _normalize(
        (-direction[2] * direction[0], -direction[2] * direction[1], 1 - direction[2] ** 2)
    )
    return viewpoint, direction, up


def _normalize(vector: Vector) -> Vector:
    length = math.sqrt(sum(component * component for component in vector))
    return (vector[0] / length, vector[1] / length, vector[2] / length)


def _vector(parent: ET.Element, name: str, value: Vector) -> None:
    element = ET.SubElement(parent, name)
    for axis, component in zip("XYZ", value, strict=True):
        ET.SubElement(element, axis).text = _number(component)


def _number(value: float) -> str:
    return f"{value:.6f}"


def _datetime(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def _text(value: str) -> str:
    return _INVALID_XML.sub("", value)


def _to_bytes(root: ET.Element) -> bytes:
    ET.indent(root)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)
