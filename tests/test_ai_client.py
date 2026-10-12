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


@pytest.mark.parametrize('api_format,field', [
    ('anthropic', 'max_tokens'), ('openai_chat', 'max_tokens'), ('openai_responses', 'max_output_tokens'),
])
@pytest.mark.asyncio
async def test_vision_respects_configured_budget_instead_of_hidden_1024_cap(monkeypatch, api_format, field):
    captured = {}

    async def post(self, endpoint, payload, headers):
        captured.update(payload)
        return {'output_text': 'OK', 'content': [{'type': 'text', 'text': 'OK'}],
                'choices': [{'message': {'content': 'OK'}}]}

    monkeypatch.setattr(AIClient, '_post_json', post)
    response = await AIClient(_settings(api_format=api_format, max_output_tokens=32768)).generate_vision(
        'Review image.', [{'type': 'text', 'text': 'Summary'}])
    assert captured[field] == 32768
    assert response.text == 'OK'


@pytest.mark.asyncio
async def test_advertised_model_limits_clamp_budget_and_reject_context_overflow(monkeypatch):
    from src.integrations.ai_client import AIProviderError
    from src.integrations.model_limits import ModelLimits

    async def limits(self):
        return ModelLimits(context_tokens=64000, output_tokens=16000)

    monkeypatch.setattr(AIClient, '_fetch_model_limits', limits)
    client = AIClient(_settings(max_output_tokens=131072, context_window_tokens=32000))
    await client.prepare_limits()
    assert client.output_token_budget == 16000
    assert client.input_token_budget == 16000
    with pytest.raises(AIProviderError, match='no generation request was sent'):
        await client.generate_text('System', '正文' * 10000)


def test_model_metadata_parsing_supports_actual_provider_shapes():
    from src.integrations.model_limits import ModelLimits, models_endpoint, parse_model_limits
    data = {'data': [
        {'id': 'deepseek-v4-pro', 'context_window': 1048576, 'max_output_tokens': 393216},
        {'id': 'kimi-for-coding', 'context_length': 1048576, 'limit': {'context': 1048576}},
        {'id': 'invalid', 'max_output_tokens': True, 'context_length': -1},
    ]}
    assert parse_model_limits(data, 'deepseek-v4-pro') == ModelLimits(1048576, None, 393216)
    assert parse_model_limits(data, 'kimi-for-coding') == ModelLimits(1048576)
    assert parse_model_limits(data, 'invalid') == ModelLimits()
    assert parse_model_limits(data, 'missing') == ModelLimits()
    assert models_endpoint('https://vendor.test/coding/v1/messages') == 'https://vendor.test/coding/v1/models'
    assert models_endpoint('https://vendor.test/api/v4/chat/completions?version=x') == 'https://vendor.test/api/v4/models?version=x'
