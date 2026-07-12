"""Pipeline screen — extract → review → upload in one flow."""
from __future__ import annotations

from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel

from src.core.paths.paths import get_paths
from src.tui.theme import ACCENT, MUTED, SUCCESS, ERROR, PANEL_BORDER, PANEL_PADDING


async def show_pipeline(console: Console) -> None:
    console.clear()
    console.rule(f"[bold {ACCENT}]Run Full Pipeline[/bold {ACCENT}]")
    console.print(f"[{MUTED}]Extract → AI Review → Upload[/{MUTED}]")
    console.print()

    url = Prompt.ask(f"[{ACCENT}]URL[/{ACCENT}]", default="").strip()
    if not url or url in ("q", "quit"):
        return

    from src.graph.graph import run_pipeline_graph

    output_dir = get_paths().output_dir

    # ── Step 1: Extract ─────────────────────────────
    try:
        console.print(f"[{ACCENT}][1/3][/{ACCENT}] Extracting {url[:70]}…")
        hpath = (await run_pipeline_graph(url, output_dir, auto_confirm=True)).hpath
        console.print(f"      [{SUCCESS}]Done[/{SUCCESS}]  {hpath}")
        console.print()
    except Exception as exc:
        console.print(f"      [{ERROR}]Pipeline failed: {exc}[/{ERROR}]")
        Prompt.ask(f"[{MUTED}]Press any key to continue[/{MUTED}]", default="")
        return

    # ── Step 2/3: Review & Upload are handled by the graph ──────────
    console.print(f"[{ACCENT}][2-3/3][/{ACCENT}] AI review and upload completed by the pipeline graph.")
    console.print(f"      [{SUCCESS}]Uploaded:[/{SUCCESS}] {hpath}")

    console.print()
    console.print(Panel(
        f"[bold {SUCCESS}]Pipeline complete![/bold {SUCCESS}]\n"
        f"[{MUTED}]Uploaded to: {hpath}[/{MUTED}]",
        border_style=SUCCESS,
        padding=PANEL_PADDING,
    ))
    Prompt.ask(f"[{MUTED}]Press any key to continue[/{MUTED}]", default="")
