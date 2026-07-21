"""Noosphere MCP server exposing the article pipeline as AI-callable tools."""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
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
async def extract_article(url: str) -> str:
    """Extract an article from *url* and download its images.

    Returns the local article_id that can be passed to review_article or
    upload_article.
    """
    url = _validate_url(url)

    from src.graph.graph import run_extract_graph

    reviewed_path = await run_extract_graph(url)
    article_id = reviewed_path.parent.name
    return f"Extracted article '{article_id}' to {reviewed_path}"


@mcp.tool()
async def review_article(article_id: str) -> str:
    """Run AI copy-editing and validation on an already-extracted article."""
    article_dir = _resolve_article_dir(article_id)
    reviewed_path = article_dir / "reviewed.md"
    if not reviewed_path.exists():
        raise ValueError(f"reviewed.md not found for article: {article_id}")

    from src.graph.graph import run_ai_review_graph

    result: ValidationResult = await run_ai_review_graph(reviewed_path)
    if result.ok:
        return f"Article '{article_id}' reviewed successfully"
    return f"Article '{article_id}' review failed after max attempts: {result.issues}"


@mcp.tool()
async def upload_article(article_id: str, *, target: str = "auto") -> str:
    """Upload a reviewed article to the configured note platform."""
    article_dir = _resolve_article_dir(article_id)
    reviewed_path = article_dir / "reviewed.md"
    if not reviewed_path.exists():
        raise ValueError(f"reviewed.md not found for article: {article_id}")

    from src.graph.graph import run_upload_graph

    result: UploadResult = await run_upload_graph(reviewed_path, target=_validate_upload_target(target))
    return f"Article '{article_id}' uploaded to {result.hpath} (created={result.created})"


@mcp.tool()
async def run_pipeline(url: str, *, auto_confirm: bool = True) -> str:
    """Run the full extract → ai-review → upload pipeline for *url*."""
    url = _validate_url(url)

    from src.graph.graph import run_pipeline_graph

    result: UploadResult = await run_pipeline_graph(url, auto_confirm=auto_confirm)
    return f"Pipeline completed for {url}: uploaded to {result.hpath} (created={result.created})"


# ---------------------------------------------------------------------------
# ASGI application with SSE transport and health endpoint
# ---------------------------------------------------------------------------

def _health_handler(request):
    return JSONResponse({"status": "ok", "service": "noosphere-mcp"})


def create_app() -> Starlette:
    """Return a Starlette ASGI app serving the MCP SSE endpoint and health check."""
    from src.api.web import (
        activate_ai_provider,
        create_capture,
        create_article_review,
        get_article,
        get_article_asset,
        get_article_review_job,
        get_removed_article_asset,
        get_pipeline_settings,
        get_settings,
        get_taxonomy,
        get_upload_job,
        list_capture_jobs,
        list_articles,
        update_article,
        update_article_image,
        update_article_classification,
        update_pipeline_settings,
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
        Route("/api/v1/articles/{article_id}", get_article, methods=["GET"]),
        Route("/api/v1/articles/{article_id}", update_article, methods=["PATCH"]),
        Route("/api/v1/articles/{article_id}/upload", upload_web_article, methods=["POST"]),
        Route("/api/v1/articles/{article_id}/review", create_article_review, methods=["POST"]),
        Route("/api/v1/articles/{article_id}/assets/{asset_name}", get_article_asset, methods=["GET"]),
        Route("/api/v1/articles/{article_id}/removed/{asset_name}", get_removed_article_asset, methods=["GET"]),
        Route("/api/v1/articles/{article_id}/images/{asset_name}", update_article_image, methods=["PATCH"]),
        Route("/api/v1/articles/{article_id}/classification", update_article_classification, methods=["PATCH"]),
        Route("/api/v1/uploads/{job_id}", get_upload_job, methods=["GET"]),
        Route("/api/v1/reviews/{job_id}", get_article_review_job, methods=["GET"]),
        Route("/api/v1/captures", create_capture, methods=["POST"]),
        Route("/api/v1/captures", list_capture_jobs, methods=["GET"]),
        Route("/api/v1/settings", get_settings, methods=["GET"]),
        Route("/api/v1/settings", update_settings, methods=["PATCH"]),
        Route("/api/v1/settings/active-provider", activate_ai_provider, methods=["PATCH"]),
        Route("/api/v1/settings/secrets/reveal", reveal_settings_secret, methods=["POST"]),
        Route("/api/v1/settings/test", test_settings_service, methods=["POST"]),
        Route("/api/v1/pipeline/settings", get_pipeline_settings, methods=["GET"]),
        Route("/api/v1/pipeline/settings", update_pipeline_settings, methods=["PATCH"]),
        Route("/api/v1/taxonomy", get_taxonomy, methods=["GET"]),
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
