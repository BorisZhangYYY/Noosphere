"""Progress panel component — async operation wrappers."""
from __future__ import annotations

from typing import TypeVar

from rich.console import Console

from src.tui.theme import ACCENT

T = TypeVar("T")


async def run_with_spinner(
    console: Console,
    message: str,
    coro,
) -> T:
    """Run an async coroutine with a spinner status message.

    Returns the coroutine's result or raises the exception.
    """
    with console.status(f"[{ACCENT}]{message}…[/{ACCENT}]", spinner="dots"):
        return await coro
