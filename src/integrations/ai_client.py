from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import aiohttp

from src.core.config.config import load_config
from src.core.config.schema import Config


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
    timeout_seconds: int = 300


@dataclass(frozen=True)
class AITextResponse:
    text: str
    model: str
    provider: str


def resolve_ai_settings(config: Config | None = None) -> AISettings:
    if config is None:
        config = load_config()
    settings = config.resolve_ai_settings()
    return AISettings(
        provider=settings["provider"],
        model=settings["model"],
        api_key=settings["api_key"],
        api_base=settings["api_base"],
        max_output_tokens=settings["max_output_tokens"],
        temperature=settings["temperature"],
        anthropic_version=settings["anthropic_version"],
        timeout_seconds=settings["timeout_seconds"],
    )


class AIClient:
    def __init__(self, settings: AISettings | None = None):
        self.settings = settings or resolve_ai_settings()

    async def generate_text(self, system_prompt: str, user_prompt: str) -> AITextResponse:
        if self.settings.provider == "openai":
            text = await self._openai_response(system_prompt, user_prompt)
        elif self.settings.provider in {ANTHROPIC_PROVIDER, "compatible"}:
            text = await self._anthropic_message(system_prompt, user_prompt)
        else:
            raise AIProviderError(f"Unsupported AI provider: {self.settings.provider}")
        return AITextResponse(text=text, model=self.settings.model, provider=self.settings.provider)

    def _api_key(self) -> str:
        return self.settings.api_key

    async def _openai_response(self, system_prompt: str, user_prompt: str) -> str:
        endpoint = openai_responses_endpoint(self.settings.api_base)
        payload: dict[str, Any] = {
            "model": self.settings.model,
            "instructions": system_prompt,
            "input": user_prompt,
            "max_output_tokens": self.settings.max_output_tokens,
        }
        if self.settings.temperature is not None:
            payload["temperature"] = self.settings.temperature

        data = await self._post_json(
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

    async def _anthropic_message(self, system_prompt: str, user_prompt: str) -> str:
        endpoint = anthropic_messages_endpoint(self.settings.api_base)
        payload: dict[str, Any] = {
            "model": self.settings.model,
            "max_tokens": self.settings.max_output_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": [{"type": "text", "text": user_prompt}]}],
        }
        if self.settings.temperature is not None:
            payload["temperature"] = self.settings.temperature

        data = await self._post_json(
            endpoint,
            payload,
            {
                "x-api-key": self._api_key(),
                "anthropic-version": self.settings.anthropic_version,
                "Content-Type": "application/json",
            },
        )
        return text_from_anthropic_content(data)

    async def _post_json(self, endpoint: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                endpoint,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.settings.timeout_seconds),
            ) as response:
                response.raise_for_status()
                data = await response.json()
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
