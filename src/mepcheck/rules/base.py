"""Rule metadata, registry and runner.

A rule is a pure function: it gets the model view and the configuration and
returns issues. It never writes anything, so each rule can be tested on a
small synthetic model.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from mepcheck.config import Config
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

    def issue(
        self,
        model: ModelView,
        element: Entity,
        *,
        message: str,
        evidence: dict[str, Any] | None = None,
        guids: list[str] | None = None,
    ) -> Issue:
        """Build an issue for ``element`` with its name, system, storey and location."""
        guids = guids or [element.GlobalId]
        systems = model.systems_of(element)
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
            system=", ".join(s.Name or f"#{s.id()}" for s in systems) or None,
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
    """Run the rules, apply severity overrides and sort the issues deterministically."""
    _check_known(config.severity_overrides)
    issues: list[Issue] = []
    for rule in get_rules(ids):
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


def _check_known(ids: Iterable[str]) -> None:
    unknown = sorted(set(ids) - _REGISTRY.keys())
    if unknown:
        available = ", ".join(sorted(_REGISTRY))
        raise UnknownRuleError(f"Unknown rule id(s): {', '.join(unknown)} (available: {available})")
