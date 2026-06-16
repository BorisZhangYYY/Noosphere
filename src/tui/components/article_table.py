"""Article table — main dashboard view.

Design principle: one colour system, clear hierarchy, readable at a glance.
Columns are proportioned so title gets the most space; ID and platform are
secondary; status is a compact coloured label; timestamp is muted.
"""
from __future__ import annotations

from rich.table import Table
from rich.text import Text

from src.tui.components.status_badge import status_label
from src.tui.helpers.scanner import DashboardSnapshot
from src.tui.theme import SUCCESS, INFO, WARNING, ERROR, MUTED, HEADING


def build_article_table(snapshot: DashboardSnapshot, show_caption: bool = True) -> Table:
    """Build a Rich Table showing all articles with status badges."""
    parts: list[str] = [f"[bold]{snapshot.total}[/bold] articles"]
    if snapshot.uploaded:
        parts.append(f"[{SUCCESS}]{snapshot.uploaded} uploaded[/{SUCCESS}]")
    if snapshot.reviewed:
        parts.append(f"[{INFO}]{snapshot.reviewed} reviewed[/{INFO}]")
    if snapshot.extracted:
        parts.append(f"[{WARNING}]{snapshot.extracted} extracted[/{WARNING}]")
    if snapshot.failed:
        parts.append(f"[{ERROR}]{snapshot.failed} failed[/{ERROR}]")

    caption = (
        f"[{MUTED}]v view  r review  u upload  m email  i images  p pipeline  o open  t prompts  q quit[/{MUTED}]"
        if show_caption
        else None
    )

    table = Table(
        title=" · ".join(parts),
        caption=caption,
        expand=True,
        pad_edge=False,
        border_style=MUTED,
        show_header=True,
        header_style=f"bold {MUTED}",
    )
    table.add_column("#",        justify="right", style=MUTED, width=4, no_wrap=True)
    table.add_column("Title",    style=HEADING,   width=42, no_wrap=False)
    table.add_column("Platform", style=MUTED,     width=14, no_wrap=True)
    table.add_column("Status",   justify="center", width=14, no_wrap=True)
    table.add_column("Updated",  style=MUTED,     width=10, no_wrap=True)

    for i, art in enumerate(snapshot.articles, 1):
        title = art.title[:40] + "…" if len(art.title) > 40 else art.title
        updated = art.updated_at[:10] if art.updated_at else "-"
        table.add_row(
            str(i),
            Text(title, style=HEADING),
            art.platform_label,
            status_label(art.status),
            updated,
        )

    return table
