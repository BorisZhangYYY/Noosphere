"""Prompt management screen — view and edit pipeline prompts.

Pipeline prompts are stored as Markdown files under prompts/ and referenced
from config.json. Selecting a prompt opens it directly in the user's $EDITOR
so viewing and editing happen in the same place.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from src.core.config.config import load_config, clear_config_cache
from src.core.paths import resolve_project_path
from src.core.review.prompt_metadata import parse_prompt_file
from src.tui.helpers.prompts import ask_cancelable, print_invalid_option
from src.tui.helpers.editor import open_in_editor
from src.tui.theme import ACCENT, MUTED, SUCCESS, WARNING, ERROR, PANEL_BORDER, PANEL_PADDING


@dataclass
class PromptEntry:
    """A displayable prompt entry."""

    name: str
    platform: str  # Empty string means global.
    source_type: str
    path: Path | None
    body: str


def show_prompts(console: Console) -> None:
    """Interactive prompt browser/editor."""
    entries = _collect_prompt_entries(console)
    if not entries:
        console.print(f"[{WARNING}]No prompts configured.[/{WARNING}]")
        Prompt.ask(f"[{MUTED}]Press any key to continue[/{MUTED}]", default="")
        return

    while True:
        console.clear()
        console.rule(f"[bold {ACCENT}]Prompts[/bold {ACCENT}]")
        console.print(_build_prompt_table(entries))
        console.print()

        choice = ask_cancelable(
            console,
            f"[{ACCENT}]Select # to view/edit[/{ACCENT}]",
        )
        if choice is None:
            return
        if not choice:
            print_invalid_option(console)
            Prompt.ask(f"[{MUTED}]Press any key to continue[/{MUTED}]", default="")
            continue

        try:
            idx = int(choice) - 1
            if not (0 <= idx < len(entries)):
                raise ValueError
        except ValueError:
            print_invalid_option(console, choice)
            Prompt.ask(f"[{MUTED}]Press any key to continue[/{MUTED}]", default="")
            continue

        _edit_prompt(console, entries[idx])


def _collect_prompt_entries(console: Console) -> list[PromptEntry]:
    """Build a list of editable prompt entries from the current config."""
    config = load_config()
    entries: list[PromptEntry] = []

    entries.append(_resolve_entry(
        name="Rewrite Article",
        platform="",
        key="rewrite_prompt",
        path_key="rewrite_prompt_path",
        default_path=Path("prompts/rewrite_article.md"),
        config=config,
    ))
    entries.append(_resolve_entry(
        name="Image Review",
        platform="",
        key="image_review_prompt",
        path_key="image_review_prompt_path",
        default_path=Path("prompts/image_review.md"),
        config=config,
    ))

    for platform_name in sorted(config.ai.platform_prompts.keys()):
        platform_config = config.ai.platform_prompts[platform_name]
        if "rewrite_prompt" in platform_config or "rewrite_prompt_path" in platform_config:
            entries.append(_resolve_entry(
                name=f"Rewrite ({platform_name})",
                platform=platform_name,
                key="rewrite_prompt",
                path_key="rewrite_prompt_path",
                default_path=Path("prompts/rewrite_article.md"),
                config=config,
            ))

    return [e for e in entries if e is not None]


def _resolve_entry(
    *,
    name: str,
    platform: str,
    key: str,
    path_key: str,
    default_path: Path,
    config: object,
) -> PromptEntry | None:
    """Resolve a single prompt entry, mirroring AIConfig.resolve_prompt precedence."""
    from src.core.config.schema import Config

    cfg: Config = config  # type: ignore[assignment]
    platform_overrides = cfg.ai.platform_prompts

    if platform and platform in platform_overrides:
        pc = platform_overrides[platform]
        inline = pc.get(key, "")
        if isinstance(inline, str) and inline.strip():
            return PromptEntry(name, platform, "inline", None, inline)
        path_str = pc.get(path_key, "")
        if isinstance(path_str, str) and path_str.strip():
            path = resolve_project_path(path_str)
            body = _read_prompt_body(path)
            if body is not None:
                return PromptEntry(name, platform, "file", path, body)
            return PromptEntry(name, platform, "file (missing)", path, "")

    global_inline = getattr(cfg.ai, key, None)
    if isinstance(global_inline, str) and global_inline.strip():
        return PromptEntry(name, platform, "inline", None, global_inline)

    global_path = getattr(cfg.ai, path_key, None)
    if isinstance(global_path, str) and global_path.strip():
        path = resolve_project_path(global_path)
        body = _read_prompt_body(path)
        if body is not None:
            return PromptEntry(name, platform, "file", path, body)
        return PromptEntry(name, platform, "file (missing)", path, "")

    path = resolve_project_path(str(default_path))
    body = _read_prompt_body(path)
    if body is not None:
        return PromptEntry(name, platform, "file (default)", path, body)
    return None


def _read_prompt_body(path: Path) -> str | None:
    """Read a prompt file body, skipping YAML frontmatter if present."""
    if not path.exists():
        return None
    try:
        parsed = parse_prompt_file(path)
        return parsed.body
    except Exception:
        try:
            return path.read_text(encoding="utf-8")
        except Exception:
            return None


def _build_prompt_table(entries: list[PromptEntry]) -> Table:
    """Render the prompt list as a table."""
    table = Table(border_style=PANEL_BORDER, header_style=f"bold {MUTED}")
    table.add_column("#", justify="right", style=MUTED, width=4)
    table.add_column("Name", style="bold")
    table.add_column("Platform", style=MUTED)
    table.add_column("Source", style=MUTED)
    table.add_column("Path", style=MUTED)

    for i, entry in enumerate(entries, 1):
        platform_label = entry.platform or "global"
        path_str = str(entry.path) if entry.path else "—"
        table.add_row(str(i), entry.name, platform_label, entry.source_type, path_str)
    return table


def _edit_prompt(console: Console, entry: PromptEntry) -> None:
    """Open a prompt in $EDITOR. For inline prompts, show instructions."""
    if entry.source_type.startswith("file") and entry.path is not None and entry.path.exists():
        changed = open_in_editor(entry.path)
        if changed:
            clear_config_cache()
            console.print(f"[{SUCCESS}]Saved. Config cache cleared for next run.[/{SUCCESS}]")
        else:
            console.print(f"[{MUTED}]No changes detected.[/{MUTED}]")
    elif entry.source_type.startswith("file") and entry.path is not None:
        console.print(f"[{ERROR}]File not found: {entry.path}[/{ERROR}]")
    else:
        console.print(Panel(
            f"[{WARNING}]This prompt is inline in config.json.[/{WARNING}]\n"
            f"[{MUTED}]Edit the corresponding ai.platform_prompts or ai.{entry.name.lower().replace(' ', '_')} key in config.json directly.[/{MUTED}]",
            border_style=WARNING,
            padding=PANEL_PADDING,
        ))

    Prompt.ask(f"[{MUTED}]Press any key to continue[/{MUTED}]", default="")
