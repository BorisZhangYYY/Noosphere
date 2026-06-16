"""Markdown viewer — renders Markdown in a Rich Panel."""
from __future__ import annotations

from pathlib import Path

from rich.markdown import Markdown as RichMarkdown
from rich.panel import Panel
from rich.console import Console

from src.tui.theme import ERROR, PANEL_BORDER, PANEL_PADDING


def render_markdown_file(file_path: Path, console: Console) -> None:
    """Render a Markdown file in a Panel with syntax highlighting."""
    if not file_path.exists():
        console.print(f"[{ERROR}]File not found: {file_path}[/{ERROR}]")
        return
    render_markdown_text(file_path.read_text(encoding="utf-8"), title=file_path.name, console=console)


def render_markdown_text(text: str, title: str = "", console: Console | None = None) -> None:
    """Render Markdown text inside a styled Panel."""
    _console = console or Console()
    md = RichMarkdown(text, code_theme="monokai")
    _console.print(Panel(
        md,
        title=f"[bold]{title}[/bold]" if title else None,
        border_style=PANEL_BORDER,
        padding=PANEL_PADDING,
    ))
