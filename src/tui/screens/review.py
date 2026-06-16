"""AI Review screen."""
from __future__ import annotations

from rich.console import Console
from rich.prompt import Prompt

from src.core.paths.paths import get_paths
from src.tui.helpers.prompts import ask_cancelable, print_invalid_option
from src.tui.helpers.scanner import scan_articles
from src.tui.components.article_table import build_article_table
from src.tui.theme import ACCENT, MUTED, SUCCESS, ERROR


async def show_review(console: Console) -> None:
    output_dir = get_paths().output_dir
    snapshot = scan_articles(output_dir)

    if not snapshot.articles:
        console.print(f"[{MUTED}]No articles available for review.[/{MUTED}]")
        Prompt.ask(f"[{MUTED}]Press any key to continue[/{MUTED}]", default="")
        return

    console.clear()
    console.rule(f"[bold {ACCENT}]AI Review[/bold {ACCENT}]")
    console.print(build_article_table(snapshot, show_caption=False))
    console.print()

    choice = ask_cancelable(
        console,
        f"[{ACCENT}]Select # to review[/{ACCENT}]",
    )
    if choice is None:
        return
    if not choice:
        print_invalid_option(console)
        Prompt.ask(f"[{MUTED}]Press any key to continue[/{MUTED}]", default="")
        return

    try:
        idx = int(choice) - 1
        if not (0 <= idx < len(snapshot.articles)):
            raise ValueError
    except ValueError:
        print_invalid_option(console, choice)
        Prompt.ask(f"[{MUTED}]Press any key to continue[/{MUTED}]", default="")
        return

    art = snapshot.articles[idx]
    reviewed_path = art.dir_path / "reviewed.md"
    if not reviewed_path.exists():
        console.print(f"[{ERROR}]reviewed.md not found in {art.dir_path}[/{ERROR}]")
        Prompt.ask(f"[{MUTED}]Press any key to continue[/{MUTED}]", default="")
        return

    from src.pipelines.ai_review import run_ai_review
    from src.core.review.review_validation import format_validation_issues

    try:
        # Show what we're about to do so the user knows what to expect
        console.print()
        console.print(f"[bold]Article:[/bold] {art.title[:60]}")
        console.print(f"[{MUTED}]Phases: image analysis → AI rewrite → validation (retries if needed)[/{MUTED}]")
        console.print()

        with console.status(
            f"[{ACCENT}]AI reviewing… (this may take 30-90s for long articles)[/{ACCENT}]",
            spinner="dots",
        ):
            result = await run_ai_review(reviewed_path)

        console.print()
        if result.ok:
            console.print(f"[{SUCCESS}]AI review passed[/{SUCCESS}]")
            console.print(f"  Attempts: {result.attempts}")
            console.print(f"  Output:   {result.reviewed_path}")
        else:
            console.print(f"[{ERROR}]AI review failed after {result.attempts} attempt(s)[/{ERROR}]")
            console.print(f"  {format_validation_issues(result.validation.issues)}")
    except Exception as exc:
        console.print(f"[{ERROR}]Error: {exc}[/{ERROR}]")

    console.print()
    Prompt.ask(f"[{MUTED}]Press any key to continue[/{MUTED}]", default="")
