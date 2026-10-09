"""Rules. Importing this package registers all of them."""

from mepcheck.rules import (  # noqa: F401  (registers rules)
    insulation,
    integrity,
    ports,
    properties,
    spatial,
    systems,
)
from mepcheck.rules.base import Rule, UnknownRuleError, get_rules, run_rules

__all__ = ["Rule", "UnknownRuleError", "get_rules", "run_rules"]
