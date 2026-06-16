"""Noosphere TUI — unified terminal interface for all CLI operations.

Launch via ``python -m src.cli tui``.

Design principles (taste-skill informed):
  - Single accent colour (cyan) for interactive elements
  - Semantic colours for status (green/blue/yellow/red)
  - Consistent panel borders and padding across all screens
  - Clean hierarchy: heading > body > secondary > muted
"""
from __future__ import annotations

import inspect
import traceback

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text

from src.core.paths.paths import get_paths
from src.tui.screens.dashboard import show_dashboard
from src.tui.theme import ACCENT, PANEL_BORDER, PANEL_PADDING, MUTED, ERROR


async def launch_tui() -> None:
    """Main TUI entry point. Show welcome, then enter interactive loop."""
    console = Console()
    output_dir = get_paths().output_dir

    # Welcome banner (shown once)
    _show_welcome(console)

    # Routes — lazily imported to keep startup fast
    routes: dict[str, object] = {}

    def _load_routes() -> None:
        if routes:
            return
        from src.tui.screens.extract import show_extract      # noqa: F811
        from src.tui.screens.review import show_review
        from src.tui.screens.upload import show_upload
        from src.tui.screens.email_send import show_email
        from src.tui.screens.images import show_images
        from src.tui.screens.pipeline import show_pipeline
        from src.tui.screens.prompts import show_prompts
        routes["extract"] = show_extract
        routes["review"] = show_review
        routes["upload"] = show_upload
        routes["email"] = show_email
        routes["images"] = show_images
        routes["pipeline"] = show_pipeline
        routes["prompts"] = show_prompts

    while True:
        action = show_dashboard(console, output_dir)
        if action == "quit":
            console.print(f"\n[{MUTED}]Goodbye.[/{MUTED}]")
            return

        if action is None:
            continue

        _load_routes()
        screen = routes.get(action)
        if screen is None:
            console.print(f"[{ERROR}]Unknown action: {action}[/{ERROR}]")
            continue

        try:
            if inspect.iscoroutinefunction(screen):
                await screen(console)
            else:
                screen(console)
        except KeyboardInterrupt:
            console.print(f"\n[{MUTED}]Cancelled. Returning to menu…[/{MUTED}]")
        except Exception as exc:
            # Catch-all keeps the TUI alive even when a screen crashes.
            console.print(f"[{ERROR}]Unexpected error: {exc}[/{ERROR}]")
            console.print(f"[{MUTED}]{traceback.format_exc()}[/{MUTED}]")
            Prompt.ask(f"[{MUTED}]Press any key to continue[/{MUTED}]", default="")


def _show_welcome(console: Console) -> None:
    """Display a one-time welcome banner."""
    logo = Text("Noosphere", style=f"bold {ACCENT}")
    tagline = Text("Article extraction · AI review · Sharing", style=MUTED)
    content = Text.assemble(logo, "\n", tagline)
    console.print(Panel(
        content,
        border_style=ACCENT,
        padding=PANEL_PADDING,
    ))
