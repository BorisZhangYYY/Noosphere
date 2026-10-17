"""Expose article prose, excluding provider envelopes and internal summaries."""
from __future__ import annotations

from collections.abc import Awaitable, Callable

from src.core.telemetry import get_event_sink, reset_event_sink, set_event_sink


class ReviewBodyStream:
    """Incrementally decode the root markdown field or a bounded part's body."""

    def __init__(self, protocol: str = "json") -> None:
        self.protocol = protocol
        self.text = ""
        self.raw = ""
        self.depth = 0
        self.quoted = False
        self.role = ""
        self.key = ""
        self.value_next = False
        self.escaped = False
        self.unicode_digits: str | None = None
        self.high_surrogate = ""
        self.pending: list[str] = []

    def push(self, delta: str) -> str:
        if self.protocol == "tag":
            self.raw += delta
            start = self.raw.find("<reviewed_content>")
            if start >= 0:
                body = self.raw[start + len("<reviewed_content>"):]
                end = body.find("</reviewed_content>")
                if end >= 0:
                    body = body[:end]
                else:
                    for size in range(min(len(body), len("</reviewed_content>") - 1), 0, -1):
                        if body.endswith("</reviewed_content>"[:size]):
                            body = body[:-size]
                            break
                self.text = body.lstrip("\r\n")
            return self.text
        self.pending = []
        for char in delta:
            if self.quoted:
                if self.unicode_digits is not None:
                    self.unicode_digits += char
                    if len(self.unicode_digits) == 4:
                        try:
                            self._accept(chr(int(self.unicode_digits, 16)))
                        except ValueError:
                            pass
                        self.unicode_digits = None
                    continue
                if self.escaped:
                    self.escaped = False
                    if char == "u":
                        self.unicode_digits = ""
                    else:
                        self._accept({"n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f"}.get(char, char))
                elif char == "\\":
                    self.escaped = True
                elif char == '"':
                    self.quoted = False
                else:
                    self._accept(char)
            elif char == '"':
                self.quoted = True
                self.role = "body" if self.depth == 1 and self.value_next and self.key == "markdown" else "key" if self.depth == 1 and not self.value_next else "other"
                if self.role == "key":
                    self.key = ""
                self.value_next = False
            elif char in "{[":
                self.depth += 1
            elif char in "}]":
                self.depth -= 1
            elif char == ":" and self.depth == 1:
                self.value_next = True
            elif char == "," and self.depth == 1:
                self.value_next = False
        self.text += "".join(self.pending)
        return self.text

    def _accept(self, char: str) -> None:
        if self.role == "key":
            self.key += char
        elif self.role == "body":
            if "\ud800" <= char <= "\udbff":
                self.high_surrogate = char
                return
            if self.high_surrogate:
                high, self.high_surrogate = self.high_surrogate, ""
                if "\udc00" <= char <= "\udfff":
                    char = chr(0x10000 + ((ord(high) - 0xD800) << 10) + ord(char) - 0xDC00)
            self.pending.append(char)


async def generate_review_text(client, system_prompt: str, user_prompt: str, *, protocol: str = "json",
                               update: Callable[[str], Awaitable[None]] | None = None):
    """Transform only this model call; parallel part streams remain task-local."""
    parent = get_event_sink()
    if parent is None:
        return await client.generate_text(system_prompt, user_prompt)
    parser = ReviewBodyStream(protocol)
    previous = ""

    async def publish(delta: str) -> None:
        nonlocal previous
        body = parser.push(delta)
        if body != previous:
            previous = body
            if update:
                await update(body)
            elif parent:
                await parent("review_output", "", body)

    async def sink(kind: str, message: str, details: str | None) -> None:
        if kind == "ai_output_delta":
            await publish(details or "")
        elif parent:
            await parent(kind, message, details)

    token = set_event_sink(sink)
    try:
        response = await client.generate_text(system_prompt, user_prompt)
        if not parser.text:
            await publish(response.text)
        return response
    finally:
        reset_event_sink(token)
