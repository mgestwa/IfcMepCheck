"""LLM providers with structured output, selected by environment variables, and a response cache.

MEPCHECK_LLM_PROVIDER   anthropic (default) | openai
MEPCHECK_LLM_MODEL      default claude-opus-5-5 for anthropic; required for openai
ANTHROPIC_API_KEY / OPENAI_API_KEY are read by the provider SDKs.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError

ANTHROPIC_DEFAULT_MODEL = "claude-opus-5-5"
_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMError(Exception):
    """The provider could not produce explanations (configuration, API error or refusal)."""


class ExplanationItem(BaseModel):
    issue_id: str
    explanation: str
    suggested_fix: str


class ExplanationBatch(BaseModel):
    items: list[ExplanationItem]


class LLMClient(Protocol):
    provider: str
    model: str

    def explain(self, system: str, prompt: str) -> ExplanationBatch: ...


class AnthropicClient:
    provider = "anthropic"

    def __init__(self, model: str = ANTHROPIC_DEFAULT_MODEL, sdk_client: Any = None) -> None:
        self.model = model
        if sdk_client is None:
            anthropic = _import("anthropic")
            sdk_client = anthropic.Anthropic()
        self._client = sdk_client

    def explain(self, system: str, prompt: str) -> ExplanationBatch:
        anthropic = _import("anthropic")
        try:
            response = self._client.beta.messages.parse(
                model=self.model,
                max_tokens=16000,
                # Opus 5.5 rejects temperature; low effort keeps answers short and cheap.
                output_config={"effort": "low"},
                # A safety decline is re-run server-side on the recommended fallback model.
                betas=[_FALLBACK_BETA],
                fallbacks="default",
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": prompt}],
                output_format=ExplanationBatch,
            )
        except anthropic.APIError as exc:
            raise LLMError(f"Anthropic API error: {exc}") from exc
        if response.stop_reason == "refusal":
            raise LLMError("The model declined the request")
        if response.stop_reason == "max_tokens":
            raise LLMError("The response was cut off at max_tokens")
        if response.parsed_output is None:
            raise LLMError("The response did not match the expected schema")
        return response.parsed_output


class OpenAIClient:
    provider = "openai"

    def __init__(self, model: str, sdk_client: Any = None) -> None:
        self.model = model
        if sdk_client is None:
            openai = _import("openai")
            sdk_client = openai.OpenAI()
        self._client = sdk_client

    def explain(self, system: str, prompt: str) -> ExplanationBatch:
        openai = _import("openai")
        try:
            response = self._client.responses.parse(
                model=self.model,
                instructions=system,
                input=prompt,
                text_format=ExplanationBatch,
                store=False,  # do not keep model data on the provider side
            )
        except (
            openai.APIError,
            openai.LengthFinishReasonError,
            openai.ContentFilterFinishReasonError,
        ) as exc:
            raise LLMError(f"OpenAI API error: {exc}") from exc
        if response.output_parsed is None:
            raise LLMError("The model declined the request or returned no structured output")
        return response.output_parsed


def client_from_env(env: Mapping[str, str] | None = None) -> LLMClient:
    if env is None:
        _load_dotenv()
        env = os.environ
    provider = (env.get("MEPCHECK_LLM_PROVIDER") or "anthropic").strip().lower()
    model = (env.get("MEPCHECK_LLM_MODEL") or "").strip()
    if provider == "anthropic":
        return AnthropicClient(model or ANTHROPIC_DEFAULT_MODEL)
    if provider == "openai":
        if not model:
            raise LLMError("Set MEPCHECK_LLM_MODEL to an OpenAI model name")
        return OpenAIClient(model)
    raise LLMError(f"Unknown MEPCHECK_LLM_PROVIDER {provider!r}; use 'anthropic' or 'openai'")


class ResponseCache:
    """One JSON file per explained issue, keyed by a hash of everything sent to the model."""

    def __init__(self, directory: str | Path = ".mepcheck_cache") -> None:
        self.directory = Path(directory)

    @staticmethod
    def key(**parts: Any) -> str:
        payload = json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get(self, key: str) -> ExplanationItem | None:
        path = self.directory / f"{key}.json"
        try:
            return ExplanationItem.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError):
            return None

    def put(self, key: str, item: ExplanationItem) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory / f"{key}.json").write_text(item.model_dump_json(), encoding="utf-8")


def _import(name: str) -> Any:
    try:
        return __import__(name)
    except ImportError as exc:
        raise LLMError(f"The {name} package is missing: pip install 'mepcheck[llm]'") from exc


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(override=False)
