"""Pipeline screen — extract → review → upload in one flow."""
from __future__ import annotations

import json
from datetime import datetime

from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel

from src.core.paths.paths import get_paths
from src.core.upload.factory import create_adapter
from src.tui.theme import ACCENT, MUTED, SUCCESS, ERROR, WARNING, PANEL_BORDER, PANEL_PADDING


async def show_pipeline(console: Console) -> None:
    console.clear()
    console.rule(f"[bold {ACCENT}]Run Full Pipeline[/bold {ACCENT}]")
    console.print(f"[{MUTED}]Extract → AI Review → Upload[/{MUTED}]")
    console.print()

    url = Prompt.ask(f"[{ACCENT}]URL[/{ACCENT}]", default="").strip()
    if not url or url in ("q", "quit"):
        return

    output_dir = get_paths().output_dir

    # ── Step 1: Extract ─────────────────────────────
    try:
        from src.pipelines.extract import extract_to_output
        console.print(f"[{ACCENT}][1/3][/{ACCENT}] Extracting {url[:70]}…")
        reviewed_path = await extract_to_output(url, output_dir)
        console.print(f"      [{SUCCESS}]Done[/{SUCCESS}]  {reviewed_path}")
        console.print()
    except Exception as exc:
        console.print(f"      [{ERROR}]Extract failed: {exc}[/{ERROR}]")
        Prompt.ask(f"[{MUTED}]Press any key to continue[/{MUTED}]", default="")
        return

    # ── Step 2: AI Review ──────────────────────────
    try:
        from src.pipelines.ai_review import run_ai_review

        # Show detailed progress — the pipeline internally runs:
        # image analysis, then up to N rewrite attempts with validation
        console.print(f"[{ACCENT}][2/3][/{ACCENT}] AI reviewing…")
        console.print(f"      [dim]Phase: image analysis → rewrite → validate (up to 3 attempts)[/dim]")

        with console.status(f"[{ACCENT}]AI reviewing {reviewed_path.name}…[/{ACCENT}]", spinner="dots"):
            result = await run_ai_review(reviewed_path)

        if result.ok:
            attempts_text = f"{result.attempts} attempt(s)"
            console.print(f"      [{SUCCESS}]AI review passed ({attempts_text})[/{SUCCESS}]")
            # Show validation summary
            if result.validation.issues:
                console.print(f"      [dim]Validation notes: {len(result.validation.issues)} minor issue(s)[/dim]")
        else:
            console.print(f"      [{ERROR}]AI review failed after {result.attempts} attempt(s)[/{ERROR}]")
            from src.core.review.review_validation import format_validation_issues
            console.print(f"      [dim]{format_validation_issues(result.validation.issues)}[/dim]")
            Prompt.ask(f"[{MUTED}]Press any key to continue[/{MUTED}]", default="")
            return
        console.print()
    except Exception as exc:
        console.print(f"      [{ERROR}]AI review error: {exc}[/{ERROR}]")
        Prompt.ask(f"[{MUTED}]Press any key to continue[/{MUTED}]", default="")
        return

    # ── Step 3: Upload ─────────────────────────────
    try:
        from src.pipelines.upload import upload_markdown_file
        adapter = create_adapter()
        console.print(f"[{ACCENT}][3/3][/{ACCENT}] Uploading to [bold]{adapter.platform_name}[/bold]…")
        hpath = await upload_markdown_file(reviewed_path)
        console.print(f"      [{SUCCESS}]Uploaded:[/{SUCCESS}] {hpath}")

        manifest_path = reviewed_path.with_name("manifest.json")
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["uploaded"] = {
                "platform": adapter.platform_name,
                "hpath": hpath,
                "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            }
            manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except Exception as exc:
        console.print(f"      [{ERROR}]Upload failed: {exc}[/{ERROR}]")

    console.print()
    console.print(Panel(
        f"[bold {SUCCESS}]Pipeline complete![/bold {SUCCESS}]\n"
        f"[{MUTED}]Article: {reviewed_path}[/{MUTED}]",
        border_style=SUCCESS,
        padding=PANEL_PADDING,
    ))
    Prompt.ask(f"[{MUTED}]Press any key to continue[/{MUTED}]", default="")
