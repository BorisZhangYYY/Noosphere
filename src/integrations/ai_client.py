from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from src.core.config.config import ai_config, ai_provider_config, load_config, resolve_ai_api_key


class AIProviderError(RuntimeError):
    pass


ANTHROPIC_PROVIDER = "anthropic"


@dataclass(frozen=True)
class AISettings:
    provider: str
    model: str
    api_key: str
    api_base: str
    max_output_tokens: int
    temperature: float | None = None
    anthropic_version: str = "2023-06-01"


@dataclass(frozen=True)
class AITextResponse:
    text: str
    model: str
    provider: str


def resolve_ai_settings(config: dict | None = None) -> AISettings:
    root_config = load_config() if config is None else config
    resolved = ai_config(root_config)
    provider = str(resolved.get("provider") or "").strip().lower()
    if not provider:
        raise AIProviderError("ai.provider is required")
    provider_config = ai_provider_config(root_config, provider)

    model = str(provider_config.get("model") or "").strip()
    if not model:
        raise AIProviderError(f"ai_providers.{provider}.model is required")

    max_output_tokens = int(provider_config.get("max_output_tokens") or 12000)
    temperature_value = provider_config.get("temperature")
    temperature = float(temperature_value) if temperature_value is not None else None
    api_base = str(provider_config.get("api_base") or "").rstrip("/")
    if not api_base:
        raise AIProviderError(f"ai_providers.{provider}.api_base is required")

    api_key = resolve_ai_api_key(root_config, provider)

    return AISettings(
        provider=provider,
        model=model,
        api_key=api_key,
        api_base=api_base,
        max_output_tokens=max_output_tokens,
        temperature=temperature,
        anthropic_version=str(provider_config.get("anthropic_version") or "2023-06-01"),
    )


class AIClient:
    def __init__(self, settings: AISettings | None = None):
        self.settings = settings or resolve_ai_settings()

    def generate_text(self, system_prompt: str, user_prompt: str) -> AITextResponse:
        if self.settings.provider == "openai":
            text = self._openai_response(system_prompt, user_prompt)
        elif self.settings.provider == ANTHROPIC_PROVIDER:
            text = self._anthropic_message(system_prompt, user_prompt)
        else:
            raise AIProviderError(f"Unsupported AI provider: {self.settings.provider}")
        return AITextResponse(text=text, model=self.settings.model, provider=self.settings.provider)

    def generate_structured_text(
        self,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict[str, Any],
    ) -> AITextResponse:
        if self.settings.provider == "openai":
            text = self._openai_structured_response(system_prompt, user_prompt, json_schema)
        elif self.settings.provider == ANTHROPIC_PROVIDER:
            text = self._anthropic_structured_message(system_prompt, user_prompt, json_schema)
        else:
            raise AIProviderError(f"Unsupported AI provider: {self.settings.provider}")
        return AITextResponse(text=text, model=self.settings.model, provider=self.settings.provider)

    def _api_key(self) -> str:
        return self.settings.api_key

    def _openai_response(self, system_prompt: str, user_prompt: str) -> str:
        endpoint = openai_responses_endpoint(self.settings.api_base)
        payload: dict[str, Any] = {
            "model": self.settings.model,
            "instructions": system_prompt,
            "input": user_prompt,
            "max_output_tokens": self.settings.max_output_tokens,
        }
        if self.settings.temperature is not None:
            payload["temperature"] = self.settings.temperature

        data = self._post_json(
            endpoint,
            payload,
            {
                "Authorization": f"Bearer {self._api_key()}",
                "Content-Type": "application/json",
            },
        )
        text = data.get("output_text")
        if isinstance(text, str) and text.strip():
            return text
        return text_from_openai_output(data)

    def _anthropic_message(self, system_prompt: str, user_prompt: str) -> str:
        endpoint = anthropic_messages_endpoint(self.settings.api_base)
        payload: dict[str, Any] = {
            "model": self.settings.model,
            "max_tokens": self.settings.max_output_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": [{"type": "text", "text": user_prompt}]}],
        }
        if self.settings.temperature is not None:
            payload["temperature"] = self.settings.temperature

        data = self._post_json(
            endpoint,
            payload,
            {
                "x-api-key": self._api_key(),
                "anthropic-version": self.settings.anthropic_version,
                "Content-Type": "application/json",
            },
        )
        return text_from_anthropic_content(data)

    def _openai_structured_response(
        self, system_prompt: str, user_prompt: str, json_schema: dict[str, Any]
    ) -> str:
        endpoint = openai_responses_endpoint(self.settings.api_base)
        payload: dict[str, Any] = {
            "model": self.settings.model,
            "instructions": system_prompt,
            "input": user_prompt,
            "max_output_tokens": self.settings.max_output_tokens,
            "response_format": {
                "type": "json_object",
                "schema": json_schema,
            },
        }
        if self.settings.temperature is not None:
            payload["temperature"] = self.settings.temperature

        data = self._post_json(
            endpoint,
            payload,
            {
                "Authorization": f"Bearer {self._api_key()}",
                "Content-Type": "application/json",
            },
        )
        text = data.get("output_text")
        if isinstance(text, str) and text.strip():
            return text
        return text_from_openai_output(data)

    def _anthropic_structured_message(
        self, system_prompt: str, user_prompt: str, json_schema: dict[str, Any]
    ) -> str:
        endpoint = anthropic_messages_endpoint(self.settings.api_base)
        payload: dict[str, Any] = {
            "model": self.settings.model,
            "max_tokens": self.settings.max_output_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": [{"type": "text", "text": user_prompt}]}],
            "input_schema": json_schema,
        }
        if self.settings.temperature is not None:
            payload["temperature"] = self.settings.temperature

        data = self._post_json(
            endpoint,
            payload,
            {
                "x-api-key": self._api_key(),
                "anthropic-version": self.settings.anthropic_version,
                "Content-Type": "application/json",
            },
        )
        return text_from_anthropic_content(data)

    def _post_json(self, endpoint: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(endpoint, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise AIProviderError(f"{self.settings.provider} API HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise AIProviderError(f"{self.settings.provider} API connection failed: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise AIProviderError(f"{self.settings.provider} API returned invalid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise AIProviderError(f"{self.settings.provider} API returned a non-object response")
        return data


def text_from_openai_output(data: dict[str, Any]) -> str:
    chunks: list[str] = []
    for item in data.get("output") or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content") or []:
            if not isinstance(content, dict):
                continue
            text = content.get("text")
            if isinstance(text, str):
                chunks.append(text)
    if chunks:
        return "\n".join(chunks).strip()
    raise AIProviderError("OpenAI response did not contain output text")


def text_from_anthropic_content(data: dict[str, Any]) -> str:
    chunks: list[str] = []
    for content in data.get("content") or []:
        if isinstance(content, dict) and content.get("type") == "text" and isinstance(content.get("text"), str):
            chunks.append(content["text"])
    if chunks:
        return "\n".join(chunks).strip()
    raise AIProviderError("Anthropic response did not contain text content")


def openai_responses_endpoint(api_base: str) -> str:
    base = api_base.rstrip("/")
    if base.endswith("/responses"):
        return base
    if base.endswith("/v1"):
        return f"{base}/responses"
    return f"{base}/v1/responses"


def anthropic_messages_endpoint(api_base: str) -> str:
    base = api_base.rstrip("/")
    if base.endswith("/messages"):
        return base
    if base.endswith("/v1"):
        return f"{base}/messages"
    return f"{base}/v1/messages"
