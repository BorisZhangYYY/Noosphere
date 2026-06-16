"""Reusable prompt helpers for the TUI."""
from __future__ import annotations

from rich.console import Console
from rich.prompt import Prompt

from src.tui.theme import ACCENT, ERROR


def ask_cancelable(
    console: Console,
    prompt: str,
    default: str = "",
) -> str | None:
    """Ask for input and treat 'q'/'quit' as cancellation.

    The prompt itself is clean; callers decide whether to render a bottom hint.

    Returns the stripped input, or None if the user cancelled.
    """
    console.print(prompt)
    value = Prompt.ask(
        f"[{ACCENT}]›[/{ACCENT}]",
        default=default,
        show_default=False,
    ).strip()
    if value.lower() in ("q", "quit"):
        return None
    return value


def print_invalid_option(console: Console, choice: str = "") -> None:
    """Print a consistent error message for invalid menu selections."""
    if choice:
        console.print(f"[{ERROR}]Invalid Option: {choice}[/{ERROR}]")
    else:
        console.print(f"[{ERROR}]Invalid Option[/{ERROR}]")
