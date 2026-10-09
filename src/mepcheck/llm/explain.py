"""Add explanations and suggested fixes to issues with an LLM.

Only the context of each issue goes to the model (rule description, evidence,
trimmed property sets, system and storey), never the IFC model itself. The model
can only describe the issues it was given: answers for unknown or repeated ids
are rejected, so the list of issues never changes.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from mepcheck.issues import Issue, Report
from mepcheck.llm.client import ExplanationItem, LLMClient, LLMError, ResponseCache
from mepcheck.model import ModelView
from mepcheck.rules import Rule, get_rules

log = logging.getLogger(__name__)

PROMPT_VERSION = 1
LANGUAGES = {"en": "English", "pl": "Polish"}
MAX_PSETS = 8
MAX_PROPERTIES = 15
MAX_TEXT = 80

SYSTEM_PROMPT = """\
You are a senior BIM/MEP quality consultant. A rule-based checker has already found \
the issues below in an IFC model of an HVAC installation; its findings are final.

For every issue you receive, write:
- explanation: 1-3 sentences on what is wrong and why it matters for handover, \
coordination or commissioning, based on the rule description and the evidence;
- suggested_fix: concrete steps to fix it in the authoring tool (for example Revit) \
or in the IFC export settings.

Return exactly one item per issue_id you were given, with that issue_id. Never add, \
merge or drop issues. Use only the facts in the issue context; when something is \
unknown, say what to check instead of guessing. Keep GlobalIds, IFC class names and \
property names unchanged. Write in {language}.
"""


@dataclass
class ExplainStats:
    explained: int = 0
    cached: int = 0
    failed: int = 0
    skipped: int = 0  # over max_issues
    rejected: int = 0  # answers for unknown or repeated issue ids


def explain_report(
    report: Report,
    client: LLMClient,
    *,
    lang: str = "en",
    model: ModelView | None = None,
    cache: ResponseCache | None = None,
    max_issues: int = 50,
    batch_size: int = 20,
    force: bool = False,
) -> ExplainStats:
    """Fill ``explanation`` and ``suggested_fix`` in place; LLM failures are logged, not raised."""
    if lang not in LANGUAGES:
        raise ValueError(f"Unsupported language {lang!r}; use one of: {', '.join(LANGUAGES)}")
    stats = ExplainStats()
    rules = {rule.id: rule for rule in get_rules()}
    candidates = [issue for issue in report.issues if force or not _is_explained(issue)]
    candidates.sort(key=lambda issue: -issue.severity.rank)  # stable: report order within a level
    if max_issues and len(candidates) > max_issues:
        stats.skipped = len(candidates) - max_issues
        candidates = candidates[:max_issues]

    pending: list[tuple[Issue, dict[str, Any], str]] = []
    for issue in candidates:
        context = issue_context(issue, rules.get(issue.rule_id), model)
        key = ResponseCache.key(
            provider=client.provider,
            model=client.model,
            prompt=PROMPT_VERSION,
            lang=lang,
            context=context,
        )
        cached = cache.get(key) if cache is not None else None
        if cached is not None:
            _apply(issue, cached)
            stats.cached += 1
        else:
            pending.append((issue, context, key))

    system = SYSTEM_PROMPT.format(language=LANGUAGES[lang])
    for start in range(0, len(pending), batch_size):
        batch = pending[start : start + batch_size]
        prompt = json.dumps(
            {"issues": [context for _, context, _ in batch]},
            ensure_ascii=False,
            indent=1,
            default=str,
        )
        try:
            result = client.explain(system, prompt)
        except LLMError as exc:
            log.warning(
                "LLM request failed, %d issues left without explanation: %s", len(batch), exc
            )
            stats.failed += len(batch)
            continue

        by_id = {issue.id: (issue, key) for issue, _, key in batch}
        done: set[str] = set()
        for item in result.items:
            entry = by_id.get(item.issue_id)
            if entry is None or item.issue_id in done or not _has_text(item):
                stats.rejected += 1
                continue
            issue, key = entry
            _apply(issue, item)
            done.add(item.issue_id)
            stats.explained += 1
            if cache is not None:
                cache.put(key, item)
        if len(done) < len(batch):
            log.warning("LLM returned no explanation for %d issues", len(batch) - len(done))
            stats.failed += len(batch) - len(done)
    if stats.rejected:
        log.warning("Rejected %d LLM answers for unknown or repeated issue ids", stats.rejected)
    return stats


def issue_context(
    issue: Issue, rule: Rule | None, model: ModelView | None = None
) -> dict[str, Any]:
    """Everything the LLM gets about one issue."""
    element: dict[str, Any] = {
        "ifc_class": issue.ifc_class,
        "name": issue.element_name,
        "system": issue.system,
        "storey": issue.storey,
    }
    if model is not None:
        entities = model.guid_index.get(issue.guids[0], [])
        if entities and entities[0].is_a("IfcObjectDefinition"):
            element["property_sets"] = trim_psets(model.psets_of(entities[0]))
    return {
        "issue_id": issue.id,
        "rule": {
            "id": issue.rule_id,
            "title": issue.title,
            "why_it_matters": rule.rationale if rule is not None else None,
        },
        "severity": issue.severity.value,
        "message": issue.message,
        "element": element,
        "evidence": issue.evidence,
    }


def trim_psets(psets: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """A bounded, JSON-friendly excerpt of the property sets (cost and confidentiality)."""
    trimmed: dict[str, dict[str, Any]] = {}
    for name in sorted(psets)[:MAX_PSETS]:
        properties: dict[str, Any] = {}
        for key, value in psets[name].items():
            if key == "id" or value is None:
                continue
            if not isinstance(value, bool | int | float):
                value = str(value)[:MAX_TEXT]
            properties[key] = value
            if len(properties) == MAX_PROPERTIES:
                break
        if properties:
            trimmed[name] = properties
    return trimmed


def _is_explained(issue: Issue) -> bool:
    return bool(issue.explanation and issue.suggested_fix)


def _has_text(item: ExplanationItem) -> bool:
    return bool(item.explanation.strip() and item.suggested_fix.strip())


def _apply(issue: Issue, item: ExplanationItem) -> None:
    issue.explanation = item.explanation.strip()
    issue.suggested_fix = item.suggested_fix.strip()
