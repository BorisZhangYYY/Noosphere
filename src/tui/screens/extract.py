"""Extract screen — single URL or batch file extraction."""
from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.progress import Progress, TextColumn, BarColumn, TimeElapsedColumn
from rich.table import Table

from src.core.paths.paths import get_paths
from src.core.paths.output_paths import find_existing_article_dir
from src.tui.helpers.prompts import ask_cancelable, print_invalid_option
from src.tui.theme import ACCENT, MUTED, SUCCESS, WARNING, ERROR, PANEL_BORDER, PANEL_PADDING


async def show_extract(console: Console) -> None:
    """Interactive extraction screen."""
    console.clear()
    console.rule(f"[bold {ACCENT}]Extract Articles[/bold {ACCENT}]")
    console.print()
    console.print(f"  [{ACCENT}]1[/{ACCENT}] Single URL")
    console.print(f"  [{ACCENT}]2[/{ACCENT}] Batch file (one URL per line)")
    console.print()
    choice = Prompt.ask(f"[{ACCENT}]Choice[/{ACCENT}]", default="").strip().lower()

    if choice == "1":
        await _extract_single(console)
    elif choice == "2":
        await _extract_batch(console)
    elif choice in ("q", "quit", ""):
        return
    else:
        print_invalid_option(console, choice)
        Prompt.ask(f"[{MUTED}]Press any key to continue[/{MUTED}]", default="")


async def _extract_single(console: Console) -> None:
    url = ask_cancelable(console, f"[{ACCENT}]URL[/{ACCENT}]")
    if not url:
        return

    from src.pipelines.extract import extract_to_output

    output_dir = get_paths().output_dir
    try:
        with console.status(f"[{ACCENT}]Extracting {url[:60]}…[/{ACCENT}]", spinner="dots"):
            path = await extract_to_output(url, output_dir)
        console.print(f"[{SUCCESS}]Extracted:[/{SUCCESS}] {path}")
    except Exception as exc:
        console.print(f"[{ERROR}]Failed: {exc}[/{ERROR}]")

    Prompt.ask(f"[{MUTED}]Press any key to continue[/{MUTED}]", default="")


async def _extract_batch(console: Console) -> None:
    file_path = ask_cancelable(console, f"[{ACCENT}]Batch file path[/{ACCENT}]")
    if not file_path:
        return

    batch_path = Path(file_path)
    if not batch_path.exists():
        console.print(f"[{ERROR}]File not found: {batch_path}[/{ERROR}]")
        Prompt.ask(f"[{MUTED}]Press any key to continue[/{MUTED}]", default="")
        return

    urls: list[str] = []
    for line in batch_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            urls.append(line)

    if not urls:
        console.print(f"[{WARNING}]No URLs found in file.[/{WARNING}]")
        Prompt.ask(f"[{MUTED}]Press any key to continue[/{MUTED}]", default="")
        return

    console.print(f"[{MUTED}]Found {len(urls)} URLs. Extracting…[/{MUTED}]")
    await _run_batch_extract(console, urls)


async def _run_batch_extract(console: Console, urls: list[str]) -> None:
    from src.pipelines.extract import extract_to_output

    output_dir = get_paths().output_dir
    ok = skip = fail = 0

    progress = Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    )

    with progress:
        task = progress.add_task("Extracting…", total=len(urls))
        for url in urls:
            try:
                existing = find_existing_article_dir(output_dir, url)
                if existing is not None:
                    progress.console.print(f"[{WARNING}]Skip[/{WARNING}] {url}")
                    skip += 1
                    progress.advance(task)
                    continue
                await extract_to_output(url, output_dir)
                ok += 1
                progress.console.print(f"[{SUCCESS}]Done[/{SUCCESS}]  {url}")
            except Exception as exc:
                fail += 1
                progress.console.print(f"[{ERROR}]Fail[/{ERROR}]  {url}: {exc}")
            progress.advance(task)

    table = Table(title="Extraction Summary", border_style=PANEL_BORDER)
    table.add_column("Result", style=ACCENT)
    table.add_column("Count", justify="right")
    table.add_row(f"[{SUCCESS}]Successful[/{SUCCESS}]", str(ok))
    table.add_row(f"[{WARNING}]Skipped[/{WARNING}]", str(skip))
    table.add_row(f"[{ERROR}]Failed[/{ERROR}]", str(fail))
    console.print(table)
    Prompt.ask(f"[{MUTED}]Press any key to continue[/{MUTED}]", default="")
