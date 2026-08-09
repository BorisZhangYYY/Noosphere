"""Business operations exposed consistently across every Noosphere interface."""
from __future__ import annotations

import json
import re
import shutil
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.core.config.config import clear_config_cache, load_config
from src.core.config.schema import Config


def _web_helpers():
    from src.api import web

    return web


def list_articles(
    *,
    locale: str = "en-US",
    query: str = "",
    status: str = "",
    collection_id: str = "",
) -> list[dict[str, Any]]:
    """Return localized article summaries with optional lightweight filters."""
    web = _web_helpers()
    articles: list[dict[str, Any]] = []
    output_dir = load_config().output_dir_path
    if output_dir.exists():
        for manifest_path in output_dir.rglob("manifest.json"):
            summary = web._article_summary(manifest_path, locale)
            if summary:
                articles.append(summary)
    normalized_query = query.strip().casefold()
    normalized_status = status.strip().casefold()
    normalized_collection = collection_id.strip()
    if normalized_query:
        articles = [
            article
            for article in articles
            if normalized_query in " ".join(str(value) for value in article.get("searchTerms") or []).casefold()
        ]
    if normalized_status:
        articles = [article for article in articles if str(article.get("status") or "").casefold() == normalized_status]
    if normalized_collection:
        articles = [
            article
            for article in articles
            if normalized_collection
            in {
                str(item.get("id") or "")
                for item in (article.get("collection") or {}).get("collection_path") or []
            }
        ]
    articles.sort(key=lambda item: str(item.get("capturedAt") or ""), reverse=True)
    return articles


def get_article(article_id: str, *, locale: str = "en-US", include_content: bool = True) -> dict[str, Any]:
    """Return one article with its collection placement, activity, and images."""
    web = _web_helpers()
    article_dir = web._safe_article_dir(article_id)
    manifest_path = article_dir / "manifest.json"
    summary = web._article_summary(manifest_path, locale)
    if not summary:
        raise ValueError("Article manifest is missing or invalid")
    manifest = web._read_json(manifest_path)
    article = manifest.get("article") or {}
    paths = manifest.get("paths") or {}
    raw_path = article_dir / str(paths.get("raw") or "raw.md")
    reviewed_path = article_dir / str(paths.get("reviewed") or "reviewed.md")
    assets_dir = article_dir / str(paths.get("assets") or "assets")
    raw_markdown = raw_path.read_text(encoding="utf-8") if raw_path.is_file() else ""
    reviewed_markdown = reviewed_path.read_text(encoding="utf-8") if reviewed_path.is_file() else ""
    from src.core.article_metadata import article_metadata_state, editable_article_markdown, strip_editor_artifacts

    reviewed_markdown = strip_editor_artifacts(reviewed_markdown)
    protected_metadata = article_metadata_state(manifest, raw_markdown)
    referenced = {
        web._markdown_image_name(match.group(2))
        for markdown in (raw_markdown, reviewed_markdown)
        for match in web.MARKDOWN_IMAGE_RE.finditer(markdown)
    }
    assets = [
        {"name": path.name, "state": "active", "path": str(path)}
        for path in sorted(assets_dir.iterdir())
        if path.is_file() and path.name in referenced
    ] if assets_dir.is_dir() else []
    image_filter = manifest.get("image_filter") or {}
    descriptions = image_filter.get("image_descriptions") or {}
    manual_removed = set(image_filter.get("manual_removed_images") or [])
    removed_dir = article_dir / "removed"
    removed_assets = [
        {
            "name": path.name,
            "state": "removed",
            "path": str(path),
            "reason": str(descriptions.get(f"assets/{path.name}") or descriptions.get(path.name) or ""),
            "source": "manual" if f"assets/{path.name}" in manual_removed else "ai",
        }
        for path in sorted(removed_dir.iterdir())
        if path.is_file()
    ] if removed_dir.is_dir() else []
    payload: dict[str, Any] = {
        **summary,
        "publishedAt": protected_metadata["publishedAt"]["value"],
        "contentType": str(article.get("content_type") or "article"),
        "hasUploaded": bool(manifest.get("uploaded")),
        "assets": assets,
        "removedAssets": removed_assets,
        "metadata": protected_metadata,
        "metadataHistory": list((manifest.get("metadata_enrichment") or {}).get("history") or []),
    }
    if include_content:
        payload.update(
            rawMarkdown=raw_markdown,
            reviewedMarkdown=reviewed_markdown,
            editableMarkdown=editable_article_markdown(reviewed_markdown or raw_markdown),
        )
    return payload


def _article_trash_dir(article_id: str) -> Path:
    """Resolve an article's recycle-bin directory outside the active library."""
    from src.mcp.server import _validate_article_id

    _validate_article_id(article_id)
    output_dir = load_config().output_dir_path.resolve()
    trash_root = (output_dir.parent / "trash" / "articles").resolve()
    trash_dir = (trash_root / article_id).resolve()
    if trash_dir.parent != trash_root:
        raise ValueError(f"Invalid article id: {article_id}")
    return trash_dir


def trash_articles(article_ids: list[str]) -> list[dict[str, Any]]:
    """Move active article workspaces into the persistent recycle bin."""
    if not article_ids:
        raise ValueError("At least one article id is required")
    unique_ids = list(dict.fromkeys(str(article_id) for article_id in article_ids))
    from src.core.trash import ArticleTrashStore

    store = ArticleTrashStore()
    plans: list[tuple[str, Path, Path, dict[str, Any]]] = []
    for article_id in unique_ids:
        article_dir = _web_helpers()._safe_article_dir(article_id)
        trash_dir = _article_trash_dir(article_id)
        if trash_dir.exists() or store.get(article_id) is not None:
            raise ValueError(f"Article is already in the recycle bin: {article_id}")
        plans.append((article_id, article_dir, trash_dir, _web_helpers()._read_json(article_dir / "manifest.json")))

    results: list[dict[str, Any]] = []
    moved: list[tuple[str, Path, Path]] = []
    try:
        for article_id, article_dir, trash_dir, manifest in plans:
            article = manifest.get("article") or {}
            title = str(article.get("title") or article_id)
            url = str(article.get("url") or "")
            trash_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(article_dir), str(trash_dir))
            moved.append((article_id, article_dir, trash_dir))
            record = store.add(
                article_id,
                title=title,
                url=url,
                details={
                    "platform": str(article.get("platform") or "unknown"),
                    "platformLabel": str(article.get("platform_label") or article.get("platform") or "Unknown"),
                    "capturedAt": article.get("captured_at"),
                    "assetsCount": len((manifest.get("assets") or {}).get("downloaded") or []),
                },
            )
            results.append(record)
    except Exception:
        for moved_id, article_dir, trash_dir in reversed(moved):
            try:
                store.remove(moved_id)
            finally:
                if trash_dir.exists() and not article_dir.exists():
                    shutil.move(str(trash_dir), str(article_dir))
        raise
    return results


def list_trashed_articles() -> list[dict[str, Any]]:
    """Return recycle-bin records whose workspaces still exist."""
    from src.core.trash import ArticleTrashStore

    return [
        record
        for record in ArticleTrashStore().list()
        if _article_trash_dir(record["id"]).is_dir()
    ]


def restore_trashed_articles(article_ids: list[str]) -> list[dict[str, Any]]:
    """Move articles from the recycle bin back into the active library."""
    if not article_ids:
        raise ValueError("At least one article id is required")
    from src.core.trash import ArticleTrashStore

    store = ArticleTrashStore()
    output_dir = load_config().output_dir_path.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    plans: list[tuple[str, dict[str, Any], Path, Path]] = []
    for article_id in dict.fromkeys(str(article_id) for article_id in article_ids):
        record = store.get(article_id)
        if record is None:
            raise ValueError(f"Article is not in the recycle bin: {article_id}")
        trash_dir = _article_trash_dir(article_id)
        article_dir = (output_dir / article_id).resolve()
        if article_dir.parent != output_dir or article_dir.exists():
            raise ValueError(f"An active article already uses this id: {article_id}")
        if not trash_dir.is_dir():
            raise ValueError(f"Recycle-bin workspace is missing: {article_id}")
        plans.append((article_id, record, trash_dir, article_dir))

    results: list[dict[str, Any]] = []
    restored: list[tuple[str, Path, Path, dict[str, Any]]] = []
    try:
        for article_id, record, trash_dir, article_dir in plans:
            shutil.move(str(trash_dir), str(article_dir))
            restored.append((article_id, trash_dir, article_dir, record))
            store.remove(article_id)
            results.append(record)
    except Exception:
        for restored_id, trash_dir, article_dir, record in reversed(restored):
            if article_dir.exists() and not trash_dir.exists():
                shutil.move(str(article_dir), str(trash_dir))
            if store.get(restored_id) is None:
                store.add(
                    restored_id,
                    title=record["title"],
                    url=record["url"],
                    details=record.get("details") or {},
                )
        raise
    return results


def permanently_delete_trashed_articles(article_ids: list[str]) -> list[str]:
    """Permanently delete trashed workspaces and their database metadata."""
    if not article_ids:
        raise ValueError("At least one article id is required")
    from src.core.activity import ArticleActivityStore
    from src.core.collections import CollectionStore
    from src.core.trash import ArticleTrashStore

    trash_store = ArticleTrashStore()
    unique_ids = list(dict.fromkeys(str(article_id) for article_id in article_ids))
    for article_id in unique_ids:
        if trash_store.get(article_id) is None:
            raise ValueError(f"Article is not in the recycle bin: {article_id}")
    deleted: list[str] = []
    for article_id in unique_ids:
        trash_dir = _article_trash_dir(article_id)
        if trash_dir.is_dir():
            shutil.rmtree(trash_dir)
        CollectionStore().delete_assignment(article_id)
        ArticleActivityStore().delete_article(article_id)
        trash_store.remove(article_id)
        deleted.append(article_id)
    return deleted


def save_reviewed_markdown(
    article_id: str,
    reviewed_markdown: str,
    *,
    image_states: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Atomically update reviewed.md and staged image states while preserving raw.md."""
    if not isinstance(reviewed_markdown, str):
        raise ValueError("reviewed_markdown must be a string")
    if len(reviewed_markdown.encode("utf-8")) > 10 * 1024 * 1024:
        raise ValueError("Reviewed Markdown exceeds the 10 MB limit")
    if image_states is None:
        image_states = {}
    if not isinstance(image_states, dict):
        raise ValueError("image_states must be an object")
    web = _web_helpers()
    article_dir = web._safe_article_dir(article_id)
    manifest_path = article_dir / "manifest.json"
    reviewed_path = article_dir / "reviewed.md"
    manifest = web._read_json(manifest_path)
    raw_path = article_dir / "raw.md"
    raw_markdown = raw_path.read_text(encoding="utf-8") if raw_path.is_file() else ""
    assets_dir = article_dir / "assets"
    removed_dir = article_dir / "removed"
    assets_dir.mkdir(exist_ok=True)
    removed_dir.mkdir(exist_ok=True)
    normalized_states: dict[str, str] = {}
    moves: list[tuple[Path, Path]] = []
    removed_names = {path.name for path in removed_dir.iterdir() if path.is_file()}
    for raw_name, raw_state in image_states.items():
        asset_name = str(raw_name).strip()
        state = str(raw_state).strip()
        if not asset_name or Path(asset_name).name != asset_name:
            raise ValueError("Invalid asset name")
        if state not in {"active", "removed"}:
            raise ValueError("Image state must be active or removed")
        active_path = assets_dir / asset_name
        removed_path = removed_dir / asset_name
        if active_path.is_file() and removed_path.is_file():
            raise ValueError(f"Image exists in both active and removed states: {asset_name}")
        if not active_path.is_file() and not removed_path.is_file():
            raise ValueError(f"Image asset not found: {asset_name}")
        normalized_states[asset_name] = state
        if state == "removed":
            removed_names.add(asset_name)
            if active_path.is_file():
                moves.append((active_path, removed_path))
        else:
            removed_names.discard(asset_name)
            if removed_path.is_file():
                moves.append((removed_path, active_path))

    from src.core.article_metadata import render_protected_review, strip_editor_artifacts

    normalized_markdown = strip_editor_artifacts(reviewed_markdown)
    for asset_name, state in normalized_states.items():
        if state == "removed":
            normalized_markdown = web._replace_image_target(normalized_markdown, asset_name, None)
            continue
        normalized_markdown = web._replace_image_target(
            normalized_markdown,
            asset_name,
            f"assets/{asset_name}",
        )
        present = {
            web._markdown_image_name(match.group(2))
            for match in web.MARKDOWN_IMAGE_RE.finditer(normalized_markdown)
        }
        if asset_name not in present:
            from src.core.review.image_filter import _restore_images_to_original_positions

            normalized_markdown = _restore_images_to_original_positions(
                normalized_markdown,
                raw_markdown,
                {f"assets/{asset_name}"},
            )
            present = {
                web._markdown_image_name(match.group(2))
                for match in web.MARKDOWN_IMAGE_RE.finditer(normalized_markdown)
            }
            if asset_name not in present:
                normalized_markdown = (
                    normalized_markdown.rstrip()
                    + f"\n\n![{Path(asset_name).stem}](assets/{asset_name})\n"
                )

    image_filter = manifest.setdefault("image_filter", {})
    manual_removed = set(image_filter.get("manual_removed_images") or [])
    removed_files = set(image_filter.get("removed_files") or [])
    promotion_images = set(image_filter.get("promotion_images") or [])
    for asset_name, state in normalized_states.items():
        relative_asset = f"assets/{asset_name}"
        relative_removed = f"removed/{asset_name}"
        if state == "removed":
            manual_removed.add(relative_asset)
            removed_files.add(relative_removed)
        else:
            manual_removed.discard(relative_asset)
            removed_files.discard(relative_removed)
            promotion_images.discard(relative_asset)
    image_filter["manual_removed_images"] = sorted(manual_removed)
    image_filter["removed_files"] = sorted(removed_files)
    image_filter["promotion_images"] = sorted(promotion_images)

    protected_markdown = render_protected_review(normalized_markdown, manifest, raw_markdown)
    persisted_markdown = web._persistable_reviewed_markdown(protected_markdown, removed_names)
    original_reviewed = reviewed_path.read_text(encoding="utf-8") if reviewed_path.is_file() else None
    original_manifest = manifest_path.read_text(encoding="utf-8") if manifest_path.is_file() else None
    completed_moves: list[tuple[Path, Path]] = []
    try:
        for source, destination in moves:
            source.rename(destination)
            completed_moves.append((source, destination))
        web._atomic_write_text(reviewed_path, persisted_markdown)
        if normalized_states:
            web._atomic_write_text(
                manifest_path,
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            )
    except OSError:
        for source, destination in reversed(completed_moves):
            if destination.exists() and not source.exists():
                destination.rename(source)
        if original_reviewed is not None:
            web._atomic_write_text(reviewed_path, original_reviewed)
        if original_manifest is not None:
            web._atomic_write_text(manifest_path, original_manifest)
        raise
    return {
        "ok": True,
        "article_id": article_id,
        "image_states": normalized_states,
    }


def get_reflection(article_id: str) -> dict[str, Any]:
    """Return reflection Markdown and its persisted upload preference."""
    web = _web_helpers()
    article_dir = web._safe_article_dir(article_id)
    from src.core.reflection import read_reflection, read_upload_enabled

    markdown = read_reflection(article_dir)
    return {
        "articleId": article_id,
        "markdown": markdown,
        "uploadEnabled": read_upload_enabled(article_dir / "manifest.json"),
        "exists": bool(markdown.strip()),
    }


def save_reflection(
    article_id: str,
    markdown: str | None = None,
    *,
    upload_enabled: bool | None = None,
) -> dict[str, Any]:
    """Update reflection Markdown and/or its upload preference."""
    if markdown is not None:
        if not isinstance(markdown, str):
            raise ValueError("reflection_markdown must be a string")
        if len(markdown.encode("utf-8")) > 10 * 1024 * 1024:
            raise ValueError("Reflection Markdown exceeds the 10 MB limit")
    if upload_enabled is not None and not isinstance(upload_enabled, bool):
        raise ValueError("upload_enabled must be a boolean")
    if markdown is None and upload_enabled is None:
        raise ValueError("Provide markdown, upload_enabled, or both")

    web = _web_helpers()
    article_dir = web._safe_article_dir(article_id)
    from src.core.reflection import set_upload_enabled, write_reflection

    if markdown is not None:
        write_reflection(article_dir, markdown)
    if upload_enabled is not None:
        set_upload_enabled(article_dir / "manifest.json", upload_enabled)
    return get_reflection(article_id)


def update_article_metadata(article_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    """Update only missing author/publication fields through a controlled boundary."""
    if not isinstance(updates, dict):
        raise ValueError("Metadata updates must be an object")
    allowed = {"author", "publishedAt"}
    unexpected = set(updates) - allowed
    if unexpected:
        raise ValueError(f"Protected metadata cannot be edited: {', '.join(sorted(unexpected))}")
    if not updates:
        raise ValueError("At least one metadata field is required")

    web = _web_helpers()
    article_dir = web._safe_article_dir(article_id)
    manifest_path = article_dir / "manifest.json"
    reviewed_path = article_dir / "reviewed.md"
    raw_path = article_dir / "raw.md"
    manifest = web._read_json(manifest_path)
    raw_markdown = raw_path.read_text(encoding="utf-8") if raw_path.is_file() else ""
    reviewed_markdown = reviewed_path.read_text(encoding="utf-8") if reviewed_path.is_file() else raw_markdown
    from src.core.article_metadata import article_metadata_state, render_protected_review, strip_editor_artifacts

    reviewed_markdown = strip_editor_artifacts(reviewed_markdown)
    state = article_metadata_state(manifest, raw_markdown)
    enrichment = manifest.setdefault("metadata_enrichment", {})
    fields = enrichment.setdefault("fields", {})
    history = enrichment.setdefault("history", [])
    now = datetime.now(UTC).isoformat()
    for key, raw_value in updates.items():
        if not state[key]["editable"]:
            raise ValueError(f"Source metadata is protected and already contains {key}")
        value = str(raw_value or "").strip()
        previous = fields.get(key) if isinstance(fields.get(key), dict) else None
        if value:
            fields[key] = {
                "value": value,
                "source": "manual",
                "evidence": "",
                "updated_at": now,
            }
            action = "accepted"
        else:
            fields.pop(key, None)
            action = "reverted"
        history.append({
            "field": key,
            "action": action,
            "source": "manual",
            "value": value,
            "previous_value": str((previous or {}).get("value") or ""),
            "evidence": "",
            "at": now,
        })

    protected_markdown = render_protected_review(reviewed_markdown, manifest, raw_markdown)
    web._atomic_write_text(reviewed_path, protected_markdown)
    web._atomic_write_text(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return {
        "ok": True,
        "article_id": article_id,
        "metadata": article_metadata_state(manifest, raw_markdown),
    }


def set_article_image_state(
    article_id: str,
    asset_name: str,
    state: str,
    *,
    reviewed_markdown: str | None = None,
) -> dict[str, Any]:
    """Move one image between active and removed states and update reviewed.md."""
    if not asset_name or Path(asset_name).name != asset_name:
        raise ValueError("Invalid asset name")
    if state not in {"active", "removed"}:
        raise ValueError("state must be active or removed")
    web = _web_helpers()
    article_dir = web._safe_article_dir(article_id)
    reviewed_path = article_dir / "reviewed.md"
    if reviewed_markdown is None:
        reviewed_markdown = reviewed_path.read_text(encoding="utf-8") if reviewed_path.is_file() else ""
    save_reviewed_markdown(
        article_id,
        reviewed_markdown,
        image_states={asset_name: state},
    )
    return {"ok": True, "article_id": article_id, "name": asset_name, "state": state}


def list_collections(
    *,
    include_deleted: bool = False,
    locale: str | None = None,
) -> list[dict[str, Any]]:
    from src.core.collections import CollectionStore

    return CollectionStore().list_tree(
        include_retired=include_deleted,
        locale=locale,
    )


def create_collection(
    *,
    name: str,
    description: str = "",
    parent_id: str | None = None,
    locale: str | None = None,
) -> dict[str, Any]:
    from src.core.collections import CollectionStore

    return CollectionStore().create_collection(
        name=name,
        description=description,
        parent_id=parent_id,
        locale=locale,
    )


def update_collection(
    collection_id: str,
    *,
    name: str | None = None,
    description: str | None = None,
    retired: bool | None = None,
    locale: str | None = None,
) -> dict[str, Any]:
    from src.core.collections import CollectionStore

    return CollectionStore().update_collection(
        collection_id,
        name=name,
        description=description,
        retired=retired,
        locale=locale,
    )


def place_article(
    article_id: str,
    *,
    collection_id: str | None = None,
    collection_path: list[str] | None = None,
    create_missing: bool = False,
    collection_description: str = "",
) -> dict[str, Any]:
    """Place an article by stable ID or an explicitly authorized path."""
    _web_helpers()._safe_article_dir(article_id)
    from src.core.collections import CollectionStore

    store = CollectionStore()
    normalized_id = str(collection_id or "").strip() or None
    normalized_path = (
        [str(segment).strip() for segment in collection_path]
        if collection_path is not None
        else None
    )
    if normalized_id and normalized_path:
        raise ValueError("Provide either collection_id or collection_path, not both")
    if normalized_path is not None and (
        not normalized_path or any(not segment for segment in normalized_path)
    ):
        raise ValueError("collection_path must contain at least one non-empty name")
    if create_missing and normalized_path is None:
        raise ValueError("create_missing requires an explicit collection_path")
    if collection_description.strip() and normalized_path is None:
        raise ValueError("collection_description requires an explicit collection_path")

    created_collections: list[dict[str, Any]] = []
    if normalized_path is not None:
        target = store.get_collection_by_path(normalized_path)
        if target is None:
            if not create_missing:
                raise ValueError(
                    "Collection path does not exist; explicitly allow creation to create its final segment"
                )
            description = collection_description.strip()
            if not description:
                raise ValueError(
                    "A non-empty collection_description is required when creating a missing collection"
                )
            parent = None
            if len(normalized_path) > 1:
                parent = store.get_collection_by_path(normalized_path[:-1])
                if parent is None:
                    raise ValueError(
                        "Only the final collection path segment may be created; its parent path must already exist"
                    )
            target = store.create_collection(
                name=normalized_path[-1],
                description=description,
                parent_id=str(parent["id"]) if parent else None,
            )
            created_collections.append(target)
        normalized_id = str(target["id"])

    assignment = store.assign_article(
        article_id,
        collection_id=normalized_id,
        reason="Explicit path placement" if normalized_path is not None else "Manual placement",
    )
    assignment["created_collections"] = created_collections
    return assignment


def get_settings() -> dict[str, Any]:
    return _web_helpers()._settings_payload(load_config())


def save_settings(payload: dict[str, Any], *, active_provider: str | None = None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Settings payload must be an object")
    web = _web_helpers()
    draft = dict(payload)
    if active_provider:
        draft["aiProvider"] = active_provider
    updated = web._merge_settings(load_config(), draft)
    web._atomic_write_config(updated)
    clear_config_cache()
    persisted = load_config()
    if active_provider and persisted.ai.provider.casefold() != active_provider.casefold():
        raise ValueError(f"Failed to activate AI provider: {active_provider}")
    return web._settings_payload(persisted)


def get_secret(service: str, *, provider_name: str = "") -> str:
    """Reveal one local secret for the explicit CLI-only command."""
    config = load_config()
    normalized = service.strip().casefold()
    if normalized == "ai":
        selected = provider_name or config.ai.provider
        provider = config.ai_providers.get(selected)
        if provider is None:
            raise ValueError(f"AI provider not found: {selected}")
        return provider.api_key
    if normalized == "firecrawl":
        return config.crawler.firecrawl.api_key or ""
    if normalized == "siyuan":
        return config.siyuan.token if config.siyuan and config.siyuan.token else ""
    raise ValueError(f"Unsupported secret service: {service}")


async def test_service(service: str, *, provider_name: str = "", settings: dict[str, Any] | None = None) -> dict[str, Any]:
    normalized = service.strip().casefold()
    try:
        if normalized == "ai":
            from src.integrations.ai_client import AIClient, resolve_ai_settings

            config = _web_helpers()._merge_settings(load_config(), settings) if settings else load_config()
            selected = provider_name or config.ai.provider
            ai_settings = replace(
                resolve_ai_settings(config, selected),
                max_output_tokens=512,
                temperature=0,
                timeout_seconds=60,
            )
            response = await AIClient(ai_settings).generate_text(
                "You are a connection test. Follow the user instruction exactly.",
                "Reply with exactly NOOSPHERE_OK",
            )
            if response.text.strip() != "NOOSPHERE_OK":
                raise ValueError("Provider returned an unexpected connection-test response")
            return {"ok": True, "service": "ai", "provider": selected, "model": response.model}
        if normalized == "firecrawl":
            from src.integrations.crawler import _crawl_page_firecrawl

            result = await _crawl_page_firecrawl("https://example.com", delay_before_return_html=0)
            if not result.success:
                raise ValueError(result.error or "Firecrawl test failed")
            return {"ok": True, "service": "firecrawl", "statusCode": result.status_code}
        raise ValueError(f"Unsupported service test: {service}")
    except Exception as exc:
        message = str(exc)
        if "nodename nor servname" in message.lower() or "name or service not known" in message.lower():
            message = f"DNS resolution failed for the provider host. Check Docker/host DNS and proxy settings. Original error: {message}"
        raise ValueError(message) from exc


def get_pipeline_settings(*, locale: str = "en-US") -> dict[str, Any]:
    return _web_helpers()._pipeline_payload(load_config(), locale)


def save_pipeline_settings(payload: dict[str, Any], *, locale: str = "en-US") -> dict[str, Any]:
    """Persist review mode, language, active perspective, and custom profiles."""
    if not isinstance(payload, dict):
        raise ValueError("Pipeline settings payload must be an object")
    config = load_config()
    review_mode = str(payload.get("reviewMode") or config.pipeline.review_mode)
    active = str(payload.get("activePerspective") or config.pipeline.active_perspective)
    output_language = str(payload.get("outputLanguage") or config.pipeline.output_language)
    if review_mode not in {"auto_upload", "ai_then_manual"}:
        raise ValueError(f"Unsupported review mode: {review_mode}")
    if output_language not in {"follow_ui", "zh-CN", "en-US", "source"}:
        raise ValueError(f"Unsupported output language: {output_language}")
    perspectives = payload.get("perspectives")
    if not isinstance(perspectives, list):
        raise ValueError("Perspective contents are required")
    if len(json.dumps(perspectives, ensure_ascii=False).encode("utf-8")) > 4 * 1024 * 1024:
        raise ValueError("The custom perspective payload exceeds the 4 MB limit")
    from src.core.paths import resolve_project_path, runtime_home
    from src.core.review.output_contract import validate_output_template

    data = config.model_dump(mode="json")
    data.setdefault("pipeline", {})["review_mode"] = review_mode
    data["pipeline"]["output_language"] = output_language
    next_perspectives = {
        key: profile.model_dump(mode="json")
        for key, profile in config.pipeline.perspectives.items()
        if profile.builtin
    }
    custom_files: list[tuple[Path, str]] = []
    seen_ids = set(next_perspectives)
    for item in perspectives:
        if not isinstance(item, dict) or bool(item.get("builtin")):
            continue
        key = str(item.get("id") or "").strip()
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", key):
            raise ValueError("Custom perspective IDs may contain lowercase letters, numbers, hyphens, and underscores")
        if key in seen_ids:
            raise ValueError(f"Duplicate review perspective: {key}")
        seen_ids.add(key)
        label = str(item.get("label") or "").strip()
        description = str(item.get("description") or "").strip()
        prompt = item.get("prompt")
        template = item.get("template")
        output_sections = item.get("outputSections")
        body_section = str(item.get("bodySection") or "").strip()
        if not label or len(label) > 80:
            raise ValueError(f"Perspective {key} needs a label of at most 80 characters")
        if len(description) > 400:
            raise ValueError(f"Perspective {key} description is too long")
        if not isinstance(prompt, str) or not prompt.strip() or not isinstance(template, str):
            raise ValueError(f"Perspective {key} is missing prompt or template content")
        if not isinstance(output_sections, dict) or not output_sections:
            raise ValueError(f"Perspective {key} is missing output sections")
        normalized_sections: dict[str, str] = {}
        for slot, heading in output_sections.items():
            slot_name = str(slot).strip()
            heading_name = str(heading).strip()
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,47}", slot_name) or not heading_name:
                raise ValueError(f"Perspective {key} has an invalid output section")
            normalized_sections[slot_name] = heading_name
        if body_section not in normalized_sections:
            raise ValueError(f"Perspective {key} body section is invalid")
        validate_output_template(template, normalized_sections)
        existing = config.pipeline.perspectives.get(key)
        custom_root = runtime_home() / "prompts" / "review"
        prompt_path = resolve_project_path(existing.prompt_path) if existing and not existing.builtin else custom_root / f"{key}.prompt.md"
        template_path = resolve_project_path(existing.template_path) if existing and not existing.builtin else custom_root / f"{key}.template.md"
        next_perspectives[key] = {
            "label": label,
            "description": description,
            "prompt_path": str(prompt_path),
            "template_path": str(template_path),
            "output_sections": normalized_sections,
            "body_section": body_section,
            "builtin": False,
            "localizations": {},
        }
        custom_files.extend(((prompt_path, prompt), (template_path, template)))
    if active not in next_perspectives:
        raise ValueError(f"Unknown review perspective: {active}")
    data["pipeline"]["active_perspective"] = active
    data["pipeline"]["perspectives"] = next_perspectives
    updated = Config.model_validate(data)
    web = _web_helpers()
    for destination, content in custom_files:
        web._atomic_write_text(destination, content)
    web._atomic_write_config(updated)
    clear_config_cache()
    return web._pipeline_payload(load_config(), locale)


def upsert_review_perspective(
    perspective_id: str,
    *,
    label: str,
    description: str,
    prompt: str,
    template: str,
    output_sections: dict[str, str],
    body_section: str,
    locale: str = "en-US",
    activate: bool = False,
) -> dict[str, Any]:
    payload = get_pipeline_settings(locale=locale)
    existing = next((item for item in payload["perspectives"] if item["id"] == perspective_id), None)
    if existing and existing.get("builtin"):
        raise ValueError("Built-in review perspectives cannot be modified")
    replacement = {
        "id": perspective_id,
        "label": label,
        "description": description,
        "prompt": prompt,
        "template": template,
        "builtin": False,
        "editable": True,
        "outputSections": output_sections,
        "bodySection": body_section,
    }
    payload["perspectives"] = [replacement if item["id"] == perspective_id else item for item in payload["perspectives"]]
    if not any(item["id"] == perspective_id for item in payload["perspectives"]):
        payload["perspectives"].append(replacement)
    if activate:
        payload["activePerspective"] = perspective_id
    return save_pipeline_settings(payload, locale=locale)


def delete_review_perspective(perspective_id: str, *, locale: str = "en-US") -> dict[str, Any]:
    payload = get_pipeline_settings(locale=locale)
    target = next((item for item in payload["perspectives"] if item["id"] == perspective_id), None)
    if target is None:
        raise ValueError(f"Review perspective not found: {perspective_id}")
    if target.get("builtin"):
        raise ValueError("Built-in review perspectives cannot be deleted")
    payload["perspectives"] = [item for item in payload["perspectives"] if item["id"] != perspective_id]
    if payload["activePerspective"] == perspective_id:
        payload["activePerspective"] = next(item["id"] for item in payload["perspectives"] if item.get("builtin"))
    return save_pipeline_settings(payload, locale=locale)
