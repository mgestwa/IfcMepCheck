"""Checker configuration. Loading it from YAML is added together with the YAML rules."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from mepcheck.issues import Severity


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    storey_tolerance_m: float = Field(default=0.5, ge=0)
    severity_overrides: dict[str, Severity] = Field(default_factory=dict)
