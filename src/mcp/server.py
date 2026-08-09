"""Noosphere MCP server exposing the article pipeline as AI-callable tools."""
from __future__ import annotations

import logging
import os
import re
import asyncio
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from starlette.responses import RedirectResponse
from starlette.staticfiles import StaticFiles

from src.core.config.config import load_config
from src.core.models.article import UploadResult
from src.core.paths import project_root
from src.core.review.review_validation import ValidationResult

logger = logging.getLogger(__name__)


class SPAStaticFiles(StaticFiles):
    """Serve the React entry point for client-side routes under /app."""

    async def get_response(self, path: str, scope):
        try:
            response = await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404 or Path(path).suffix:
                raise
            return await super().get_response("index.html", scope)
        if response.status_code == 404 and not Path(path).suffix:
            return await super().get_response("index.html", scope)
        return response

mcp = FastMCP("noosphere")

# ---------------------------------------------------------------------------
# URL validation
# ---------------------------------------------------------------------------

_RE_HTTP_URL = re.compile(r"^https?://", re.IGNORECASE)


def _validate_url(url: str) -> str:
    """Return a stripped, validated HTTP/HTTPS URL or raise ValueError."""
    if not isinstance(url, str) or not url.strip():
        raise ValueError("URL must be a non-empty string")

    stripped = url.strip()
    if not _RE_HTTP_URL.match(stripped):
        raise ValueError(f"URL must start with http:// or https://: {stripped[:80]!r}")

    parsed = urlparse(stripped)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid URL (missing scheme or host): {stripped[:80]!r}")
    if " " in parsed.netloc or "\n" in parsed.netloc:
        raise ValueError(f"URL host contains whitespace: {stripped[:80]!r}")

    return stripped


def _resolve_article_dir(article_id: str) -> Path:
    """Return the article workspace directory for *article_id*."""
    _validate_article_id(article_id)
    config = load_config()
    article_dir = config.output_dir_path / article_id
    if not article_dir.exists():
        raise ValueError(f"Article not found: {article_id}")
    return article_dir


def _validate_article_id(article_id: str) -> str:
    """Reject article identifiers that could escape the output workspace."""
    if not isinstance(article_id, str) or not article_id.strip():
        raise ValueError("article_id must be a non-empty string")
    if article_id != article_id.strip() or article_id in {".", ".."}:
        raise ValueError("article_id must be a single workspace directory name")
    if "/" in article_id or "\\" in article_id or Path(article_id).is_absolute():
        raise ValueError("article_id must not contain a path separator")
    return article_id


def _validate_upload_target(target: str) -> str | None:
    """Normalize the MCP upload target to a configured adapter name."""
    if target == "auto":
        return None
    if target not in {"local", "siyuan"}:
        raise ValueError("target must be one of: auto, local, siyuan")
    return target


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def extract_article(url: str) -> dict[str, Any]:
    """Extract an article from *url* and download its images.

    Returns the local article_id that can be passed to review_article or
    upload_article.
    """
    url = _validate_url(url)

    from src.graph.graph import run_extract_graph

    reviewed_path = await run_extract_graph(url)
    article_id = reviewed_path.parent.name
    return {
        "ok": True,
        "operation": "extract",
        "article_id": article_id,
        "status": "captured",
        "reviewed_path": str(reviewed_path),
        "next_actions": ["review_article", "get_article"],
    }


@mcp.tool()
async def review_article(article_id: str, perspective: str = "", language: str = "source") -> dict[str, Any]:
    """Run AI copy-editing and deterministic assembly on an extracted article."""
    article_dir = _resolve_article_dir(article_id)
    reviewed_path = article_dir / "reviewed.md"
    if not reviewed_path.exists():
        raise ValueError(f"reviewed.md not found for article: {article_id}")

    from src.graph.graph import run_ai_review_graph

    result: ValidationResult = await run_ai_review_graph(reviewed_path, perspective=perspective or None, output_language=language)
    return {
        "ok": result.ok,
        "operation": "review",
        "article_id": article_id,
        "status": "reviewed" if result.ok else "failed",
        "perspective": perspective or load_config().pipeline.active_perspective,
        "language": language,
        "diagnostics": [getattr(issue, "message", str(issue)) for issue in result.issues],
        "next_actions": ["get_article", "upload_article"] if result.ok else ["get_article"],
    }


@mcp.tool()
async def upload_article(
    article_id: str,
    *,
    target: str = "auto",
    include_reflection: bool | None = None,
) -> dict[str, Any]:
    """Upload a reviewed article to the configured note platform."""
    article_dir = _resolve_article_dir(article_id)
    reviewed_path = article_dir / "reviewed.md"
    if not reviewed_path.exists():
        raise ValueError(f"reviewed.md not found for article: {article_id}")

    from src.graph.graph import run_upload_graph

    result: UploadResult = await run_upload_graph(
        reviewed_path,
        target=_validate_upload_target(target),
        include_reflection=include_reflection,
    )
    return {
        "ok": True,
        "operation": "upload",
        "article_id": article_id,
        "status": "uploaded",
        "target": target,
        "hpath": result.hpath,
        "created": result.created,
        "include_reflection": include_reflection,
    }


@mcp.tool()
async def get_article_reflection(article_id: str) -> dict[str, Any]:
    """Return an article's reflection and upload preference."""
    _resolve_article_dir(article_id)
    from src.application.service import get_reflection

    reflection = await _to_thread(get_reflection, article_id)
    return {"ok": True, "operation": "reflect", "article_id": article_id, **reflection}


@mcp.tool()
async def save_article_reflection(
    article_id: str,
    markdown: str | None = None,
    *,
    upload_enabled: bool | None = None,
) -> dict[str, Any]:
    """Save reflection Markdown and/or its persistent upload preference."""
    _resolve_article_dir(article_id)
    from src.application.service import save_reflection

    reflection = await _to_thread(
        save_reflection,
        article_id,
        markdown,
        upload_enabled=upload_enabled,
    )
    return {"ok": True, "operation": "reflect", "article_id": article_id, **reflection}


@mcp.tool()
async def list_article_annotations(article_id: str) -> dict[str, Any]:
    """List Markdown interpretations anchored to quoted article passages."""
    _resolve_article_dir(article_id)
    from src.application.service import get_article_annotations

    annotations = await _to_thread(get_article_annotations, article_id)
    return {"ok": True, "operation": "annotations.list", **annotations}


@mcp.tool()
async def create_article_annotation(
    article_id: str,
    quote: str,
    note: str,
    prefix: str = "",
    suffix: str = "",
    occurrence: int = 0,
) -> dict[str, Any]:
    """Anchor a Markdown interpretation to an exact passage from an article."""
    _resolve_article_dir(article_id)
    from src.application.service import create_article_annotation as create_annotation

    annotation = await _to_thread(
        create_annotation,
        article_id,
        quote=quote,
        note=note,
        prefix=prefix,
        suffix=suffix,
        occurrence=occurrence,
    )
    return {"ok": True, "operation": "annotations.create", "article_id": article_id, "annotation": annotation}


@mcp.tool()
async def update_article_annotation(article_id: str, annotation_id: str, note: str) -> dict[str, Any]:
    """Replace the Markdown interpretation without changing its quote anchor."""
    _resolve_article_dir(article_id)
    from src.application.service import update_article_annotation as update_annotation

    annotation = await _to_thread(update_annotation, article_id, annotation_id, note=note)
    return {"ok": True, "operation": "annotations.update", "article_id": article_id, "annotation": annotation}


@mcp.tool()
async def delete_article_annotation(article_id: str, annotation_id: str) -> dict[str, Any]:
    """Delete one quoted-passage interpretation."""
    _resolve_article_dir(article_id)
    from src.application.service import delete_article_annotation as delete_annotation

    annotation = await _to_thread(delete_annotation, article_id, annotation_id)
    return {
        "ok": True,
        "operation": "annotations.delete",
        "article_id": article_id,
        "deleted": True,
        "annotation": annotation,
    }


@mcp.tool()
async def polish_article_reflection(
    article_id: str,
    *,
    apply: bool = False,
    markdown: str | None = None,
) -> dict[str, Any]:
    """Polish a reflection and apply it only when explicitly requested."""
    article_dir = _resolve_article_dir(article_id)
    reviewed_path = article_dir / "reviewed.md"
    if not reviewed_path.is_file():
        raise ValueError(f"reviewed.md not found for article: {article_id}")
    from src.graph.graph import run_reflection_graph

    result = await run_reflection_graph(reviewed_path, reflection=markdown)
    if apply:
        from src.application.service import save_reflection

        await _to_thread(save_reflection, article_id, result["markdown"])
    return {
        "ok": True,
        "operation": "reflect",
        "article_id": article_id,
        "status": "applied" if apply else "polished",
        "polished_markdown": result["markdown"],
        "model": result["model"],
        "provider": result["provider"],
    }


@mcp.tool()
async def run_pipeline(url: str, *, auto_confirm: bool = True, perspective: str = "", language: str = "source") -> dict[str, Any]:
    """Run the full extract → ai-review → upload pipeline for *url*."""
    url = _validate_url(url)

    from src.graph.graph import run_pipeline_graph

    result: UploadResult = await run_pipeline_graph(
        url,
        auto_confirm=auto_confirm,
        perspective=perspective or None,
        output_language=language,
    )
    return {
        "ok": True,
        "operation": "pipeline",
        "url": url,
        "status": "uploaded",
        "perspective": perspective or load_config().pipeline.active_perspective,
        "language": language,
        "hpath": result.hpath,
        "created": result.created,
    }


@mcp.tool()
async def list_articles(
    query: str = "",
    status: str = "",
    collection_id: str = "",
    locale: str = "en-US",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """List articles with collection paths and optional search filters."""
    from src.application.service import list_articles as application_list_articles

    items = await _to_thread(
        application_list_articles,
        locale=locale,
        query=query,
        status=status,
        collection_id=collection_id,
    )
    safe_offset = max(0, offset)
    safe_limit = min(200, max(1, limit))
    return {
        "ok": True,
        "total": len(items),
        "offset": safe_offset,
        "limit": safe_limit,
        "articles": items[safe_offset:safe_offset + safe_limit],
    }


@mcp.tool()
async def get_article(article_id: str, locale: str = "en-US", include_content: bool = True) -> dict[str, Any]:
    """Get article metadata, activity, collection path, assets, and reviewed content."""
    from src.application.service import get_article as application_get_article

    article = await _to_thread(application_get_article, article_id, locale=locale, include_content=include_content)
    return {"ok": True, "article": article}


@mcp.tool()
async def update_article_content(article_id: str, reviewed_markdown: str) -> dict[str, Any]:
    """Replace reviewed.md while keeping raw.md immutable."""
    from src.application.service import save_reviewed_markdown

    return await _to_thread(save_reviewed_markdown, article_id, reviewed_markdown)


@mcp.tool()
async def update_missing_article_metadata(
    article_id: str,
    author: str | None = None,
    published_at: str | None = None,
) -> dict[str, Any]:
    """Fill author or publication time only when the captured source left it missing."""
    from src.application.service import update_article_metadata

    updates = {
        key: value
        for key, value in {"author": author, "publishedAt": published_at}.items()
        if value is not None
    }
    return await _to_thread(update_article_metadata, article_id, updates)


@mcp.tool()
async def list_collections(include_deleted: bool = False) -> dict[str, Any]:
    """Return the complete user-owned collection tree at arbitrary depth."""
    from src.application.service import list_collections as application_list_collections

    collections = await _to_thread(
        application_list_collections,
        include_deleted=include_deleted,
    )
    return {"ok": True, "collections": collections}


@mcp.tool()
async def create_collection(
    name: str,
    description: str = "",
    parent_id: str = "",
) -> dict[str, Any]:
    """Create a collection at the root or inside any existing collection."""
    from src.application.service import create_collection as create_collection_operation

    collection = await _to_thread(
        create_collection_operation,
        name=name,
        description=description,
        parent_id=parent_id or None,
    )
    return {"ok": True, "collection": collection}


@mcp.tool()
async def update_collection(
    collection_id: str,
    name: str | None = None,
    description: str | None = None,
    retired: bool | None = None,
) -> dict[str, Any]:
    """Rename, describe, delete, or restore one collection subtree."""
    from src.application.service import update_collection as update_collection_operation

    collection = await _to_thread(
        update_collection_operation,
        collection_id,
        name=name,
        description=description,
        retired=retired,
    )
    return {"ok": True, "collection": collection}


@mcp.tool()
async def delete_collection(
    collection_id: str,
) -> dict[str, Any]:
    """Recoverably delete one collection and its complete descendant subtree."""
    from src.application.service import update_collection as update_collection_operation

    collection = await _to_thread(
        update_collection_operation,
        collection_id,
        retired=True,
    )
    return {
        "ok": True,
        "deleted": True,
        "recoverable": True,
        "collection": collection,
        "next_actions": ["restore_collection", "list_collections"],
    }


@mcp.tool()
async def restore_collection(
    collection_id: str,
) -> dict[str, Any]:
    """Restore a recoverably deleted collection and its descendants."""
    from src.application.service import update_collection as update_collection_operation

    collection = await _to_thread(
        update_collection_operation,
        collection_id,
        retired=False,
    )
    return {
        "ok": True,
        "deleted": False,
        "recoverable": True,
        "collection": collection,
        "next_actions": ["list_collections", "place_article"],
    }


@mcp.tool()
async def place_article(
    article_id: str,
    collection_id: str = "",
    collection_path: list[str] | None = None,
    create_missing: bool = False,
    collection_description: str = "",
) -> dict[str, Any]:
    """Move an article by ID or explicit path; optionally create only a missing leaf."""
    from src.application.service import place_article as application_place_article

    assignment = await _to_thread(
        application_place_article,
        article_id,
        collection_id=collection_id or None,
        collection_path=collection_path,
        create_missing=create_missing,
        collection_description=collection_description,
    )
    return {"ok": True, "article_id": article_id, "collection": assignment}


@mcp.tool()
async def list_review_perspectives(locale: str = "en-US") -> dict[str, Any]:
    """List built-in and custom review perspectives and their template contracts."""
    from src.application.service import get_pipeline_settings

    settings = await _to_thread(get_pipeline_settings, locale=locale)
    return {
        "ok": True,
        "active_perspective": settings["activePerspective"],
        "review_mode": settings["reviewMode"],
        "output_language": settings["outputLanguage"],
        "perspectives": settings["perspectives"],
    }


@mcp.tool()
async def save_review_perspective(
    perspective_id: str,
    label: str,
    description: str,
    prompt: str,
    template: str,
    output_sections: dict[str, str],
    body_section: str,
    locale: str = "en-US",
    activate: bool = False,
) -> dict[str, Any]:
    """Create or update a custom perspective after validating its template fields."""
    from src.application.service import upsert_review_perspective

    settings = await _to_thread(
        upsert_review_perspective,
        perspective_id,
        label=label,
        description=description,
        prompt=prompt,
        template=template,
        output_sections=output_sections,
        body_section=body_section,
        locale=locale,
        activate=activate,
    )
    return {"ok": True, "active_perspective": settings["activePerspective"], "perspectives": settings["perspectives"]}


@mcp.tool()
async def delete_review_perspective(perspective_id: str, locale: str = "en-US") -> dict[str, Any]:
    """Delete a custom perspective; built-in perspectives remain immutable."""
    from src.application.service import delete_review_perspective

    settings = await _to_thread(delete_review_perspective, perspective_id, locale=locale)
    return {"ok": True, "active_perspective": settings["activePerspective"], "perspectives": settings["perspectives"]}


@mcp.tool()
async def list_article_images(article_id: str, locale: str = "en-US") -> dict[str, Any]:
    """List active and removed article images, including removal reasons."""
    from src.application.service import get_article as application_get_article

    article = await _to_thread(application_get_article, article_id, locale=locale, include_content=False)
    return {"ok": True, "article_id": article_id, "active": article["assets"], "removed": article["removedAssets"]}


@mcp.tool()
async def set_article_image_state(article_id: str, asset_name: str, state: str) -> dict[str, Any]:
    """Remove or restore an image and update the reviewed Markdown deterministically."""
    from src.application.service import set_article_image_state as application_set_image_state

    return await _to_thread(application_set_image_state, article_id, asset_name, state)


@mcp.tool()
async def get_runtime_settings() -> dict[str, Any]:
    """Return masked providers, crawler order, and archive settings."""
    from src.application.service import get_settings

    return {"ok": True, "settings": await _to_thread(get_settings)}


@mcp.tool()
async def update_runtime_settings(settings: dict[str, Any]) -> dict[str, Any]:
    """Persist the same provider, crawler, and archive settings accepted by the web UI."""
    from src.application.service import save_settings

    return {"ok": True, "settings": await _to_thread(save_settings, settings)}


@mcp.tool()
async def activate_ai_provider(provider_name: str) -> dict[str, Any]:
    """Select an existing provider for subsequent text reviews."""
    from src.application.service import get_settings, save_settings

    current = await _to_thread(get_settings)
    settings = await _to_thread(save_settings, current, active_provider=provider_name)
    return {"ok": True, "settings": settings}


@mcp.tool()
async def test_runtime_service(service: str, provider_name: str = "") -> dict[str, Any]:
    """Test AI-provider or Firecrawl connectivity without changing saved settings."""
    from src.application.service import test_service

    return await test_service(service, provider_name=provider_name)


@mcp.tool()
async def start_capture(
    url: str,
    review_mode: str = "ai_then_manual",
    perspective: str = "",
    language: str = "source",
) -> dict[str, Any]:
    """Start a background capture-review workflow and return a pollable job."""
    from src.api.web import start_capture_job

    return await start_capture_job(
        url,
        review_mode=review_mode,
        perspective=perspective or None,
        output_language=language,
    )


@mcp.tool()
async def start_review(article_id: str, perspective: str = "", language: str = "source") -> dict[str, Any]:
    """Start an asynchronous article re-review and return a pollable job."""
    from src.api.web import start_article_review_job

    return await start_article_review_job(
        article_id,
        perspective=perspective or None,
        output_language=language,
    )


@mcp.tool()
async def start_upload(article_id: str, target: str = "siyuan") -> dict[str, Any]:
    """Start an asynchronous upload and return a pollable job."""
    from src.api.web import start_upload_job

    return await start_upload_job(article_id, target=target)


@mcp.tool()
async def start_polish(article_id: str, markdown: str = "") -> dict[str, Any]:
    """Start an asynchronous reflection polish and return a pollable job."""
    from src.api.web import start_polish_job

    return await start_polish_job(
        article_id,
        reflection_markdown=markdown if markdown else None,
    )


@mcp.tool()
async def get_job(job_id: str) -> dict[str, Any]:
    """Poll a background capture, review, upload, or polish job."""
    from src.api.web import get_background_job

    return get_background_job(job_id)


@mcp.tool()
async def list_jobs(kind: str = "all") -> dict[str, Any]:
    """List recent background jobs by kind."""
    from src.api.web import list_background_jobs

    jobs = list_background_jobs(kind=kind)
    return {"ok": True, "kind": kind, "jobs": jobs}


async def _to_thread(function, /, *args, **kwargs):
    return await asyncio.to_thread(function, *args, **kwargs)


# ---------------------------------------------------------------------------
# ASGI application with SSE transport and health endpoint
# ---------------------------------------------------------------------------

def _health_handler(request):
    return JSONResponse({"status": "ok", "service": "noosphere-mcp"})


def create_app() -> Starlette:
    """Return a Starlette ASGI app serving the MCP SSE endpoint and health check."""
    from src.api.web import (
        activate_ai_provider,
        batch_article_trash_action,
        batch_trash_articles,
        create_article_annotation,
        create_capture,
        create_article_review,
        create_article_polish,
        create_collection as create_collection_route,
        delete_article_annotation,
        get_article,
        list_article_annotations,
        get_article_asset,
        get_article_review_job,
        get_polish_job,
        get_job as get_web_job,
        get_removed_article_asset,
        get_pipeline_settings,
        get_settings,
        get_collections,
        get_upload_job,
        list_article_trash,
        list_capture_jobs,
        list_jobs as list_web_jobs,
        list_articles,
        permanently_delete_article,
        restore_article_trash,
        retry_capture_job,
        trash_article,
        update_article,
        update_article_annotation,
        update_article_metadata,
        update_article_image,
        update_article_reflection,
        update_article_collection,
        update_pipeline_settings,
        update_collection as update_collection_route,
        upload_web_article,
        reveal_settings_secret,
        test_settings_service,
        update_settings,
    )

    sse_app = mcp.sse_app()
    routes = [
        Route("/", lambda request: RedirectResponse("/app/"), methods=["GET"]),
        Route("/health", _health_handler, methods=["GET"]),
        Route("/api/v1/articles", list_articles, methods=["GET"]),
        Route("/api/v1/articles/batch-delete", batch_trash_articles, methods=["POST"]),
        Route("/api/v1/trash/articles", list_article_trash, methods=["GET"]),
        Route("/api/v1/trash/articles/batch", batch_article_trash_action, methods=["POST"]),
        Route("/api/v1/trash/articles/{article_id}/restore", restore_article_trash, methods=["POST"]),
        Route("/api/v1/trash/articles/{article_id}", permanently_delete_article, methods=["DELETE"]),
        Route("/api/v1/articles/{article_id}", get_article, methods=["GET"]),
        Route("/api/v1/articles/{article_id}", update_article, methods=["PATCH"]),
        Route("/api/v1/articles/{article_id}/metadata", update_article_metadata, methods=["PATCH"]),
        Route("/api/v1/articles/{article_id}", trash_article, methods=["DELETE"]),
        Route("/api/v1/articles/{article_id}/upload", upload_web_article, methods=["POST"]),
        Route("/api/v1/articles/{article_id}/review", create_article_review, methods=["POST"]),
        Route("/api/v1/articles/{article_id}/reflection", update_article_reflection, methods=["PATCH"]),
        Route("/api/v1/articles/{article_id}/annotations", list_article_annotations, methods=["GET"]),
        Route("/api/v1/articles/{article_id}/annotations", create_article_annotation, methods=["POST"]),
        Route("/api/v1/articles/{article_id}/annotations/{annotation_id}", update_article_annotation, methods=["PATCH"]),
        Route("/api/v1/articles/{article_id}/annotations/{annotation_id}", delete_article_annotation, methods=["DELETE"]),
        Route("/api/v1/articles/{article_id}/polish", create_article_polish, methods=["POST"]),
        Route("/api/v1/articles/{article_id}/assets/{asset_name}", get_article_asset, methods=["GET"]),
        Route("/api/v1/articles/{article_id}/removed/{asset_name}", get_removed_article_asset, methods=["GET"]),
        Route("/api/v1/articles/{article_id}/images/{asset_name}", update_article_image, methods=["PATCH"]),
        Route("/api/v1/articles/{article_id}/collection", update_article_collection, methods=["PATCH"]),
        Route("/api/v1/uploads/{job_id}", get_upload_job, methods=["GET"]),
        Route("/api/v1/reviews/{job_id}", get_article_review_job, methods=["GET"]),
        Route("/api/v1/polish/{job_id}", get_polish_job, methods=["GET"]),
        Route("/api/v1/jobs", list_web_jobs, methods=["GET"]),
        Route("/api/v1/jobs/{job_id}", get_web_job, methods=["GET"]),
        Route("/api/v1/captures", create_capture, methods=["POST"]),
        Route("/api/v1/captures", list_capture_jobs, methods=["GET"]),
        Route("/api/v1/captures/{job_id}/retry", retry_capture_job, methods=["POST"]),
        Route("/api/v1/settings", get_settings, methods=["GET"]),
        Route("/api/v1/settings", update_settings, methods=["PATCH"]),
        Route("/api/v1/settings/active-provider", activate_ai_provider, methods=["PATCH"]),
        Route("/api/v1/settings/secrets/reveal", reveal_settings_secret, methods=["POST"]),
        Route("/api/v1/settings/test", test_settings_service, methods=["POST"]),
        Route("/api/v1/pipeline/settings", get_pipeline_settings, methods=["GET"]),
        Route("/api/v1/pipeline/settings", update_pipeline_settings, methods=["PATCH"]),
        Route("/api/v1/collections", get_collections, methods=["GET"]),
        Route("/api/v1/collections", create_collection_route, methods=["POST"]),
        Route("/api/v1/collections/{collection_id}", update_collection_route, methods=["PATCH"]),
    ]
    frontend_dist = project_root() / "frontend" / "dist"
    if frontend_dist.is_dir():
        routes.append(Mount("/app", app=SPAStaticFiles(directory=frontend_dist, html=True), name="web"))
    else:
        async def frontend_missing(request):
            return JSONResponse(
                {"error": "Web frontend is not built. Run npm run build in frontend/."},
                status_code=503,
            )
        routes.append(Route("/app/{path:path}", frontend_missing, methods=["GET"]))
    routes.append(Mount("/", app=sse_app))
    return Starlette(
        routes=routes,
    )


if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    app = create_app()
    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_PORT", "8080"))
    logger.info("Starting Noosphere MCP server on %s:%s", host, port)
    uvicorn.run(app, host=host, port=port)
