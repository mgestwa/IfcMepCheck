"""Checker configuration, loaded from YAML with line-numbered error messages."""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path
from typing import Annotated, Any

import yaml
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, ValidationError

from mepcheck.issues import Severity
from mepcheck.kinds import HVAC_CLASSES


class ConfigError(Exception):
    """The configuration file cannot be read or is invalid."""


def _hvac_class(name: str) -> str:
    if name not in HVAC_CLASSES:
        raise ValueError(f"unknown IFC class {name!r}; use one of: {', '.join(HVAC_CLASSES)}")
    return name


def _regex(pattern: str) -> str:
    try:
        re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"invalid regular expression {pattern!r}: {exc}") from exc
    return pattern


HvacClass = Annotated[str, AfterValidator(_hvac_class)]
Regex = Annotated[str, AfterValidator(_regex)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PropertyRef(_Strict):
    """A property in a given property set, or in any property set when ``pset`` is omitted."""

    pset: str | None = None
    property: str = Field(min_length=1)

    def __str__(self) -> str:
        return f"{self.pset or '*'}.{self.property}"


class RequiredProperty(_Strict):
    name: str = Field(min_length=1)
    # Alternatives, e.g. a standard Pset and the one exported by Revit.
    any_of: Annotated[list[PropertyRef], Field(min_length=1)] | None = None

    def sources(self) -> list[PropertyRef]:
        return self.any_of or [PropertyRef(property=self.name)]


class InsulationConfig(_Strict):
    # Matched with re.search against system names, e.g. '^N\d*' for supply systems.
    required_for_system_names: Annotated[list[Regex], Field(min_length=1)]
    classes: Annotated[list[HvacClass], Field(min_length=1)] = Field(
        default_factory=lambda: ["IfcDuctSegment", "IfcDuctFitting"]
    )
    covering_types: Annotated[list[str], Field(min_length=1)] = Field(
        default_factory=lambda: ["INSULATION"]
    )


class Config(_Strict):
    storey_tolerance_m: float = Field(default=0.5, ge=0)
    required_properties: dict[HvacClass, list[RequiredProperty]] = Field(default_factory=dict)
    insulation: InsulationConfig | None = None
    # Fallback for exports without IfcSystem (older Revit): read the system name
    # from a property, e.g. {pset: Mechanical, property: System Name}.
    system_name_properties: list[PropertyRef] = Field(default_factory=list)
    severity_overrides: dict[str, Severity] = Field(default_factory=dict)


def load_config(path: str | Path, rule_ids: Iterable[str] | None = None) -> Config:
    """Load and validate a YAML configuration.

    Every problem is reported as ``file:line: field: message``. When ``rule_ids``
    is given, unknown ids in ``severity_overrides`` are reported too.
    """
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Cannot read configuration {path}: {exc.strerror or exc}") from exc
    try:
        root = yaml.compose(text, Loader=yaml.SafeLoader)
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        line = mark.line + 1 if mark is not None else "?"
        problem = getattr(exc, "problem", None) or str(exc)
        raise ConfigError(f"{path}:{line}: invalid YAML: {problem}") from exc

    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path}:1: the configuration must be a mapping of settings")

    lines = _line_index(root)
    try:
        config = Config.model_validate(data)
    except ValidationError as exc:
        messages = [_format_error(path, error, lines) for error in exc.errors()]
        raise ConfigError("\n".join(messages)) from exc

    if rule_ids is not None:
        known = set(rule_ids)
        unknown = [rule_id for rule_id in config.severity_overrides if rule_id not in known]
        if unknown:
            messages = [
                f"{path}:{lines.get(('severity_overrides', rule_id), '?')}: "
                f"severity_overrides.{rule_id}: unknown rule id"
                for rule_id in unknown
            ]
            raise ConfigError("\n".join(messages))
    return config


def _line_index(
    node: yaml.Node | None, path: tuple[Any, ...] = (), index: dict | None = None
) -> dict[tuple[Any, ...], int]:
    """Map every key path in the YAML document to its 1-based line number."""
    index = {} if index is None else index
    if node is None:
        return index
    index.setdefault(path, node.start_mark.line + 1)
    if isinstance(node, yaml.MappingNode):
        for key_node, value_node in node.value:
            child = (*path, key_node.value)
            index[child] = key_node.start_mark.line + 1
            _line_index(value_node, child, index)
    elif isinstance(node, yaml.SequenceNode):
        for position, item in enumerate(node.value):
            _line_index(item, (*path, position), index)
    return index


def _format_error(path: Path, error: dict[str, Any], lines: dict[tuple[Any, ...], int]) -> str:
    location = [part for part in error["loc"] if part != "[key]"]
    line: int | str = "?"
    for size in range(len(location), -1, -1):
        if tuple(location[:size]) in lines:
            line = lines[tuple(location[:size])]
            break
    field = ".".join(str(part) for part in location) or "(root)"
    message = error["msg"].removeprefix("Value error, ")
    return f"{path}:{line}: {field}: {message}"
