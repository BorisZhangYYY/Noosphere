"""Upload screen — upload to local archive or SiYuan."""
from __future__ import annotations

import json
from datetime import datetime

from rich.console import Console
from rich.prompt import Prompt

from src.core.paths.paths import get_paths
from src.tui.helpers.prompts import ask_cancelable, print_invalid_option
from src.tui.helpers.scanner import scan_articles
from src.tui.components.article_table import build_article_table
from src.tui.theme import ACCENT, MUTED, SUCCESS, ERROR


async def show_upload(console: Console) -> None:
    output_dir = get_paths().output_dir
    snapshot = scan_articles(output_dir)

    if not snapshot.articles:
        console.print(f"[{MUTED}]No articles available for upload.[/{MUTED}]")
        Prompt.ask(f"[{MUTED}]Press any key to continue[/{MUTED}]", default="")
        return

    console.clear()
    console.rule(f"[bold {ACCENT}]Upload[/bold {ACCENT}]")
    console.print(build_article_table(snapshot, show_caption=False))
    console.print()

    choice = ask_cancelable(
        console,
        f"[{ACCENT}]Select # to upload[/{ACCENT}]",
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
        console.print(f"[{ERROR}]reviewed.md not found[/{ERROR}]")
        Prompt.ask(f"[{MUTED}]Press any key to continue[/{MUTED}]", default="")
        return

    console.print()
    console.print(f"[bold]Target:[/bold]")
    console.print(f"  [{ACCENT}]l[/{ACCENT}] Local Archive")
    console.print(f"  [{ACCENT}]s[/{ACCENT}] SiYuan")
    console.print(f"  [{ACCENT}]a[/{ACCENT}] Auto (from config)")
    target_map = {"l": "local", "s": "siyuan", "a": None}
    tc = Prompt.ask(f"[{ACCENT}]Target[/{ACCENT}]", default="a").strip().lower()
    target = target_map.get(tc)
    if tc not in target_map:
        print_invalid_option(console, tc)
        Prompt.ask(f"[{MUTED}]Press any key to continue[/{MUTED}]", default="")
        return

    from src.core.upload.factory import create_adapter
    from src.pipelines.upload import upload_markdown_file

    try:
        adapter = create_adapter(target=target)
    except ValueError as exc:
        console.print(f"[{ERROR}]{exc}[/{ERROR}]")
        console.print(f"[{MUTED}]Tip: add [bold]\"local_archive\": {{\"enabled\": true}}[/bold] to config.json[/{MUTED}]")
        Prompt.ask(f"[{MUTED}]Press any key to continue[/{MUTED}]", default="")
        return

    try:
        with console.status(f"[{ACCENT}]Uploading to {adapter.platform_name}…[/{ACCENT}]", spinner="dots"):
            hpath = await upload_markdown_file(reviewed_path, adapter=adapter)
        console.print(f"[{SUCCESS}]Uploaded to {adapter.platform_name}:[/{SUCCESS}] {hpath}")

        manifest_path = art.dir_path / "manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["uploaded"] = {
                "platform": adapter.platform_name,
                "hpath": hpath,
                "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            }
            manifest_path.write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
    except Exception as exc:
        console.print(f"[{ERROR}]Upload failed: {exc}[/{ERROR}]")

    Prompt.ask(f"[{MUTED}]Press any key to continue[/{MUTED}]", default="")
