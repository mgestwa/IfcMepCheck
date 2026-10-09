"""Issue data model with stable identifiers, and the report that holds issues."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# Fixed namespace, so issue ids are reproducible across runs and machines:
# uuid5(NAMESPACE_URL, "https://github.com/mgestwa/IfcMepCheck")
ISSUE_NAMESPACE = uuid.UUID("6cd485b2-a571-5b46-9911-a2b9d8cebd45")


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

    @property
    def rank(self) -> int:
        """Higher means more severe."""
        return _SEVERITY_RANK[self]


_SEVERITY_RANK = {Severity.INFO: 0, Severity.WARNING: 1, Severity.ERROR: 2}


def issue_id(rule_id: str, guids: Iterable[str]) -> str:
    """Stable id: the same rule on the same elements always gives the same id.

    A re-run on a corrected model keeps the ids of the remaining issues, and
    BCF topics derived from them are updated instead of duplicated.
    """
    key = f"{rule_id}|{','.join(sorted(set(guids)))}"
    return str(uuid.uuid5(ISSUE_NAMESPACE, key))


class Issue(BaseModel):
    id: str
    rule_id: str
    severity: Severity
    title: str
    message: str
    guids: list[str]
    ifc_class: str
    element_name: str | None = None
    system: str | None = None
    storey: str | None = None
    location: tuple[float, float, float] | None = None  # metres, for the BCF camera
    evidence: dict[str, Any] = Field(default_factory=dict)
    explanation: str | None = None  # filled in by the LLM layer
    suggested_fix: str | None = None  # filled in by the LLM layer


class ReportMeta(BaseModel):
    tool: str = "mepcheck"
    version: str
    file: str | None
    ifc_schema: str
    generated_at: datetime
    config: dict[str, Any]
    rules: list[str]
    skipped_rules: dict[str, str] = Field(default_factory=dict)  # rule id -> reason


class Report(BaseModel):
    meta: ReportMeta
    issues: list[Issue]
