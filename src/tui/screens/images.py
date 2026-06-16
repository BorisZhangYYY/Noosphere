"""Images screen — review and restore images removed by AI filtering.

Fuses the original `review-images --preview` HTML functionality directly
into the TUI: list removed images with AI descriptions, restore one or all,
generate HTML preview for browser viewing.
"""
from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from src.core.paths.paths import get_paths
from src.tui.helpers.prompts import ask_cancelable, print_invalid_option
from src.tui.helpers.scanner import scan_articles
from src.tui.components.article_table import build_article_table
from src.tui.theme import ACCENT, MUTED, SUCCESS, WARNING, ERROR, PANEL_BORDER, PANEL_PADDING


def show_images(console: Console) -> None:
    output_dir = get_paths().output_dir
    snapshot = scan_articles(output_dir)

    if not snapshot.articles:
        console.print(f"[{MUTED}]No articles available.[/{MUTED}]")
        Prompt.ask(f"[{MUTED}]Press any key to continue[/{MUTED}]", default="")
        return

    console.clear()
    console.rule(f"[bold {ACCENT}]Image Review[/bold {ACCENT}]")
    console.print(build_article_table(snapshot, show_caption=False))
    console.print()

    choice = ask_cancelable(
        console,
        f"[{ACCENT}]Select #[/{ACCENT}]",
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

    _manage_images(console, snapshot.articles[idx].dir_path)


def _manage_images(console: Console, article_dir: Path) -> None:
    manifest_path = article_dir / "manifest.json"
    if not manifest_path.exists():
        console.print(f"[{ERROR}]manifest.json not found[/{ERROR}]")
        Prompt.ask(f"[{MUTED}]Press any key to continue[/{MUTED}]", default="")
        return

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    image_filter = manifest.get("image_filter", {})
    removed_files = list(image_filter.get("removed_files", []))
    descriptions = image_filter.get("image_descriptions", {})

    removed_dir = article_dir / "removed"
    assets_dir = article_dir / "assets"

    if not removed_files and removed_dir.exists() and removed_dir.is_dir():
        removed_files = [
            str(p.relative_to(article_dir))
            for p in removed_dir.iterdir() if p.is_file()
        ]

    while True:
        console.clear()
        console.rule(f"[bold {ACCENT}]Image Review — {article_dir.name}[/bold {ACCENT}]")

        if not removed_files:
            console.print(Panel(
                f"[{SUCCESS}]No images were removed. All images are preserved.[/{SUCCESS}]",
                border_style=SUCCESS, padding=PANEL_PADDING,
            ))
            Prompt.ask(f"[{MUTED}]Press any key to go back[/{MUTED}]", default="")
            return

        table = Table(
            title=f"Removed Images ({len(removed_files)} total)",
            border_style=PANEL_BORDER,
            header_style=f"bold {MUTED}",
        )
        table.add_column("#",       justify="right", style=MUTED, width=4)
        table.add_column("Filename", style="bold",   width=26)
        table.add_column("AI Description", style=MUTED, width=52)
        table.add_column("Available", justify="center", width=12)

        available_count = 0
        for i, removed_path in enumerate(removed_files, 1):
            filename = Path(removed_path).name
            desc = descriptions.get(removed_path, descriptions.get(f"assets/{filename}", ""))
            desc = (desc[:50] + "…") if len(desc) > 50 else desc or f"[{MUTED}]No description[/{MUTED}]"

            removed_file = removed_dir / filename
            if not removed_file.exists():
                for f in removed_dir.iterdir():
                    if f.stem.startswith(Path(filename).stem):
                        removed_file = f
                        filename = f.name
                        break
            is_available = removed_file.exists()
            if is_available:
                available_count += 1
            avail = f"[{SUCCESS}]Yes[/{SUCCESS}]" if is_available else f"[{ERROR}]No[/{ERROR}]"
            table.add_row(str(i), filename, desc, avail)

        console.print(table)
        console.print(f"[{MUTED}]{available_count}/{len(removed_files)} files on disk[/{MUTED}]")
        console.print()

        cmd = Prompt.ask(f"[{ACCENT}]Action[/{ACCENT}]", default="").strip()
        if cmd in ("q", "quit"):
            return
        elif cmd == "R":
            _restore_all(console, removed_dir, assets_dir, removed_files)
        elif cmd == "p":
            _generate_preview(console, article_dir, removed_files, descriptions, removed_dir)
        elif cmd.startswith("r "):
            _restore_one(console, cmd, removed_dir, assets_dir, removed_files)
        elif cmd:
            print_invalid_option(console, cmd)
            Prompt.ask(f"[{MUTED}]Press any key to continue[/{MUTED}]", default="")


def _restore_one(console: Console, cmd: str, removed_dir: Path, assets_dir: Path, removed_files: list[str]) -> None:
    try:
        idx = int(cmd.split()[1]) - 1
        if not (0 <= idx < len(removed_files)):
            raise ValueError
    except (ValueError, IndexError):
        console.print(f"[{ERROR}]Invalid index[/{ERROR}]")
        Prompt.ask(f"[{MUTED}]Press any key to continue[/{MUTED}]", default="")
        return

    filename = Path(removed_files[idx]).name
    src = removed_dir / filename
    if not src.exists():
        for f in removed_dir.iterdir():
            if f.stem.startswith(Path(filename).stem):
                src = f; break

    if src.exists():
        assets_dir.mkdir(parents=True, exist_ok=True)
        try:
            src.rename(assets_dir / filename)
            console.print(f"[{SUCCESS}]Restored: {filename}[/{SUCCESS}]")
            removed_files.pop(idx)
        except OSError as exc:
            console.print(f"[{ERROR}]Failed: {exc}[/{ERROR}]")
    else:
        console.print(f"[{ERROR}]File not found: {filename}[/{ERROR}]")
    Prompt.ask(f"[{MUTED}]Press any key to continue[/{MUTED}]", default="")


def _restore_all(console: Console, removed_dir: Path, assets_dir: Path, removed_files: list[str]) -> None:
    if not removed_dir.exists():
        console.print(f"[{WARNING}]No removed/ directory found.[/{WARNING}]")
        Prompt.ask(f"[{MUTED}]Press any key to continue[/{MUTED}]", default="")
        return
    assets_dir.mkdir(parents=True, exist_ok=True)
    restored = 0
    for src in list(removed_dir.iterdir()):
        if src.is_file():
            try:
                src.rename(assets_dir / src.name)
                restored += 1
            except OSError as exc:
                console.print(f"[{ERROR}]Failed to restore {src.name}: {exc}[/{ERROR}]")
    if restored:
        console.print(f"[{SUCCESS}]Restored {restored} images[/{SUCCESS}]")
        removed_files.clear()
    else:
        console.print(f"[{WARNING}]No images to restore.[/{WARNING}]")
    Prompt.ask(f"[{MUTED}]Press any key to continue[/{MUTED}]", default="")


def _generate_preview(
    console: Console,
    article_dir: Path,
    removed_files: list[str],
    descriptions: dict[str, str],
    removed_dir: Path,
) -> None:
    import html as _html
    import platform
    import subprocess

    if not removed_files:
        console.print(f"[{WARNING}]No removed images to preview.[/{WARNING}]")
        return

    image_cards: list[str] = []
    for i, removed_path in enumerate(removed_files, 1):
        filename = Path(removed_path).name
        desc = descriptions.get(removed_path, descriptions.get(f"assets/{filename}", "No description"))
        removed_file = removed_dir / filename
        if not removed_file.exists():
            for f in removed_dir.iterdir():
                if f.stem.startswith(Path(filename).stem):
                    removed_file = f; filename = f.name; break
        if not removed_file.exists():
            continue
        img_src = f"removed/{filename}"
        image_cards.append(
            f'<div class="card"><div class="img"><a href="{_html.escape(img_src)}">'
            f'<img src="{_html.escape(img_src)}" alt="{_html.escape(filename)}" loading="lazy">'
            f'</a></div><div class="info"><span class="num">#{i}</span> '
            f'<span class="name">{_html.escape(filename)}</span>'
            f'<p class="desc">{_html.escape(desc)}</p></div></div>'
        )

    html = f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Removed Images — {_html.escape(article_dir.name)}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f5f5f5;padding:20px}}
.container{{max-width:1200px;margin:0 auto}}
.header{{background:white;padding:20px;border-radius:8px;margin-bottom:20px;box-shadow:0 2px 4px rgba(0,0,0,.1)}}
.header h1{{font-size:24px;color:#333}}
.gallery{{display:grid;grid-template-columns:repeat(auto-fill,minmax(350px,1fr));gap:20px}}
.card{{background:white;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.1)}}
.img{{padding:16px;background:#fafafa;border-bottom:1px solid #eee}}
.img img{{max-width:100%;max-height:300px;object-fit:contain}}
.info{{padding:16px}}
.num{{background:#ff5722;color:white;width:28px;height:28px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;font-size:12px;font-weight:bold;margin-right:8px}}
.name{{font-weight:600;color:#333;font-size:14px}}
.desc{{color:#555;font-size:13px;margin-top:8px;padding:12px;background:#f8f9fa;border-radius:6px;border-left:3px solid #2196f3}}
.footer{{margin-top:20px;text-align:center;color:#999;font-size:12px}}
</style></head><body><div class="container">
<div class="header"><h1>Removed Images — {_html.escape(article_dir.name)}</h1>
<p style="color:#666;margin-top:8px">{len(removed_files)} images removed by AI filtering</p></div>
<div class="gallery">{chr(10).join(image_cards)}</div>
<div class="footer"><p>Generated by Noosphere TUI</p></div>
</div></body></html>"""

    html_path = article_dir / "removed-preview.html"
    html_path.write_text(html, encoding="utf-8")
    try:
        s = platform.system()
        if s == "Darwin": subprocess.run(["open", str(html_path)])
        elif s == "Windows": subprocess.run(["start", str(html_path)], shell=True)
        else: subprocess.run(["xdg-open", str(html_path)])
    except Exception:
        pass
    console.print(f"[{SUCCESS}]HTML preview: {html_path}[/{SUCCESS}]")
    Prompt.ask(f"[{MUTED}]Press any key to continue[/{MUTED}]", default="")
