from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import aiohttp

from src.core.config.config import load_config
from src.core.config.schema import Config
from src.core.telemetry import emit_event, has_event_sink


class AIProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class AISettings:
    provider: str
    model: str
    api_key: str
    api_base: str
    max_output_tokens: int
    api_format: str = ""
    temperature: float | None = None
    anthropic_version: str = "2023-06-01"
    timeout_seconds: int = 600


@dataclass(frozen=True)
class AITextResponse:
    text: str
    model: str
    provider: str


def resolve_ai_settings(config: Config | None = None, provider_name: str | None = None) -> AISettings:
    if config is None:
        config = load_config()
    settings = config.resolve_ai_settings(provider_name)
    return AISettings(
        provider=settings["provider"],
        model=settings["model"],
        api_key=settings["api_key"],
        api_base=settings["api_base"],
        max_output_tokens=settings["max_output_tokens"],
        api_format=settings["api_format"],
        temperature=settings["temperature"],
        anthropic_version=settings["anthropic_version"],
        timeout_seconds=settings["timeout_seconds"],
    )


class AIClient:
    def __init__(self, settings: AISettings | None = None):
        self.settings = settings or resolve_ai_settings()

    async def generate_text(self, system_prompt: str, user_prompt: str) -> AITextResponse:
        api_format = self._api_format()
        if has_event_sink() and api_format == "openai_responses":
            text = await self._openai_response_stream(system_prompt, user_prompt)
        elif has_event_sink() and api_format == "openai_chat":
            text = await self._openai_chat_stream(system_prompt, user_prompt)
        elif has_event_sink() and api_format == "anthropic":
            text = await self._anthropic_message_stream(system_prompt, user_prompt)
        elif api_format == "openai_responses":
            text = await self._openai_response(system_prompt, user_prompt)
        elif api_format == "openai_chat":
            text = await self._openai_chat_response(system_prompt, user_prompt)
        elif api_format == "anthropic":
            text = await self._anthropic_message(system_prompt, user_prompt)
        else:
            raise AIProviderError(f"Unsupported AI API format: {api_format}")
        return AITextResponse(text=text, model=self.settings.model, provider=self.settings.provider)

    async def _openai_response_stream(self, system_prompt: str, user_prompt: str) -> str:
        payload: dict[str, Any] = {
            "model": self.settings.model,
            "instructions": system_prompt,
            "input": user_prompt,
            "max_output_tokens": self.settings.max_output_tokens,
            "stream": True,
        }
        if self.settings.temperature is not None:
            payload["temperature"] = self.settings.temperature

        def extract(data: dict[str, Any]) -> str:
            if data.get("type") == "response.output_text.delta":
                return str(data.get("delta") or "")
            return ""

        return await self._stream_text(
            openai_responses_endpoint(self.settings.api_base),
            payload,
            {"Authorization": f"Bearer {self._api_key()}", "Content-Type": "application/json"},
            extract,
            lambda data: str(data.get("output_text") or "") or text_from_openai_output(data),
        )

    async def _openai_chat_stream(self, system_prompt: str, user_prompt: str) -> str:
        payload: dict[str, Any] = {
            "model": self.settings.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": self.settings.max_output_tokens,
            "stream": True,
        }
        if self.settings.temperature is not None:
            payload["temperature"] = self.settings.temperature

        def extract(data: dict[str, Any]) -> str:
            choices = data.get("choices") or []
            if not choices or not isinstance(choices[0], dict):
                return ""
            content = (choices[0].get("delta") or {}).get("content")
            return content if isinstance(content, str) else ""

        return await self._stream_text(
            openai_chat_endpoint(self.settings.api_base),
            payload,
            {"Authorization": f"Bearer {self._api_key()}", "Content-Type": "application/json"},
            extract,
            text_from_openai_chat,
        )

    async def _anthropic_message_stream(self, system_prompt: str, user_prompt: str) -> str:
        payload: dict[str, Any] = {
            "model": self.settings.model,
            "max_tokens": self.settings.max_output_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": [{"type": "text", "text": user_prompt}]}],
            "stream": True,
        }
        if self.settings.temperature is not None:
            payload["temperature"] = self.settings.temperature

        def extract(data: dict[str, Any]) -> str:
            if data.get("type") != "content_block_delta":
                return ""
            delta = data.get("delta") or {}
            return str(delta.get("text") or "") if delta.get("type") == "text_delta" else ""

        return await self._stream_text(
            anthropic_messages_endpoint(self.settings.api_base),
            payload,
            {
                "x-api-key": self._api_key(),
                "anthropic-version": self.settings.anthropic_version,
                "Content-Type": "application/json",
            },
            extract,
            text_from_anthropic_content,
        )

    async def _stream_text(
        self,
        endpoint: str,
        payload: dict[str, Any],
        headers: dict[str, str],
        extract_delta,
        parse_fallback,
    ) -> str:
        chunks: list[str] = []
        timeout = aiohttp.ClientTimeout(
            total=self.settings.timeout_seconds,
            connect=60,
            sock_read=self.settings.timeout_seconds,
            sock_connect=60,
        )
        async with aiohttp.ClientSession() as session:
            async with session.post(endpoint, json=payload, headers=headers, timeout=timeout) as response:
                response.raise_for_status()
                if "text/event-stream" not in response.headers.get("Content-Type", ""):
                    data = await response.json()
                    if not isinstance(data, dict):
                        raise AIProviderError(f"{self.settings.provider} API returned an invalid response")
                    text = parse_fallback(data)
                    if text:
                        await emit_event("ai_output_delta", "", text)
                    return text

                async for raw_line in response.content:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line.startswith("data:"):
                        continue
                    payload_text = line[5:].strip()
                    if not payload_text or payload_text == "[DONE]":
                        continue
                    try:
                        data = json.loads(payload_text)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(data, dict):
                        continue
                    delta = extract_delta(data)
                    if delta:
                        chunks.append(delta)
                        await emit_event("ai_output_delta", "", delta)
        text = "".join(chunks)
        if not text.strip():
            raise AIProviderError(f"{self.settings.provider} API returned an empty streamed response")
        return text

    async def generate_vision(self, system_prompt: str, content: list[dict]) -> AITextResponse:
        """Generate response with vision input (images + text).

        Args:
            system_prompt: The system/instruction prompt.
            content: A list of content dicts following Anthropic format:
                [{"type": "image", "source": {"type": "base64", "media_type": "...", "data": "..."}},
                 {"type": "text", "text": "..."}]

        Returns:
            AITextResponse with the model's analysis text.
        """
        api_format = self._api_format()
        if api_format == "openai_responses":
            text = await self._openai_vision_response(system_prompt, content)
        elif api_format == "openai_chat":
            text = await self._openai_chat_vision_response(system_prompt, content)
        elif api_format == "anthropic":
            text = await self._anthropic_vision_message(system_prompt, content)
        else:
            raise AIProviderError(f"Unsupported AI API format: {api_format}")
        return AITextResponse(text=text, model=self.settings.model, provider=self.settings.provider)

    def _api_key(self) -> str:
        return self.settings.api_key

    def _api_format(self) -> str:
        if self.settings.api_format:
            return self.settings.api_format
        return "openai_responses" if self.settings.provider == "openai" else "anthropic"

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

    async def _openai_chat_response(self, system_prompt: str, user_prompt: str) -> str:
        endpoint = openai_chat_endpoint(self.settings.api_base)
        payload: dict[str, Any] = {
            "model": self.settings.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": self.settings.max_output_tokens,
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
        return text_from_openai_chat(data)

    async def _anthropic_vision_message(self, system_prompt: str, content: list[dict]) -> str:
        endpoint = anthropic_messages_endpoint(self.settings.api_base)
        payload: dict[str, Any] = {
            "model": self.settings.model,
            "max_tokens": min(self.settings.max_output_tokens, 1024),
            "system": system_prompt,
            "messages": [{"role": "user", "content": content}],
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

    async def _openai_vision_response(self, system_prompt: str, content: list[dict]) -> str:
        endpoint = openai_responses_endpoint(self.settings.api_base)
        openai_input: list[dict] = []
        for item in content:
            if item.get("type") == "text":
                openai_input.append({"type": "input_text", "text": item["text"]})
            elif item.get("type") == "image":
                source = item.get("source", {})
                if source.get("type") == "base64":
                    media_type = source.get("media_type", "image/jpeg")
                    data = source.get("data", "")
                    openai_input.append({
                        "type": "input_image",
                        "image_url": {"url": f"data:{media_type};base64,{data}"},
                    })

        payload: dict[str, Any] = {
            "model": self.settings.model,
            "instructions": system_prompt,
            "input": openai_input,
            "max_output_tokens": min(self.settings.max_output_tokens, 1024),
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

    async def _openai_chat_vision_response(self, system_prompt: str, content: list[dict]) -> str:
        chat_content: list[dict[str, Any]] = []
        for item in content:
            if item.get("type") == "text":
                chat_content.append({"type": "text", "text": item["text"]})
            elif item.get("type") == "image":
                source = item.get("source", {})
                if source.get("type") == "base64":
                    media_type = source.get("media_type", "image/jpeg")
                    chat_content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:{media_type};base64,{source.get('data', '')}"},
                    })
        data = await self._post_json(
            openai_chat_endpoint(self.settings.api_base),
            {
                "model": self.settings.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": chat_content},
                ],
                "max_tokens": min(self.settings.max_output_tokens, 1024),
            },
            {
                "Authorization": f"Bearer {self._api_key()}",
                "Content-Type": "application/json",
            },
        )
        return text_from_openai_chat(data)

    async def _post_json(self, endpoint: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                endpoint,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.settings.timeout_seconds, connect=60, sock_read=self.settings.timeout_seconds, sock_connect=60),
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


def text_from_openai_chat(data: dict[str, Any]) -> str:
    choices = data.get("choices") or []
    if choices and isinstance(choices[0], dict):
        message = choices[0].get("message") or {}
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str) and content.strip():
            return content.strip()
    raise AIProviderError("OpenAI chat response did not contain message content")


def text_from_anthropic_content(data: dict[str, Any]) -> str:
    chunks: list[str] = []
    for content in data.get("content") or []:
        if isinstance(content, dict) and content.get("type") == "text" and isinstance(content.get("text"), str):
            chunks.append(content["text"])
    if chunks:
        return "\n".join(chunks).strip()
    raise AIProviderError("Anthropic response did not contain text content")


def openai_responses_endpoint(api_base: str) -> str:
    return _api_endpoint(api_base, "/responses")


def openai_chat_endpoint(api_base: str) -> str:
    return _api_endpoint(api_base, "/chat/completions")


def anthropic_messages_endpoint(api_base: str) -> str:
    return _api_endpoint(api_base, "/messages")


def _api_endpoint(api_base: str, endpoint_suffix: str) -> str:
    parts = urlsplit(api_base)
    path = parts.path.rstrip("/")
    if not path.endswith(endpoint_suffix):
        path = f"{path}{endpoint_suffix}" if path.endswith("/v1") else f"{path}/v1{endpoint_suffix}"
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))
