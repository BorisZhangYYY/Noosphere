"""Noosphere MCP server exposing the article pipeline as AI-callable tools."""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from urllib.parse import urlparse

from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from src.core.config.config import load_config
from src.core.models.article import UploadResult
from src.core.review.review_validation import ValidationResult

logger = logging.getLogger(__name__)

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
    config = load_config()
    article_dir = config.output_dir_path / article_id
    if not article_dir.exists():
        raise ValueError(f"Article not found: {article_id}")
    return article_dir


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

    result: UploadResult = await run_upload_graph(reviewed_path, target=target if target != "auto" else None)
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
    sse_app = mcp.sse_app()
    return Starlette(
        routes=[
            Route("/health", _health_handler, methods=["GET"]),
            Mount("/", app=sse_app),
        ],
    )


if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    app = create_app()
    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_PORT", "8080"))
    logger.info("Starting Noosphere MCP server on %s:%s", host, port)
    uvicorn.run(app, host=host, port=port)
