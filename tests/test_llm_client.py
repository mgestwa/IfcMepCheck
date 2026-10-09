"""Provider clients with fake SDK objects: no network, no API key."""

from types import SimpleNamespace

import anthropic
import httpx2
import openai
import pytest

from mepcheck.llm.client import (
    ANTHROPIC_DEFAULT_MODEL,
    AnthropicClient,
    ExplanationBatch,
    ExplanationItem,
    LLMError,
    OpenAIClient,
    ResponseCache,
    client_from_env,
)

BATCH = ExplanationBatch(
    items=[ExplanationItem(issue_id="a", explanation="Why.", suggested_fix="How.")]
)
REQUEST = httpx2.Request("POST", "https://example.invalid")


class Recorder:
    """Stands in for ``beta.messages`` or ``responses``: records calls to parse()."""

    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


def anthropic_client(response=None, error=None):
    recorder = Recorder(response, error)
    sdk = SimpleNamespace(beta=SimpleNamespace(messages=recorder))
    return AnthropicClient(sdk_client=sdk), recorder


def openai_client(response=None, error=None):
    recorder = Recorder(response, error)
    return OpenAIClient("some-model", sdk_client=SimpleNamespace(responses=recorder)), recorder


def test_anthropic_request():
    client, recorder = anthropic_client(
        SimpleNamespace(stop_reason="end_turn", parsed_output=BATCH)
    )
    assert client.explain("system prompt", "issues") == BATCH

    [call] = recorder.calls
    assert call["model"] == ANTHROPIC_DEFAULT_MODEL == "claude-opus-5-5"
    assert call["output_format"] is ExplanationBatch
    assert call["output_config"] == {"effort": "low"}
    assert call["betas"] == ["server-side-fallback-2026-07-01"]
    assert call["fallbacks"] == "default"
    assert "temperature" not in call  # rejected by Claude Opus 5.5
    assert call["system"] == [
        {"type": "text", "text": "system prompt", "cache_control": {"type": "ephemeral"}}
    ]
    assert call["messages"] == [{"role": "user", "content": "issues"}]


@pytest.mark.parametrize(
    ("stop_reason", "parsed", "message"),
    [
        ("refusal", None, "declined"),
        ("max_tokens", None, "max_tokens"),
        ("end_turn", None, "schema"),
    ],
)
def test_anthropic_unusable_response(stop_reason, parsed, message):
    client, _ = anthropic_client(SimpleNamespace(stop_reason=stop_reason, parsed_output=parsed))
    with pytest.raises(LLMError, match=message):
        client.explain("s", "p")


def test_anthropic_api_error():
    client, _ = anthropic_client(error=anthropic.APIConnectionError(request=REQUEST))
    with pytest.raises(LLMError, match="Anthropic API error"):
        client.explain("s", "p")


def test_openai_request():
    client, recorder = openai_client(SimpleNamespace(output_parsed=BATCH))
    assert client.explain("system prompt", "issues") == BATCH

    [call] = recorder.calls
    assert call == {
        "model": "some-model",
        "instructions": "system prompt",
        "input": "issues",
        "text_format": ExplanationBatch,
        "store": False,
    }


def test_openai_refusal_and_api_error():
    client, _ = openai_client(SimpleNamespace(output_parsed=None))
    with pytest.raises(LLMError, match="declined"):
        client.explain("s", "p")
    client, _ = openai_client(error=openai.APIConnectionError(request=REQUEST))
    with pytest.raises(LLMError, match="OpenAI API error"):
        client.explain("s", "p")


def test_client_from_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    default = client_from_env({})
    assert (default.provider, default.model) == ("anthropic", "claude-opus-5-5")
    chosen = client_from_env({"MEPCHECK_LLM_PROVIDER": "OpenAI", "MEPCHECK_LLM_MODEL": "m1"})
    assert (chosen.provider, chosen.model) == ("openai", "m1")
    with pytest.raises(LLMError, match="MEPCHECK_LLM_MODEL"):
        client_from_env({"MEPCHECK_LLM_PROVIDER": "openai"})
    with pytest.raises(LLMError, match="Unknown MEPCHECK_LLM_PROVIDER"):
        client_from_env({"MEPCHECK_LLM_PROVIDER": "other"})


def test_response_cache(tmp_path):
    cache = ResponseCache(tmp_path / "cache")
    key = ResponseCache.key(provider="p", model="m", context={"b": 1, "a": [1, 2]})
    assert key == ResponseCache.key(context={"a": [1, 2], "b": 1}, model="m", provider="p")
    assert cache.get(key) is None
    cache.put(key, BATCH.items[0])
    assert cache.get(key) == BATCH.items[0]
    (tmp_path / "cache" / f"{key}.json").write_text("not json", encoding="utf-8")
    assert cache.get(key) is None
