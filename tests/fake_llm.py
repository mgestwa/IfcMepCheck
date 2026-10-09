"""A deterministic stand-in for an LLM provider: tests never call a real API."""

from __future__ import annotations

import json
from collections.abc import Callable

from mepcheck.llm.client import ExplanationBatch, ExplanationItem, LLMError


def echo_answer(contexts: list[dict]) -> list[ExplanationItem]:
    return [
        ExplanationItem(
            issue_id=context["issue_id"],
            explanation=f"{context['rule']['title']} matters at handover.",
            suggested_fix=f"Fix {context['element']['name'] or context['element']['ifc_class']}.",
        )
        for context in contexts
    ]


class FakeLLM:
    provider = "fake"
    model = "fake-1"

    def __init__(
        self,
        answer: Callable[[list[dict]], list[ExplanationItem]] = echo_answer,
        error: LLMError | None = None,
    ) -> None:
        self.answer, self.error = answer, error
        self.calls: list[tuple[str, list[dict]]] = []

    def explain(self, system: str, prompt: str) -> ExplanationBatch:
        contexts = json.loads(prompt)["issues"]
        self.calls.append((system, contexts))
        if self.error is not None:
            raise self.error
        return ExplanationBatch(items=self.answer(contexts))
