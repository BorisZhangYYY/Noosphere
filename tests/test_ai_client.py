"""AI provider protocol and response parsing tests."""
from __future__ import annotations

import pytest

from src.integrations.ai_client import (
    AIClient,
    AIOutputTruncatedError,
    AISettings,
    _raise_if_output_truncated,
    anthropic_messages_endpoint,
    openai_chat_endpoint,
    openai_responses_endpoint,
    output_truncation_reason,
)


def _settings(**overrides) -> AISettings:
    values = {
        "provider": "Custom Vendor",
        "api_format": "openai_chat",
        "model": "custom-model",
        "api_key": "test-secret",
        "api_base": "https://models.example.test",
        "max_output_tokens": 512,
    }
    values.update(overrides)
    return AISettings(**values)


def test_openai_chat_endpoint_accepts_base_or_full_endpoint() -> None:
    assert openai_chat_endpoint("https://models.example.test") == "https://models.example.test/v1/chat/completions"
    assert openai_chat_endpoint("https://models.example.test/v1") == "https://models.example.test/v1/chat/completions"
    assert openai_chat_endpoint("https://models.example.test/chat/completions") == "https://models.example.test/chat/completions"


@pytest.mark.parametrize(
    ("resolver", "endpoint"),
    [
        (openai_chat_endpoint, "https://models.example.test/v1/chat/completions?api-version=2026-07-20"),
        (openai_responses_endpoint, "https://models.example.test/v1/responses?api-version=2026-07-20"),
        (anthropic_messages_endpoint, "https://models.example.test/v1/messages?api-version=2026-07-20"),
    ],
)
def test_full_endpoint_with_query_is_not_extended(resolver, endpoint) -> None:
    assert resolver(endpoint) == endpoint


def test_query_is_preserved_when_endpoint_path_is_appended() -> None:
    assert (
        openai_chat_endpoint("https://models.example.test/v1?api-version=2026-07-20")
        == "https://models.example.test/v1/chat/completions?api-version=2026-07-20"
    )


@pytest.mark.asyncio
async def test_custom_named_provider_dispatches_by_api_format(monkeypatch) -> None:
    captured: dict = {}

    async def fake_post(self, endpoint, payload, headers):
        captured.update(endpoint=endpoint, payload=payload, headers=headers)
        return {"choices": [{"message": {"content": "NOOSPHERE_OK"}}]}

    monkeypatch.setattr(AIClient, "_post_json", fake_post)
    response = await AIClient(_settings()).generate_text("system", "user")

    assert response.text == "NOOSPHERE_OK"
    assert captured["endpoint"].endswith("/v1/chat/completions")
    assert captured["payload"]["messages"][1]["content"] == "user"
    assert captured["headers"]["Authorization"] == "Bearer test-secret"


@pytest.mark.parametrize(
    ("data", "reason"),
    [
        ({"stop_reason": "max_tokens"}, "max_tokens"),
        ({"type": "message_delta", "delta": {"stop_reason": "max_tokens"}}, "max_tokens"),
        ({"choices": [{"finish_reason": "length"}]}, "length"),
        (
            {
                "status": "incomplete",
                "incomplete_details": {"reason": "max_output_tokens"},
            },
            "max_output_tokens",
        ),
        (
            {
                "type": "response.incomplete",
                "response": {
                    "status": "incomplete",
                    "incomplete_details": {"reason": "max_output_tokens"},
                },
            },
            "max_output_tokens",
        ),
    ],
)
def test_output_truncation_reason_supports_provider_formats(data, reason) -> None:
    assert output_truncation_reason(data) == reason


def test_output_truncation_raises_specific_provider_error() -> None:
    with pytest.raises(AIOutputTruncatedError, match=r"Vendor API output was truncated \(length\)"):
        _raise_if_output_truncated(
            {"choices": [{"finish_reason": "length"}]},
            "Vendor",
        )


def test_normal_completion_is_not_treated_as_truncation() -> None:
    assert output_truncation_reason({"choices": [{"finish_reason": "stop"}]}) is None
