"""Rule metadata, registry, runner and helpers shared by rules.

A rule is a pure function: it gets the model view and the configuration and
returns issues. It never writes anything, so each rule can be tested on a
small synthetic model.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from mepcheck.config import Config, PropertyRef
from mepcheck.issues import Issue, Severity, issue_id
from mepcheck.model import Entity, ModelView

CheckFn = Callable[[ModelView, Config], list[Issue]]


class UnknownRuleError(ValueError):
    pass


@dataclass(frozen=True)
class Rule:
    id: str
    title: str
    rationale: str  # why it matters at handover; used by the README and the LLM layer
    severity: Severity
    applies_to: tuple[str, ...]  # IFC classes
    requires: str | None = None  # Config section the rule needs, e.g. "insulation"

    def is_configured(self, config: Config) -> bool:
        return self.requires is None or bool(getattr(config, self.requires))

    def issue(
        self,
        model: ModelView,
        config: Config,
        element: Entity,
        *,
        message: str,
        evidence: dict[str, Any] | None = None,
        guids: list[str] | None = None,
    ) -> Issue:
        """Build an issue for ``element`` with its name, system, storey and location."""
        guids = guids or [element.GlobalId]
        storey = model.storey_of(element)
        return Issue(
            id=issue_id(self.id, guids),
            rule_id=self.id,
            severity=self.severity,
            title=self.title,
            message=message,
            guids=guids,
            ifc_class=element.is_a(),
            element_name=getattr(element, "Name", None),
            system=", ".join(system_names(model, config, element)) or None,
            storey=storey.Name if storey is not None else None,
            location=model.location_m(element),
            evidence=evidence or {},
        )


_REGISTRY: dict[str, tuple[Rule, CheckFn]] = {}


def register(rule: Rule) -> Callable[[CheckFn], CheckFn]:
    def decorator(check: CheckFn) -> CheckFn:
        if rule.id in _REGISTRY:
            raise ValueError(f"Rule {rule.id} is already registered")
        _REGISTRY[rule.id] = (rule, check)
        return check

    return decorator


def get_rules(ids: Iterable[str] | None = None) -> list[Rule]:
    """Registered rules sorted by id, optionally limited to ``ids``."""
    if ids is None:
        wanted = sorted(_REGISTRY)
    else:
        wanted = sorted({rule_id.strip().upper() for rule_id in ids if rule_id.strip()})
        _check_known(wanted)
    return [_REGISTRY[rule_id][0] for rule_id in wanted]


def run_rules(model: ModelView, config: Config, ids: Iterable[str] | None = None) -> list[Issue]:
    """Run the configured rules, apply severity overrides and sort issues deterministically.

    Rules whose configuration section is empty are skipped, not reported as clean.
    """
    _check_known(config.severity_overrides)
    issues: list[Issue] = []
    for rule in get_rules(ids):
        if not rule.is_configured(config):
            continue
        found = _REGISTRY[rule.id][1](model, config)
        override = config.severity_overrides.get(rule.id)
        if override is not None:
            found = [issue.model_copy(update={"severity": override}) for issue in found]
        issues.extend(found)
    issues.sort(key=lambda i: (i.rule_id, i.storey or "", i.element_name or "", i.id))
    return issues


def element_label(element: Entity) -> str:
    """Human-readable element reference for messages, e.g. IfcDuctSegment 'Duct A'."""
    name = getattr(element, "Name", None)
    return f"{element.is_a()} '{name}'" if name else f"{element.is_a()} #{element.id()}"


def property_values(model: ModelView, element: Entity, ref: PropertyRef) -> list[Any]:
    """Values of ``ref`` on the element (one per matching property set)."""
    psets = model.psets_of(element)
    if ref.pset is not None:
        props = psets.get(ref.pset, {})
        return [props[ref.property]] if ref.property in props else []
    return [props[ref.property] for props in psets.values() if ref.property in props]


def is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def system_names(model: ModelView, config: Config, element: Entity) -> list[str]:
    """Names of the element's IfcSystems or, when it has none, of the configured
    ``system_name_properties`` (exports that store the system only as a property)."""
    names = [system.Name or f"#{system.id()}" for system in model.systems_of(element)]
    if names:
        return names
    return property_system_names(model, config, element)


def property_system_names(model: ModelView, config: Config, element: Entity) -> list[str]:
    """System names from ``system_name_properties``. Revit writes an element that
    belongs to several systems (e.g. an air handling unit) as "A,B,C"."""
    found: set[str] = set()
    for ref in config.system_name_properties:
        for value in property_values(model, element, ref):
            if not is_empty(value):
                found.update(name.strip() for name in str(value).split(",") if name.strip())
    return sorted(found)


def _check_known(ids: Iterable[str]) -> None:
    unknown = sorted(set(ids) - _REGISTRY.keys())
    if unknown:
        available = ", ".join(sorted(_REGISTRY))
        raise UnknownRuleError(f"Unknown rule id(s): {', '.join(unknown)} (available: {available})")
