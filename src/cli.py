"""
CLI command definitions and entry points. Currently supported:
- extract: Extract an article from a website (single URL or batch file).
- upload: Upload a Markdown file to Siyuan.
- ai-review: AI-assisted content review and deterministic Markdown assembly.
- run: Pipeline of extract -> ai-review -> upload.
- articles/taxonomy/images: Manage the shared knowledge workspace.
- perspectives/config/jobs: Manage review contracts, runtime settings, and jobs.
- email: Send Markdown-styled emails via SMTP.
- mcp: Start an MCP server for AI clients.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn
from rich.table import Table

from src.core.config.config import load_config
from src.core.paths.output_paths import find_existing_article_dir
from src.core.paths.paths import get_paths
from src.graph.graph import run_extract_graph, run_ai_review_graph, run_upload_graph, run_pipeline_graph


console = Console()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract articles, optionally AI-review them, and upload Markdown to SiYuan."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract_parser = subparsers.add_parser("extract", help="Extract one or more article URLs into outputs/ARTICLE_ID/.")
    extract_parser.add_argument("url", nargs="?", help="Article URL to extract.")
    extract_parser.add_argument(
        "--batch",
        "-b",
        type=Path,
        metavar="FILE",
        help="File containing one URL per line (lines starting with # are ignored).",
    )
    extract_parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Re-extract URLs that have already been extracted.",
    )
    extract_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")

    upload_parser = subparsers.add_parser("upload", help="Upload one Markdown file, article directory, or article ID to SiYuan or local archive.")
    upload_parser.add_argument("file", type=Path, help="Markdown file, article directory, or article ID to upload.")
    upload_parser.add_argument("--force", "-f", action="store_true", help="Re-upload even if the article was already uploaded.")
    upload_parser.add_argument("--target", "-t", choices=["local", "siyuan"], default=None, help="Upload target platform (default: auto-select from config).")
    upload_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")

    ai_review_parser = subparsers.add_parser("ai-review", help="Use the configured AI model to rewrite and check one reviewed Markdown file, article directory, or article ID.")
    ai_review_parser.add_argument("file", type=Path, help="Reviewed Markdown file, article directory, or article ID.")
    ai_review_parser.add_argument("--force", "-f", action="store_true", help="Re-run AI review even if review.json is already marked completed.")
    ai_review_parser.add_argument("--perspective", help="Review perspective ID from the pipeline configuration.")
    ai_review_parser.add_argument("--language", choices=["zh-CN", "en-US", "source"], help="Reviewed article output language.")
    ai_review_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")

    run_parser = subparsers.add_parser("run", help="Extract one URL, AI-review it, then upload it to SiYuan.")
    run_parser.add_argument("url", help="Article URL to extract.")
    run_parser.add_argument("--perspective", help="Review perspective ID from the pipeline configuration.")
    run_parser.add_argument("--language", choices=["zh-CN", "en-US", "source"], help="Reviewed article output language.")
    run_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")

    email_parser = subparsers.add_parser("email", help="Send reviewed article as HTML email via SMTP.")
    email_parser.add_argument("article_id", help="Article ID to send as email.")
    email_parser.add_argument("--to", required=True, help="Recipient email address (must be in allowed_recipients).")

    # --- Image Review / Recovery command ---
    review_images_parser = subparsers.add_parser(
        "review-images", 
        help="Review and optionally recover images removed by AI filtering."
    )
    review_images_parser.add_argument(
        "article_dir", 
        type=Path, 
        help="Path to article output directory (e.g., outputs/article_id/)."
    )
    review_images_parser.add_argument(
        "--restore", 
        nargs="+", 
        metavar="IMAGE",
        help="Restore specific removed images by name (e.g., image_02.webp)."
    )
    review_images_parser.add_argument(
        "--restore-all", 
        action="store_true",
        help="Restore all removed images back to the article."
    )
    review_images_parser.add_argument(
        "--list", 
        action="store_true",
        help="List removed images with descriptions."
    )
    review_images_parser.add_argument(
        "--preview",
        action="store_true",
        help="Generate an HTML preview page for removed images."
    )

    tui_parser = subparsers.add_parser("tui", help="Launch the interactive terminal UI.")

    mcp_parser = subparsers.add_parser("mcp", help="Start the MCP server for AI clients.")
    mcp_parser.add_argument("--host", default="127.0.0.1", help="Host to bind the MCP HTTP server (default: 127.0.0.1).")
    mcp_parser.add_argument("--port", type=int, default=8080, help="Port to bind the MCP HTTP server (default: 8080).")

    articles_parser = subparsers.add_parser("articles", help="Inspect and edit article workspaces.")
    articles_subparsers = articles_parser.add_subparsers(dest="articles_command", required=True)
    articles_list = articles_subparsers.add_parser("list", help="List articles with search and taxonomy filters.")
    articles_list.add_argument("--query", default="")
    articles_list.add_argument("--status", choices=["captured", "reviewed", "uploaded", "failed"], default="")
    articles_list.add_argument("--tag-id", default="")
    articles_list.add_argument("--locale", choices=["zh-CN", "en-US"], default="en-US")
    articles_list.add_argument("--json", action="store_true")
    articles_show = articles_subparsers.add_parser("show", help="Show article metadata, classification, and content.")
    articles_show.add_argument("article_id")
    articles_show.add_argument("--locale", choices=["zh-CN", "en-US"], default="en-US")
    articles_show.add_argument("--no-content", action="store_true")
    articles_show.add_argument("--json", action="store_true")
    articles_update = articles_subparsers.add_parser("update", help="Replace reviewed.md from a UTF-8 Markdown file.")
    articles_update.add_argument("article_id")
    articles_update.add_argument("--from", dest="source_file", type=Path, required=True)
    articles_update.add_argument("--json", action="store_true")
    articles_metadata = articles_subparsers.add_parser("metadata", help="Fill source metadata fields that were missing at capture time.")
    articles_metadata.add_argument("article_id")
    articles_metadata.add_argument("--author")
    articles_metadata.add_argument("--published-at")
    articles_metadata.add_argument("--json", action="store_true")

    taxonomy_parser = subparsers.add_parser("taxonomy", help="Inspect taxonomy and move articles by stable IDs.")
    taxonomy_subparsers = taxonomy_parser.add_subparsers(dest="taxonomy_command", required=True)
    taxonomy_list = taxonomy_subparsers.add_parser("list", help="List the canonical two-level taxonomy.")
    taxonomy_list.add_argument("--locale", choices=["zh-CN", "en-US"], default="en-US")
    taxonomy_list.add_argument("--include-retired", action="store_true")
    taxonomy_list.add_argument("--json", action="store_true")
    taxonomy_create = taxonomy_subparsers.add_parser("create", help="Create a top-level category or one child category.")
    taxonomy_create.add_argument("--name", required=True)
    taxonomy_create.add_argument("--description", default="")
    taxonomy_create.add_argument("--parent-id", default="")
    taxonomy_create.add_argument("--locale", choices=["zh-CN", "en-US"], default="en-US")
    taxonomy_create.add_argument("--json", action="store_true")
    taxonomy_update = taxonomy_subparsers.add_parser("update", help="Rename, describe, retire, or restore a category.")
    taxonomy_update.add_argument("tag_id")
    taxonomy_update.add_argument("--name")
    taxonomy_update.add_argument("--description")
    retirement = taxonomy_update.add_mutually_exclusive_group()
    retirement.add_argument("--retire", action="store_true")
    retirement.add_argument("--restore", action="store_true")
    taxonomy_update.add_argument("--locale", choices=["zh-CN", "en-US"], default="en-US")
    taxonomy_update.add_argument("--json", action="store_true")
    taxonomy_assign = taxonomy_subparsers.add_parser("assign", aliases=["move"], help="Assign an article to a tag path.")
    taxonomy_assign.add_argument("article_id")
    taxonomy_assign.add_argument("--tag-id")
    taxonomy_assign.add_argument("--subtag-id")
    taxonomy_assign.add_argument("--tag-name", default="")
    taxonomy_assign.add_argument("--subtag-name", default="")
    taxonomy_assign.add_argument("--tag-description", default="")
    taxonomy_assign.add_argument("--subtag-description", default="")
    taxonomy_assign.add_argument("--tag-localizations", default="", help="JSON object containing zh-CN/en-US names, descriptions, and aliases.")
    taxonomy_assign.add_argument("--subtag-localizations", default="", help="JSON object containing zh-CN/en-US names, descriptions, and aliases.")
    taxonomy_assign.add_argument("--locale", choices=["zh-CN", "en-US"], default="en-US")
    taxonomy_assign.add_argument("--json", action="store_true")

    images_parser = subparsers.add_parser("images", help="Inspect, remove, and restore article images.")
    images_subparsers = images_parser.add_subparsers(dest="images_command", required=True)
    images_list = images_subparsers.add_parser("list", help="List active and removed images.")
    images_list.add_argument("article_id")
    images_list.add_argument("--json", action="store_true")
    images_set = images_subparsers.add_parser("set", help="Set an image state and update reviewed.md.")
    images_set.add_argument("article_id")
    images_set.add_argument("asset_name")
    images_set.add_argument("--state", choices=["active", "removed"], required=True)
    images_set.add_argument("--json", action="store_true")

    perspectives_parser = subparsers.add_parser("perspectives", help="Manage review perspectives and templates.")
    perspectives_subparsers = perspectives_parser.add_subparsers(dest="perspectives_command", required=True)
    perspectives_list = perspectives_subparsers.add_parser("list", help="List built-in and custom perspectives.")
    perspectives_list.add_argument("--locale", choices=["zh-CN", "en-US"], default="en-US")
    perspectives_list.add_argument("--json", action="store_true")
    perspectives_show = perspectives_subparsers.add_parser("show", help="Show one perspective, prompt, and template.")
    perspectives_show.add_argument("perspective_id")
    perspectives_show.add_argument("--locale", choices=["zh-CN", "en-US"], default="en-US")
    perspectives_show.add_argument("--json", action="store_true")
    perspectives_save = perspectives_subparsers.add_parser("save", help="Create or update a custom perspective.")
    perspectives_save.add_argument("perspective_id")
    perspectives_save.add_argument("--label", required=True)
    perspectives_save.add_argument("--description", default="")
    perspectives_save.add_argument("--prompt-file", type=Path, required=True)
    perspectives_save.add_argument("--template-file", type=Path, required=True)
    perspectives_save.add_argument("--sections", required=True, help='JSON object, for example {"summary":"Summary","main":"Article"}.')
    perspectives_save.add_argument("--body-section", required=True)
    perspectives_save.add_argument("--activate", action="store_true")
    perspectives_save.add_argument("--locale", choices=["zh-CN", "en-US"], default="en-US")
    perspectives_save.add_argument("--json", action="store_true")
    perspectives_delete = perspectives_subparsers.add_parser("delete", help="Delete a custom perspective.")
    perspectives_delete.add_argument("perspective_id")
    perspectives_delete.add_argument("--locale", choices=["zh-CN", "en-US"], default="en-US")
    perspectives_delete.add_argument("--json", action="store_true")
    perspectives_use = perspectives_subparsers.add_parser("use", help="Set the active review perspective.")
    perspectives_use.add_argument("perspective_id")
    perspectives_use.add_argument("--locale", choices=["zh-CN", "en-US"], default="en-US")
    perspectives_use.add_argument("--json", action="store_true")

    config_parser = subparsers.add_parser("config", help="Manage masked runtime settings and service connectivity.")
    config_subparsers = config_parser.add_subparsers(dest="config_command", required=True)
    config_show = config_subparsers.add_parser("show", help="Show masked provider, crawler, and archive settings.")
    config_show.add_argument("--json", action="store_true")
    config_apply = config_subparsers.add_parser("apply", help="Apply a web-compatible settings JSON object.")
    config_apply.add_argument("file", type=Path)
    config_apply.add_argument("--json", action="store_true")
    config_activate = config_subparsers.add_parser("activate", help="Activate an existing AI provider.")
    config_activate.add_argument("provider_name")
    config_activate.add_argument("--json", action="store_true")
    config_test = config_subparsers.add_parser("test", help="Test AI or Firecrawl connectivity.")
    config_test.add_argument("service", choices=["ai", "firecrawl"])
    config_test.add_argument("--provider", default="")
    config_test.add_argument("--json", action="store_true")
    config_reveal = config_subparsers.add_parser("reveal", help="Reveal one secret explicitly on the local terminal.")
    config_reveal.add_argument("service", choices=["ai", "firecrawl", "siyuan"])
    config_reveal.add_argument("--provider", default="")
    config_reveal.add_argument("--yes", action="store_true", help="Required acknowledgement for printing a secret.")

    jobs_parser = subparsers.add_parser("jobs", help="Inspect background jobs from a running Noosphere server.")
    jobs_subparsers = jobs_parser.add_subparsers(dest="jobs_command", required=True)
    jobs_list = jobs_subparsers.add_parser("list", help="List server-side capture, review, and upload jobs.")
    jobs_list.add_argument("--kind", choices=["all", "capture", "review", "upload"], default="all")
    jobs_list.add_argument("--server", default="http://127.0.0.1:8080")
    jobs_list.add_argument("--json", action="store_true")
    jobs_show = jobs_subparsers.add_parser("show", help="Show one server-side job.")
    jobs_show.add_argument("job_id")
    jobs_show.add_argument("--server", default="http://127.0.0.1:8080")
    jobs_show.add_argument("--json", action="store_true")

    return parser.parse_args(argv)


async def _run_extract(url: str) -> Path:
    return await run_extract_graph(url, get_paths().output_dir)


async def _run_extract_batch(
    urls: list[str],
    *,
    force: bool = False,
    quiet: bool = False,
) -> list[tuple[str, Path | None, str | None]]:
    """Extract multiple URLs with progress reporting and optional deduplication.

    Returns a list of (url, output_path_or_existing_dir, error_message).
    ``error_message`` is ``None`` on success; for skipped duplicates it is
    ``"skipped"``.
    """
    output_dir = get_paths().output_dir
    results: list[tuple[str, Path | None, str | None]] = []

    progress_columns = [
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
    ]

    with Progress(*progress_columns, console=console, transient=True, disable=quiet) as progress:
        task = progress.add_task("Extracting articles...", total=len(urls))
        for url in urls:
            try:
                if not force:
                    existing = find_existing_article_dir(output_dir, url)
                    if existing is not None:
                        if not quiet:
                            progress.console.print(f"[yellow]Skip[/yellow] {url} (already extracted at {existing})")
                        results.append((url, existing, "skipped"))
                        progress.advance(task)
                        continue

                if quiet:
                    path = await _run_extract(url)
                else:
                    with console.status(f"[cyan]Extracting[/cyan] {url}..."):
                        path = await _run_extract(url)
                    progress.console.print(f"[green]Done[/green]   {url} -> {path}")
                results.append((url, path, None))
            except Exception as exc:
                if not quiet:
                    progress.console.print(f"[red]Fail[/red]   {url}: {exc}")
                results.append((url, None, str(exc)))
            progress.advance(task)

    return results


async def _run_ai_review(path: Path, *, perspective: str | None = None, language: str | None = None):
    from src.core.review.review_validation import ValidationResult
    validation = await run_ai_review_graph(path, perspective=perspective, output_language=language)
    if not isinstance(validation, ValidationResult):
        raise RuntimeError("AI review did not return a validation result")
    return validation


async def _run_upload(path: Path, target: str | None = None) -> tuple[str, str]:
    """Upload a reviewed Markdown file and return (hpath, platform_name)."""
    upload_result = await run_upload_graph(path, target=target)
    # The upload graph records platform in manifest; report it from the manifest.
    manifest_path = path.with_name("manifest.json")
    platform = "unknown"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            platform = manifest.get("uploaded", {}).get("platform", "unknown")
        except (OSError, json.JSONDecodeError):
            pass
    return upload_result.hpath, platform


async def _run_pipeline(url: str, *, perspective: str | None = None, language: str | None = None) -> str:
    upload_result = await run_pipeline_graph(
        url,
        get_paths().output_dir,
        auto_confirm=True,
        perspective=perspective,
        output_language=language,
    )
    return upload_result.hpath


def _resolve_reviewed_path(value: Path) -> Path:
    """Resolve a user-supplied file, directory, or article ID to reviewed.md."""
    from src.core.paths.paths import get_paths

    # Direct file path
    if value.exists() and value.is_file():
        return value

    # Directory containing reviewed.md
    if value.exists() and value.is_dir():
        candidate = value / "reviewed.md"
        if candidate.exists():
            return candidate
        raise ValueError(f"Directory does not contain reviewed.md: {value}")

    # Treat as article ID
    article_id = str(value)
    candidate = get_paths().article_reviewed_path(article_id)
    if candidate.exists():
        return candidate
    raise ValueError(f"Article not found: {article_id}")


def _is_review_complete(reviewed_path: Path) -> bool:
    """Return True if review.json exists and status is 'reviewed'."""
    import json

    report_path = reviewed_path.with_name("review.json")
    if not report_path.exists():
        return False
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        return report.get("status") == "reviewed"
    except (OSError, json.JSONDecodeError):
        return False


def _record_upload(reviewed_path: Path, platform: str, hpath: str) -> None:
    """Record upload result in manifest.json."""
    import json
    from datetime import datetime

    manifest_path = reviewed_path.with_name("manifest.json")
    if not manifest_path.exists():
        return
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["uploaded"] = {
            "platform": platform,
            "hpath": hpath,
            "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except (OSError, json.JSONDecodeError):
        pass


def _is_uploaded(reviewed_path: Path) -> bool:
    """Return True if manifest.json has a non-empty uploaded record."""
    import json

    manifest_path = reviewed_path.with_name("manifest.json")
    if not manifest_path.exists():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        return bool(manifest.get("uploaded", {}).get("hpath"))
    except (OSError, json.JSONDecodeError):
        return False


def _emit_payload(payload: Any, *, as_json: bool = False) -> None:
    """Print structured command output for humans or automation."""
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        return
    console.print_json(data=payload)


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"Cannot read JSON file: {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON file: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"JSON file must contain an object: {path}")
    return payload


def _server_json(server: str, path: str) -> dict[str, Any]:
    import urllib.error
    import urllib.request

    url = server.rstrip("/") + path
    try:
        with urllib.request.urlopen(url, timeout=20) as response:  # noqa: S310 - user selects the local service URL.
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot query Noosphere server at {url}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Unexpected response from Noosphere server: {url}")
    return payload


async def _main_async(args: argparse.Namespace) -> int:
    if args.command == "articles":
        from src.application.service import get_article, list_articles, save_reviewed_markdown, update_article_metadata

        try:
            if args.articles_command == "list":
                payload = {
                    "articles": list_articles(
                        locale=args.locale,
                        query=args.query,
                        status=args.status,
                        tag_id=args.tag_id,
                    )
                }
            elif args.articles_command == "show":
                payload = {"article": get_article(args.article_id, locale=args.locale, include_content=not args.no_content)}
            elif args.articles_command == "update":
                markdown = args.source_file.read_text(encoding="utf-8")
                payload = save_reviewed_markdown(args.article_id, markdown)
            else:
                updates = {
                    key: value
                    for key, value in {"author": args.author, "publishedAt": args.published_at}.items()
                    if value is not None
                }
                payload = update_article_metadata(args.article_id, updates)
            _emit_payload(payload, as_json=args.json)
            return 0
        except (OSError, ValueError) as exc:
            console.print(f"[red]Error: {exc}[/red]")
            return 1

    if args.command == "taxonomy":
        from src.application.service import (
            classify_article,
            create_taxonomy_category,
            list_taxonomy,
            update_taxonomy_category,
        )

        try:
            if args.taxonomy_command == "list":
                payload = {
                    "tags": list_taxonomy(
                        locale=args.locale,
                        include_retired=args.include_retired,
                    )
                }
            elif args.taxonomy_command == "create":
                payload = {
                    "category": create_taxonomy_category(
                        name=args.name,
                        description=args.description,
                        parent_id=args.parent_id or None,
                        locale=args.locale,
                    )
                }
            elif args.taxonomy_command == "update":
                if args.name is None and args.description is None and not args.retire and not args.restore:
                    raise ValueError("Provide a name, description, --retire, or --restore")
                payload = {
                    "category": update_taxonomy_category(
                        args.tag_id,
                        name=args.name,
                        description=args.description,
                        retired=True if args.retire else False if args.restore else None,
                        locale=args.locale,
                    )
                }
            else:
                if not args.tag_id:
                    raise ValueError("Provide --tag-id for a configured category")
                payload = {
                    "classification": classify_article(
                        args.article_id,
                        tag_id=args.tag_id,
                        subtag_id=args.subtag_id,
                        tag_name=args.tag_name,
                        subtag_name=args.subtag_name,
                        tag_description=args.tag_description,
                        subtag_description=args.subtag_description,
                        tag_localizations=json.loads(args.tag_localizations) if args.tag_localizations else None,
                        subtag_localizations=json.loads(args.subtag_localizations) if args.subtag_localizations else None,
                        locale=args.locale,
                    )
                }
            _emit_payload(payload, as_json=args.json)
            return 0
        except (ValueError, json.JSONDecodeError) as exc:
            console.print(f"[red]Error: {exc}[/red]")
            return 1

    if args.command == "images":
        from src.application.service import get_article, set_article_image_state

        try:
            if args.images_command == "list":
                article = get_article(args.article_id, include_content=False)
                payload = {"article_id": args.article_id, "active": article["assets"], "removed": article["removedAssets"]}
            else:
                payload = set_article_image_state(args.article_id, args.asset_name, args.state)
            _emit_payload(payload, as_json=args.json)
            return 0
        except (OSError, ValueError) as exc:
            console.print(f"[red]Error: {exc}[/red]")
            return 1

    if args.command == "perspectives":
        from src.application.service import (
            delete_review_perspective,
            get_pipeline_settings,
            save_pipeline_settings,
            upsert_review_perspective,
        )

        try:
            settings = get_pipeline_settings(locale=args.locale)
            if args.perspectives_command == "list":
                payload = {
                    "activePerspective": settings["activePerspective"],
                    "perspectives": settings["perspectives"],
                }
            elif args.perspectives_command == "show":
                perspective = next((item for item in settings["perspectives"] if item["id"] == args.perspective_id), None)
                if perspective is None:
                    raise ValueError(f"Review perspective not found: {args.perspective_id}")
                payload = {"perspective": perspective, "active": settings["activePerspective"] == args.perspective_id}
            elif args.perspectives_command == "save":
                sections = json.loads(args.sections)
                if not isinstance(sections, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in sections.items()):
                    raise ValueError("--sections must be a JSON object of string field names and headings")
                payload = upsert_review_perspective(
                    args.perspective_id,
                    label=args.label,
                    description=args.description,
                    prompt=args.prompt_file.read_text(encoding="utf-8"),
                    template=args.template_file.read_text(encoding="utf-8"),
                    output_sections=sections,
                    body_section=args.body_section,
                    locale=args.locale,
                    activate=args.activate,
                )
            elif args.perspectives_command == "delete":
                payload = delete_review_perspective(args.perspective_id, locale=args.locale)
            else:
                if not any(item["id"] == args.perspective_id for item in settings["perspectives"]):
                    raise ValueError(f"Review perspective not found: {args.perspective_id}")
                settings["activePerspective"] = args.perspective_id
                payload = save_pipeline_settings(settings, locale=args.locale)
            _emit_payload(payload, as_json=args.json)
            return 0
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            console.print(f"[red]Error: {exc}[/red]")
            return 1

    if args.command == "config":
        from src.application.service import get_secret, get_settings, save_settings, test_service

        try:
            if args.config_command == "show":
                payload = {"settings": get_settings()}
            elif args.config_command == "apply":
                payload = {"settings": save_settings(_read_json_object(args.file))}
            elif args.config_command == "activate":
                payload = {"settings": save_settings(get_settings(), active_provider=args.provider_name)}
            elif args.config_command == "test":
                payload = await test_service(args.service, provider_name=args.provider)
            else:
                if not args.yes:
                    raise ValueError("Secret reveal requires --yes because it prints sensitive data to the terminal")
                payload = {"service": args.service, "provider": args.provider or None, "secret": get_secret(args.service, provider_name=args.provider)}
            _emit_payload(payload, as_json=getattr(args, "json", False))
            return 0
        except ValueError as exc:
            console.print(f"[red]Error: {exc}[/red]")
            return 1

    if args.command == "jobs":
        try:
            if args.jobs_command == "list":
                payload = _server_json(args.server, f"/api/v1/jobs?kind={args.kind}")
            else:
                payload = _server_json(args.server, f"/api/v1/jobs/{args.job_id}")
            _emit_payload(payload, as_json=args.json)
            return 0
        except ValueError as exc:
            console.print(f"[red]Error: {exc}[/red]")
            return 1

    if args.command == "extract":
        urls: list[str] = []
        if args.url:
            urls.append(args.url)
        if args.batch:
            if not args.batch.exists():
                console.print(f"[red]Error: Batch file not found: {args.batch}[/red]")
                return 1
            text = args.batch.read_text(encoding="utf-8")
            urls.extend(
                line.strip()
                for line in text.splitlines()
                if line.strip() and not line.strip().startswith("#")
            )

        if not urls:
            console.print("[red]Error: provide a URL or --batch FILE[/red]")
            return 1

        if len(urls) == 1 and not args.batch:
            try:
                path = await _run_extract(urls[0])
            except Exception as exc:
                if args.json:
                    _emit_payload({"ok": False, "operation": "extract", "url": urls[0], "error": str(exc)}, as_json=True)
                else:
                    console.print(f"[red]Extraction failed: {exc}[/red]")
                return 1
            payload = {
                "ok": True,
                "operation": "extract",
                "url": urls[0],
                "article_id": path.parent.name,
                "reviewed_path": str(path),
                "status": "captured",
            }
            if args.json:
                _emit_payload(payload, as_json=True)
            else:
                console.print(f"Reviewed draft: {path}")
                console.print(f"Next: edit manually and upload, or run: python -m src.cli ai-review {path}")
            return 0

        results = await _run_extract_batch(urls, force=args.force, quiet=args.json)
        done = sum(1 for _, _, err in results if err is None)
        skipped = sum(1 for _, _, err in results if err == "skipped")
        failed = len(results) - done - skipped

        if args.json:
            _emit_payload(
                {
                    "ok": failed == 0,
                    "operation": "extract_batch",
                    "summary": {"successful": done, "skipped": skipped, "failed": failed},
                    "results": [
                        {
                            "url": url,
                            "article_id": path.name if path and path.is_dir() else path.parent.name if path else None,
                            "path": str(path) if path else None,
                            "status": "skipped" if error == "skipped" else "failed" if error else "captured",
                            "error": None if error in {None, "skipped"} else error,
                        }
                        for url, path, error in results
                    ],
                },
                as_json=True,
            )
            return 0 if failed == 0 else 1

        table = Table(title="Extraction Summary")
        table.add_column("Status", style="cyan")
        table.add_column("Count", justify="right")
        table.add_row("Successful", str(done), style="green")
        table.add_row("Skipped (already extracted)", str(skipped), style="yellow")
        table.add_row("Failed", str(failed), style="red")
        console.print(table)
        return 0 if failed == 0 else 1

    if args.command == "upload":
        try:
            reviewed_path = _resolve_reviewed_path(args.file)
        except ValueError as exc:
            console.print(f"[red]Error: {exc}[/red]")
            return 1

        if not args.force and _is_uploaded(reviewed_path):
            manifest_path = reviewed_path.with_name("manifest.json")
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                hpath = manifest.get("uploaded", {}).get("hpath", "unknown")
            except (OSError, json.JSONDecodeError):
                hpath = "unknown"
            if args.json:
                _emit_payload({"ok": True, "operation": "upload", "status": "skipped", "hpath": hpath}, as_json=True)
            else:
                console.print(f"[yellow]Skip[/yellow] already uploaded: {hpath}")
            return 0

        try:
            hpath, platform = await _run_upload(reviewed_path, target=args.target)
        except Exception as exc:
            if args.json:
                _emit_payload({"ok": False, "operation": "upload", "error": str(exc)}, as_json=True)
            else:
                console.print(f"[red]Upload failed: {exc}[/red]")
            return 1
        _record_upload(reviewed_path, platform, hpath)
        if args.json:
            _emit_payload(
                {
                    "ok": True,
                    "operation": "upload",
                    "article_id": reviewed_path.parent.name,
                    "status": "uploaded",
                    "target": platform,
                    "hpath": hpath,
                },
                as_json=True,
            )
        else:
            console.print(f"[green]Uploaded:[/green] {hpath}")
        return 0

    if args.command == "ai-review":
        from src.core.review.review_validation import format_validation_issues
        try:
            reviewed_path = _resolve_reviewed_path(args.file)
        except ValueError as exc:
            console.print(f"[red]Error: {exc}[/red]")
            return 1

        if not args.force and _is_review_complete(reviewed_path):
            if args.json:
                _emit_payload(
                    {"ok": True, "operation": "review", "article_id": reviewed_path.parent.name, "status": "skipped"},
                    as_json=True,
                )
            else:
                console.print(f"[yellow]Skip[/yellow] AI review already completed for {reviewed_path}")
            return 0

        result = await _run_ai_review(reviewed_path, perspective=args.perspective, language=args.language)
        if result.ok:
            if args.json:
                _emit_payload(
                    {
                        "ok": True,
                        "operation": "review",
                        "article_id": reviewed_path.parent.name,
                        "status": "reviewed",
                        "perspective": args.perspective or load_config().pipeline.active_perspective,
                        "language": args.language or load_config().pipeline.output_language,
                    },
                    as_json=True,
                )
            else:
                console.print(f"[green]AI reviewed:[/green] {reviewed_path}")
            return 0
        if args.json:
            _emit_payload(
                {"ok": False, "operation": "review", "status": "failed", "diagnostics": [issue.message for issue in result.issues]},
                as_json=True,
            )
        else:
            console.print("[red]AI review failed.[/red]")
            console.print(format_validation_issues(result.issues))
        return 1

    if args.command == "run":
        try:
            hpath = await _run_pipeline(args.url, perspective=args.perspective, language=args.language)
        except Exception as exc:
            if args.json:
                _emit_payload({"ok": False, "operation": "pipeline", "url": args.url, "error": str(exc)}, as_json=True)
            else:
                console.print(f"[red]Pipeline failed: {exc}[/red]")
            return 1
        if args.json:
            _emit_payload(
                {
                    "ok": True,
                    "operation": "pipeline",
                    "url": args.url,
                    "status": "uploaded",
                    "perspective": args.perspective or load_config().pipeline.active_perspective,
                    "language": args.language or load_config().pipeline.output_language,
                    "hpath": hpath,
                },
                as_json=True,
            )
        else:
            print(f"Uploaded: {hpath}")
        return 0

    if args.command == "email":
        from src.core.email_report import EmailReport, write_report
        from src.integrations.email_adapter import EmailAdapter
        from src.integrations.markdown_to_email import MarkdownToEmailRenderer

        # --- Load SMTP configuration ---
        config = load_config()
        smtp_config = config.smtp
        if not smtp_config:
            print("Error: SMTP not configured in config.json")
            return 1

        # --- Validate recipient against allowlist ---
        allowed = smtp_config.allowed_recipients
        if args.to not in allowed:
            print(f"Error: Recipient '{args.to}' is not in allowed_recipients list")
            return 1

        # --- Load reviewed article ---
        paths = get_paths()
        reviewed_md = paths.article_reviewed_path(args.article_id)
        if not reviewed_md.exists():
            print(f"Error: Article not found: {paths.article_dir(args.article_id)}")
            return 1
        markdown_text = reviewed_md.read_text(encoding="utf-8")

        # Derive email subject from the article title (first H1)
        title_match = re.search(r"^#\s+(.+)$", markdown_text, re.MULTILINE)
        article_title = title_match.group(1).strip() if title_match else args.article_id

        assets_dir = paths.article_assets_dir(args.article_id)

        # --- Render Markdown to HTML (images embedded as base64) ---
        renderer = MarkdownToEmailRenderer()
        html_body = renderer.render(markdown_text, assets_dir=assets_dir, subject_title=article_title)

        header_note = f'<p style="margin-bottom: 1em; color: #666; font-size: 0.9em;">[Shared by {smtp_config.sender_name} via Noosphere]</p>'
        html_body = header_note + html_body

        subject = f"[Shared by {smtp_config.sender_name} via Noosphere] {article_title}"

        # --- Send email ---
        adapter = EmailAdapter(
            host=smtp_config.host,
            port=smtp_config.port,
            user=smtp_config.user,
            password=smtp_config.password,
            sender_name=smtp_config.sender_name,
            allowed_recipients=allowed,
        )
        result = adapter.send(
            article_id=args.article_id,
            recipient=args.to,
            html_body=html_body,
            subject=subject,
        )

        # --- Persist send report for audit/debugging ---
        report = EmailReport(
            article_id=args.article_id,
            recipient=args.to,
            subject=subject,
            success=result.success,
            error=result.message if not result.success else None,
        )
        report_path = write_report(args.article_id, report, paths)
        print(f"Email report: {report_path}")

        if result.success:
            print(f"Email sent successfully to {args.to}")
            return 0
        print(f"Error: {result.message}")
        return 1

    if args.command == "review-images":
        return await _run_review_images(args)

    if args.command == "tui":
        from src.tui import launch_tui
        await launch_tui()
        return 0

    if args.command == "mcp":
        import logging
        import uvicorn
        from src.mcp.server import create_app

        logging.basicConfig(level=logging.INFO)
        app = create_app()
        console.print(f"[green]Starting MCP server on {args.host}:{args.port}[/green]")
        uvicorn_config = uvicorn.Config(app, host=args.host, port=args.port, log_level="info")
        uvicorn_server = uvicorn.Server(uvicorn_config)
        await uvicorn_server.serve()
        return 0

    print(f"Error: unsupported command: {args.command}")
    return 1


def _generate_removed_preview_html(
    article_dir: Path,
    removed_files: list[str],
    descriptions: dict[str, str],
    removed_dir: Path,
    assets_dir: Path,
) -> int:
    """Generate an HTML preview page for removed images."""
    if not removed_files:
        print("No images were removed by AI filtering.")
        return 0

    import html
    
    html_path = article_dir / "removed-preview.html"
    
    # Build image cards
    image_cards = []
    for i, removed_path in enumerate(removed_files, 1):
        filename = Path(removed_path).name
        desc = descriptions.get(removed_path, descriptions.get(f"assets/{filename}", "No description"))
        
        # Check if file actually exists in removed/
        removed_file = removed_dir / filename
        if not removed_file.exists():
            for f in removed_dir.iterdir():
                if f.stem.startswith(Path(filename).stem):
                    removed_file = f
                    filename = f.name
                    break
        
        if not removed_file.exists():
            continue
            
        # Use relative path for HTML
        img_src = f"removed/{filename}"
        
        # Escape values for safe HTML/JS insertion
        safe_filename = html.escape(filename, quote=True)
        safe_desc = html.escape(desc, quote=True)
        safe_img_src = html.escape(img_src, quote=True)
        
        card_html = f"""    <div class="image-card">
      <div class="image-preview">
        <a href="{safe_img_src}" target="_blank">
          <img src="{safe_img_src}" alt="{safe_filename}" loading="lazy">
        </a>
      </div>
      <div class="image-info">
        <div class="image-header">
          <span class="image-number">#{i}</span>
          <span class="image-name">{safe_filename}</span>
        </div>
        <div class="image-description">
          <strong>AI Description:</strong><br>
          {safe_desc}
        </div>
        <div class="image-actions">
          <button onclick="restoreImage({repr(filename)})" class="btn-restore">♻️ Restore</button>
          <a href="{safe_img_src}" target="_blank" class="btn-open">🔍 Open Full Size</a>
        </div>
      </div>
    </div>"""
        image_cards.append(card_html)

    if not image_cards:
        print("No removed image files found in removed/ directory.")
        return 0

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Removed Images Preview - {html.escape(article_dir.name)}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; padding: 20px; }}
    .container {{ max-width: 1200px; margin: 0 auto; }}
    .header {{ background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
    .header h1 {{ font-size: 24px; color: #333; margin-bottom: 8px; }}
    .header p {{ color: #666; font-size: 14px; }}
    .stats {{ display: flex; gap: 16px; margin-top: 12px; }}
    .stat {{ background: #e3f2fd; padding: 8px 16px; border-radius: 20px; font-size: 13px; color: #1976d2; }}
    .gallery {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap: 20px; }}
    .image-card {{ background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1); transition: transform 0.2s; }}
    .image-card:hover {{ transform: translateY(-2px); box-shadow: 0 4px 16px rgba(0,0,0,0.15); }}
    .image-preview {{ padding: 16px; background: #fafafa; border-bottom: 1px solid #eee; }}
    .image-preview img {{ max-width: 100%; max-height: 300px; object-fit: contain; border-radius: 4px; cursor: pointer; }}
    .image-info {{ padding: 16px; }}
    .image-header {{ display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }}
    .image-number {{ background: #ff5722; color: white; width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: bold; }}
    .image-name {{ font-weight: 600; color: #333; font-size: 14px; word-break: break-all; }}
    .image-description {{ color: #555; font-size: 13px; line-height: 1.5; margin-bottom: 16px; padding: 12px; background: #f8f9fa; border-radius: 6px; border-left: 3px solid #2196f3; }}
    .image-actions {{ display: flex; gap: 10px; }}
    .btn-restore, .btn-open {{ padding: 8px 16px; border: none; border-radius: 6px; font-size: 13px; cursor: pointer; text-decoration: none; display: inline-flex; align-items: center; gap: 6px; }}
    .btn-restore {{ background: #4caf50; color: white; }}
    .btn-restore:hover {{ background: #45a049; }}
    .btn-open {{ background: #e3f2fd; color: #1976d2; }}
    .btn-open:hover {{ background: #bbdefb; }}
    .footer {{ margin-top: 20px; text-align: center; color: #999; font-size: 12px; padding: 20px; }}
    .restore-all {{ margin-bottom: 20px; text-align: center; }}
    .btn-restore-all {{ background: #ff5722; color: white; padding: 12px 32px; border: none; border-radius: 8px; font-size: 16px; cursor: pointer; font-weight: 600; }}
    .btn-restore-all:hover {{ background: #e64a19; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>🗑️ Removed Images Preview</h1>
      <p>These images were identified as promotional or irrelevant by AI and removed from the article.</p>
      <div class="stats">
        <div class="stat">📁 {len(removed_files)} images removed</div>
        <div class="stat">📂 {article_dir.name}</div>
      </div>
    </div>
    
    <div class="restore-all">
      <button onclick="restoreAll()" class="btn-restore-all">♻️ Restore All Images</button>
    </div>
    
    <div class="gallery">
{chr(10).join(image_cards)}
    </div>
    
    <div class="footer">
      <p>Generated by Noosphere AI Review System</p>
      <p>CLI: <code>python -m src.cli review-images {article_dir} --restore &lt;image&gt;</code></p>
    </div>
  </div>
  
  <script>
    function restoreImage(filename) {{
      if (confirm('Restore ' + filename + ' to the article?')) {{
        alert('Run this command in terminal:\n\npython -m src.cli review-images {repr(str(article_dir))} --restore ' + filename);
      }}
    }}
    
    function restoreAll() {{
      if (confirm('Restore ALL removed images to the article?')) {{
        alert('Run this command in terminal:\n\npython -m src.cli review-images {repr(str(article_dir))} --restore-all');
      }}
    }}
  </script>
</body>
</html>"""

    html_path.write_text(html_content, encoding="utf-8")
    print(f"✅ HTML preview generated: {html_path}")
    print(f"   Open in browser: file://{html_path}")
    print(f"\n   Images: {len(image_cards)}")
    print(f"   Directory: {article_dir}")
    return 0


async def _run_review_images(args: argparse.Namespace) -> int:
    """Handle review-images command: list and optionally restore removed images."""
    import json
    from shutil import move

    article_dir = args.article_dir
    if not article_dir.exists() or not article_dir.is_dir():
        print(f"Error: Article directory not found: {article_dir}")
        return 1

    manifest_path = article_dir / "manifest.json"
    if not manifest_path.exists():
        print(f"Error: manifest.json not found in {article_dir}")
        return 1

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    image_filter = manifest.get("image_filter", {})
    removed_files = image_filter.get("removed_files", [])
    descriptions = image_filter.get("image_descriptions", {})

    removed_dir = article_dir / "removed"
    assets_dir = article_dir / "assets"

    # Fallback: scan removed/ directory if manifest has no removed_files record.
    if not removed_files and removed_dir.exists() and removed_dir.is_dir():
        removed_files = [
            str(p.relative_to(article_dir))
            for p in removed_dir.iterdir()
            if p.is_file()
        ]

    # --list: Display removed images
    if args.list or not (args.restore or args.restore_all or args.preview):
        if not removed_files:
            print("No images were removed by AI filtering.")
            return 0

        print(f"\nRemoved images in {removed_dir}:")
        print("=" * 60)
        for i, removed_path in enumerate(removed_files, 1):
            filename = Path(removed_path).name
            desc = descriptions.get(removed_path, descriptions.get(f"assets/{filename}", "No description"))
            print(f"\n{i}. {filename}")
            print(f"   Description: {desc}")
            # Check if file actually exists in removed/
            removed_file = removed_dir / filename
            if not removed_file.exists():
                # Try with numbered suffix
                for f in removed_dir.iterdir():
                    if f.stem.startswith(Path(filename).stem):
                        removed_file = f
                        break
            status = "✓ Available" if removed_file.exists() else "✗ Missing"
            print(f"   Status: {status}")
        print(f"\n{'=' * 60}")
        print(f"Total: {len(removed_files)} removed images")
        print(f"\nTo restore an image: python -m src.cli review-images {article_dir} --restore image_02.webp")
        print(f"To restore all:       python -m src.cli review-images {article_dir} --restore-all")
        print(f"To generate preview:  python -m src.cli review-images {article_dir} --preview")
        return 0

    # --preview: Generate HTML preview page
    if args.preview:
        return _generate_removed_preview_html(article_dir, removed_files, descriptions, removed_dir, assets_dir)

    # --restore: Restore specific images
    if args.restore:
        restored = []
        failed = []
        for img_name in args.restore:
            src = removed_dir / img_name
            if not src.exists():
                # Try with numbered suffixes
                for f in removed_dir.iterdir():
                    if f.stem.startswith(Path(img_name).stem):
                        src = f
                        break
            if src.exists():
                dst = assets_dir / img_name
                try:
                    src.rename(dst)
                    restored.append(img_name)
                except OSError as e:
                    failed.append(f"{img_name}: {e}")
            else:
                failed.append(f"{img_name}: not found in removed/")

        if restored:
            print(f"Restored: {', '.join(restored)}")
        if failed:
            print(f"Failed: {', '.join(failed)}")
        return 0 if not failed else 1

    # --restore-all: Restore all removed images
    if args.restore_all:
        if not removed_dir.exists():
            print("No removed/ directory found.")
            return 0

        restored = []
        for src in removed_dir.iterdir():
            if src.is_file():
                dst = assets_dir / src.name
                try:
                    src.rename(dst)
                    restored.append(src.name)
                except OSError as e:
                    print(f"Failed to restore {src.name}: {e}")

        if restored:
            print(f"Restored {len(restored)} images: {', '.join(restored)}")
        else:
            print("No images to restore.")
        return 0

    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return asyncio.run(_main_async(args))
    except Exception as exc:
        print(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
