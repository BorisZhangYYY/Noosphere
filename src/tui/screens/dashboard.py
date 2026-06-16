"""Dashboard screen — article list with inline actions.

Design principle (taste-skill): single clear entry point, grouped actions,
consistent colour encoding. No emoji — colour alone carries the semantics.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from src.tui.helpers.scanner import scan_articles, DashboardSnapshot
from src.tui.helpers.prompts import ask_cancelable, print_invalid_option
from src.tui.helpers.editor import open_in_editor
from src.tui.components.article_table import build_article_table
from src.tui.theme import ACCENT, MUTED, ERROR, SUCCESS, PANEL_BORDER, PANEL_PADDING, HEADING


def show_dashboard(console: Console, output_dir: Path) -> str | None:
    """Display the dashboard and return the next action.

    Returns:
        "extract" | "review" | "upload" | "email" | "images" |
        "pipeline" | "prompts" | "quit" | None (stay in dashboard).
    """
    snapshot = scan_articles(output_dir)

    while True:
        console.clear()
        console.rule(f"[bold {ACCENT}]Noosphere[/bold {ACCENT}]")

        if not snapshot.articles:
            console.print(Panel(
                f"[{MUTED}]No articles found in outputs/.[/{MUTED}]\n"
                f"[{MUTED}]Press [{ACCENT}]e[{MUTED}] to extract your first article.[/{MUTED}]",
                title="Dashboard",
                border_style=PANEL_BORDER,
                padding=PANEL_PADDING,
            ))
        else:
            console.print(build_article_table(snapshot))

        # ── Actions ──────────────────────────────────
        console.print()

        cmd = Prompt.ask(
            f"[{ACCENT}]›[/{ACCENT}]",
            default="",
            show_default=False,
        ).strip().lower()

        if cmd in ("q", "quit", "exit"):
            return "quit"
        if cmd == "e":
            return "extract"
        if cmd == "r":
            return "review"
        if cmd == "u":
            return "upload"
        if cmd == "m":
            return "email"
        if cmd == "i":
            return "images"
        if cmd == "p":
            return "pipeline"
        if cmd == "v":
            _view_article(console, snapshot)
            snapshot = scan_articles(output_dir)
        elif cmd == "o":
            _open_in_finder(console, snapshot)
            snapshot = scan_articles(output_dir)
        elif cmd == "t":
            return "prompts"
        elif cmd:
            print_invalid_option(console, cmd)
            Prompt.ask(f"[{MUTED}]Press any key to continue[/{MUTED}]", default="")


def _select_article(snapshot: DashboardSnapshot, console: Console, action: str) -> int | None:
    """Prompt the user to select an article by number."""
    if not snapshot.articles:
        console.print(f"[{MUTED}]No articles available.[/{MUTED}]")
        return None

    console.print(build_article_table(snapshot, show_caption=False))
    console.print()

    choice = ask_cancelable(
        console,
        f"[{ACCENT}]Select # to {action}[/{ACCENT}]",
    )
    if choice is None:
        return None
    if not choice:
        print_invalid_option(console)
        Prompt.ask(f"[{MUTED}]Press any key to continue[/{MUTED}]", default="")
        return None
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(snapshot.articles):
            return idx
        print_invalid_option(console, choice)
    except ValueError:
        print_invalid_option(console, choice)
    Prompt.ask(f"[{MUTED}]Press any key to continue[/{MUTED}]", default="")
    return None


def _view_article(console: Console, snapshot: DashboardSnapshot) -> None:
    """Open the article in $EDITOR and offer an image menu afterwards."""
    idx = _select_article(snapshot, console, "view")
    if idx is None:
        return
    art = snapshot.articles[idx]
    reviewed_path = art.dir_path / "reviewed.md"
    if not reviewed_path.exists():
        console.print(f"[{ERROR}]reviewed.md not found in {art.dir_path}[/{ERROR}]")
        return

    # Collect images so we can offer a post-view menu even though the article
    # is opened as raw Markdown in the user's editor.
    images = _collect_images(reviewed_path)

    open_in_editor(reviewed_path)

    # After the editor closes, let the user open images by number.
    if images:
        _show_image_menu(console, images)


def _collect_images(reviewed_path: Path) -> list[tuple[str, Path]]:
    """Return [(alt_text, absolute_path), ...] for images in reviewed.md."""
    images: list[tuple[str, Path]] = []
    article_dir = reviewed_path.parent
    if not reviewed_path.exists():
        return images
    md_text = reviewed_path.read_text(encoding="utf-8")
    for m in re.finditer(r"!\[([^\]]*)\]\(([^)]+)\)", md_text):
        alt = m.group(1) or "image"
        img_path = (article_dir / m.group(2)).resolve()
        if img_path.exists():
            images.append((alt, img_path))
    return images


def _show_image_menu(console: Console, images: list[tuple[str, Path]]) -> None:
    """Show a numbered menu to open article images after viewing."""
    console.print()
    console.print(f"[{MUTED}]── Images ──[/{MUTED}]")
    for i, (alt, _path) in enumerate(images, 1):
        console.print(f"  [{ACCENT}]{i}[/{ACCENT}] {alt}")
    choice = Prompt.ask(
        f"[{ACCENT}]Image # to open (q to skip)[/{ACCENT}]",
        default="",
        show_default=False,
    ).strip().lower()
    if choice in ("", "q", "quit"):
        return
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(images):
            _open_path(images[idx][1])
        else:
            print_invalid_option(console, choice)
    except ValueError:
        print_invalid_option(console, choice)


def _open_path(path: Path) -> None:
    """Open a path with the OS default application."""
    import platform

    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.run(["open", str(path)])
        elif system == "Windows":
            subprocess.run(["explorer", str(path)])
        else:
            subprocess.run(["xdg-open", str(path)])
    except Exception as exc:
        # Errors here are non-fatal; the caller already exited the editor.
        print(f"Could not open {path}: {exc}")


def _open_in_finder(console: Console, snapshot: DashboardSnapshot) -> None:
    idx = _select_article(snapshot, console, "open")
    if idx is None:
        return
    art = snapshot.articles[idx]
    path = art.dir_path
    _open_path(path)
    console.print(f"[{SUCCESS}]Opened: {path}[/{SUCCESS}]")
