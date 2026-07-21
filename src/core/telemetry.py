"""Task-local progress events for interactive pipeline runs."""
from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Awaitable, Callable


EventSink = Callable[[str, str, str | None], Awaitable[None]]
_event_sink: ContextVar[EventSink | None] = ContextVar("noosphere_event_sink", default=None)


def set_event_sink(sink: EventSink) -> Token:
    """Install an event sink for the current asynchronous task."""
    return _event_sink.set(sink)


def reset_event_sink(token: Token) -> None:
    """Restore the previous task-local event sink."""
    _event_sink.reset(token)


def suspend_event_sink() -> Token:
    """Temporarily disable streaming events for a nested AI operation."""
    return _event_sink.set(None)


async def emit_event(kind: str, message: str, details: str | None = None) -> None:
    """Emit a progress event when the caller is running in an observed task."""
    sink = _event_sink.get()
    if sink is not None:
        await sink(kind, message, details)


def has_event_sink() -> bool:
    """Return whether the current task has an interactive progress consumer."""
    return _event_sink.get() is not None
