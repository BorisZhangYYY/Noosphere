"""Status badge — clean text-only labels with semantic colour.

Design principle: taste-skill discourages emoji as default. Colour + weight
encodes status more cleanly than icon + text in a terminal.
"""
from __future__ import annotations

from src.tui.theme import STATUS_TOKEN


def status_label(status: str) -> str:
    """Return a colour-formatted status label for Rich markup.

    Example: ``[yellow]EXTRACTED[/yellow]``
    """
    info = STATUS_TOKEN.get(status, {"label": status.upper(), "colour": "white"})
    return f"[bold {info['colour']}]{info['label']}[/bold {info['colour']}]"
