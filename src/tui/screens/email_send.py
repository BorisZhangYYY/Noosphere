"""Email send screen."""
from __future__ import annotations

import re

from rich.console import Console
from rich.prompt import Prompt

from src.core.config.config import load_config
from src.core.paths.paths import get_paths
from src.tui.helpers.prompts import ask_cancelable, print_invalid_option
from src.tui.helpers.scanner import scan_articles
from src.tui.components.article_table import build_article_table
from src.tui.theme import ACCENT, MUTED, SUCCESS, ERROR


async def show_email(console: Console) -> None:
    output_dir = get_paths().output_dir
    snapshot = scan_articles(output_dir)
    config = load_config()

    if not config.smtp:
        console.print(f"[{ERROR}]SMTP not configured in config.json[/{ERROR}]")
        Prompt.ask(f"[{MUTED}]Press any key to continue[/{MUTED}]", default="")
        return

    if not snapshot.articles:
        console.print(f"[{MUTED}]No articles available.[/{MUTED}]")
        Prompt.ask(f"[{MUTED}]Press any key to continue[/{MUTED}]", default="")
        return

    console.clear()
    console.rule(f"[bold {ACCENT}]Send Email[/bold {ACCENT}]")
    console.print(build_article_table(snapshot, show_caption=False))
    console.print()

    choice = ask_cancelable(
        console,
        f"[{ACCENT}]Select # to send[/{ACCENT}]",
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
    recipient = ask_cancelable(console, f"[{ACCENT}]Recipient email[/{ACCENT}]")
    if not recipient:
        return

    allowed = config.smtp.allowed_recipients
    if allowed and recipient not in allowed:
        console.print(f"[{ERROR}]Recipient '{recipient}' not in allowed_recipients[/{ERROR}]")
        Prompt.ask(f"[{MUTED}]Press any key to continue[/{MUTED}]", default="")
        return

    reviewed_path = art.dir_path / "reviewed.md"
    if not reviewed_path.exists():
        console.print(f"[{ERROR}]reviewed.md not found[/{ERROR}]")
        Prompt.ask(f"[{MUTED}]Press any key to continue[/{MUTED}]", default="")
        return

    from src.core.email_report import EmailReport, write_report
    from src.integrations.email_adapter import EmailAdapter
    from src.integrations.markdown_to_email import MarkdownToEmailRenderer

    markdown_text = reviewed_path.read_text(encoding="utf-8")
    title_match = re.search(r"^#\s+(.+)$", markdown_text, re.MULTILINE)
    article_title = title_match.group(1).strip() if title_match else art.article_id

    try:
        with console.status(f"[{ACCENT}]Sending email…[/{ACCENT}]", spinner="dots"):
            renderer = MarkdownToEmailRenderer()
            assets_dir = art.dir_path / "assets"
            html_body = renderer.render(
                markdown_text,
                assets_dir=assets_dir if assets_dir.exists() else None,
                subject_title=article_title,
            )
            header = (
                f'<p style="margin-bottom:1em;color:#666;font-size:0.9em">'
                f'[Shared by {config.smtp.sender_name} via Noosphere]</p>'
            )
            subject = f"[Shared by {config.smtp.sender_name} via Noosphere] {article_title}"
            adapter = EmailAdapter(
                host=config.smtp.host, port=config.smtp.port,
                user=config.smtp.user, password=config.smtp.password,
                sender_name=config.smtp.sender_name,
                allowed_recipients=allowed,
            )
            result = adapter.send(
                article_id=art.article_id, recipient=recipient,
                html_body=header + html_body, subject=subject,
            )
            report = EmailReport(
                article_id=art.article_id, recipient=recipient,
                subject=subject, success=result.success,
                error=result.message if not result.success else None,
            )
            write_report(art.article_id, report, get_paths())
        if result.success:
            console.print(f"[{SUCCESS}]Email sent to {recipient}[/{SUCCESS}]")
        else:
            console.print(f"[{ERROR}]Failed: {result.message}[/{ERROR}]")
    except Exception as exc:
        console.print(f"[{ERROR}]Error: {exc}[/{ERROR}]")

    Prompt.ask(f"[{MUTED}]Press any key to continue[/{MUTED}]", default="")
