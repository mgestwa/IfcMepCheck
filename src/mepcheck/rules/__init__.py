"""Rules. Importing this package registers all of them."""

from mepcheck.rules import integrity, ports, spatial, systems  # noqa: F401  (registers rules)
from mepcheck.rules.base import Rule, UnknownRuleError, get_rules, run_rules

__all__ = ["Rule", "UnknownRuleError", "get_rules", "run_rules"]
