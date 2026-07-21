"""LangGraph StateGraph definition for the Noosphere article pipeline."""
from __future__ import annotations

from pathlib import Path

from langgraph.graph import END, START, StateGraph
from langchain_core.runnables import RunnableConfig

from src.core.review.ai_review_data import (
    feedback_from_validation_issues,
    write_completed_review_report,
)
from src.core.config.config import load_config
from src.core.models.manifest import write_article_manifest
from src.core.paths.output_paths import article_output_paths
from src.core.paths import resolve_project_path
from src.core.review.image_filter import (
    ensure_relevant_images_present,
    remove_promotion_images_from_markdown,
    update_manifest_with_image_filter,
)
from src.core.review.review_report import inferred_manifest_path
from src.core.review.review_validation import ValidationResult
from src.graph.state import ArticleState
from src.graph.tools import (
    classify_url,
    crawl_url,
    download_images,
    edit_article,
    filter_images,
    upload_article,
    validate_article,
)


def build_pipeline_graph() -> StateGraph:
    """Return the full extract → ai-review → upload pipeline graph."""
    builder = StateGraph(ArticleState)

    builder.add_node("classify", _classify_node)
    builder.add_node("crawl", _crawl_node)
    builder.add_node("download", _download_node)
    builder.add_node("filter_images", _filter_images_node)
    builder.add_node("ai_review", build_ai_review_subgraph().compile())
    builder.add_node("human_review", _human_review_node)
    builder.add_node("upload", _upload_node)
    builder.add_node("export_upload", _export_upload_node)

    builder.add_edge(START, "classify")
    builder.add_edge("classify", "crawl")
    builder.add_edge("crawl", "download")
    builder.add_edge("download", "filter_images")
    builder.add_edge("filter_images", "ai_review")
    builder.add_conditional_edges(
        "ai_review",
        _after_ai_review_router,
        {
            "human_review": "human_review",
            "failed": END,
        },
    )
    builder.add_conditional_edges(
        "human_review",
        _after_human_review_router,
        {
            "upload": "upload",
            "failed": END,
        },
    )
    builder.add_edge("upload", "export_upload")
    builder.add_edge("export_upload", END)

    return builder


def _classify_node(state: ArticleState) -> dict[str, object]:
    """Classify the URL into a platform key."""
    return {
        "platform": classify_url.invoke({"url": state["url"]}),
        "status": "classified",
    }


async def _crawl_node(state: ArticleState) -> dict[str, object]:
    """Crawl the article and compute output workspace paths."""
    article = await crawl_url.ainvoke({"url": state["url"]})

    config = load_config()
    output_dir = Path(state.get("output_dir") or config.output_dir_path)
    paths = article_output_paths(output_dir, article)

    return {
        "platform": article.platform,
        "platform_label": article.platform_label,
        "content_type": article.content_type,
        "title": article.title,
        "article_author": article.author or "",
        "article_published_at": article.published_at or "",
        "raw_markdown": article.to_review_markdown(),
        "output_dir": str(output_dir),
        "reviewed_path": str(paths.reviewed_path),
        "assets_dir": str(paths.asset_dir),
        "article_id": paths.manifest_path.parent.name,
        "status": "crawled",
    }


async def _download_node(state: ArticleState) -> dict[str, object]:
    """Download images, write raw.md, reviewed.md copy, and manifest.json."""
    import shutil

    asset_dir = Path(state["assets_dir"])
    updated_markdown, assets, failed = await download_images.ainvoke(
        {"raw_markdown": state["raw_markdown"], "asset_dir": str(asset_dir)}
    )
    from src.core.telemetry import emit_event
    if failed:
        await emit_event(
            "download",
            "pipeline.events.assetDownloadIncomplete",
            f"{len(assets)} downloaded, {len(failed)} failed: " + "; ".join(list(failed.values())[:3]),
        )

    raw_path = Path(state["reviewed_path"]).with_name("raw.md")
    reviewed_path = Path(state["reviewed_path"])
    manifest_path = reviewed_path.with_name("manifest.json")
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(updated_markdown, encoding="utf-8")
    shutil.copyfile(raw_path, reviewed_path)

    # Reconstruct Article and ImageDownloadResult for manifest writing.
    from src.core.models.article import Article
    from src.integrations.assets import DownloadedImage, ImageDownloadResult

    article = Article(
        platform=state["platform"],
        platform_label=state.get("platform_label", state["platform"]),
        url=state["url"],
        title=state.get("title", ""),
        markdown=state["raw_markdown"],
        content_type=state["content_type"],
        author=state.get("article_author") or None,
        published_at=state.get("article_published_at") or None,
    )
    image_result = ImageDownloadResult(
        asset_dir=asset_dir,
        downloaded=[
            DownloadedImage(source_url=asset["original_url"], local_path=Path(asset["local_path"]))
            for asset in assets
        ],
        failed=failed,
    )
    from src.core.paths.output_paths import ArticleOutputPaths

    paths = ArticleOutputPaths(
        raw_path=raw_path,
        reviewed_path=reviewed_path,
        asset_dir=asset_dir,
        manifest_path=manifest_path,
    )
    write_article_manifest(article, paths, image_result)

    return {
        "raw_markdown": updated_markdown,
        "assets": assets,
        "download_failed": failed,
        "status": "assets_downloaded",
    }


async def _filter_images_node(state: ArticleState) -> dict[str, object]:
    """Classify local images as RELEVANT or PROMOTION before AI review."""
    from src.core.telemetry import emit_event

    assets_dir = state.get("assets_dir")
    asset_files = [] if not assets_dir else [path for path in Path(assets_dir).glob("**/*") if path.is_file()]
    if not asset_files:
        await emit_event("image_review", "pipeline.events.noImages")
        return {
            "image_filter_result": None,
            "status": "image_filtered",
        }

    await emit_event("image_review", "pipeline.events.imageReviewStarted")
    try:
        result = await filter_images.ainvoke(
            {
                "raw_markdown": state["raw_markdown"],
                "article_title": state.get("title", ""),
                "article_summary": "",
                "assets_dir": assets_dir,
            }
        )
    except Exception as exc:
        await emit_event("image_review", "pipeline.events.imageReviewSkipped", str(exc))
        # Gracefully degrade to unfiltered review, same as legacy pipeline.
        return {
            "image_filter_result": None,
            "status": "image_filtered",
        }

    await emit_event(
        "image_review",
        "pipeline.events.imageReviewCompleted",
        f"{len(result.relevant_images)} relevant, {len(result.promotion_images)} removed",
    )
    return {
        "image_filter_result": result,
        "status": "image_filtered",
    }


def _after_ai_review_router(state: ArticleState) -> str:
    """Route after AI review: human review if valid, otherwise fail."""
    validation_result = state.get("validation_result")
    if isinstance(validation_result, ValidationResult) and validation_result.ok:
        return "human_review"
    return "failed"


def _human_review_node(state: ArticleState, config: RunnableConfig) -> dict[str, object]:
    """Interrupt for human approval before upload."""
    configurable = config.get("configurable", {})
    if configurable.get("auto_confirm") or configurable.get("skip_human_review"):
        return {"human_approved": True, "status": "approved"}

    from langgraph.types import interrupt

    response = interrupt(
        {
            "reviewed_path": state["reviewed_path"],
            "action": "approve_upload",
            "message": "AI review completed. Approve upload?",
        }
    )
    if isinstance(response, dict) and response.get("approved"):
        return {"human_approved": True, "status": "approved"}
    return {"error": "Upload rejected by user", "status": "failed", "human_approved": False}


def _after_human_review_router(state: ArticleState) -> str:
    """Route after human review: upload if approved, otherwise fail."""
    if state.get("human_approved"):
        return "upload"
    return "failed"


async def _upload_node(state: ArticleState) -> dict[str, object]:
    """Upload the reviewed Markdown file to the configured target."""
    result = await upload_article.ainvoke(
        {
            "reviewed_path": state["reviewed_path"],
            "title": None,
            "target": state.get("upload_target"),
        }
    )
    return {
        "upload_result": result["upload_result"],
        "upload_platform": result.get("platform_name", ""),
        "status": "uploaded",
    }


def _export_upload_node(state: ArticleState) -> dict[str, object]:
    """Record upload result in manifest.json for backward compatibility."""
    import json
    import logging
    from datetime import datetime

    logger = logging.getLogger(__name__)

    manifest_path = Path(state["reviewed_path"]).with_name("manifest.json")
    if not manifest_path.exists():
        return {}

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        upload_result = state.get("upload_result")
        hpath = upload_result.hpath if upload_result else ""
        # Use the adapter's platform_name (upload target), not the article source platform.
        upload_platform = state.get("upload_platform") or state["platform"]
        manifest["uploaded"] = {
            "platform": upload_platform,
            "hpath": hpath,
            "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to persist upload result to manifest: %s", exc)

    return {}


def build_ai_review_subgraph() -> StateGraph:
    """Return the edit → validate → retry sub-graph."""
    builder = StateGraph(ArticleState)

    builder.add_node("edit", _edit_node)
    builder.add_node("validate", _validate_node)

    builder.add_edge(START, "edit")
    builder.add_edge("edit", "validate")
    builder.add_conditional_edges(
        "validate",
        _review_router,
        {
            "retry": "edit",
            "done": END,
        },
    )

    return builder


async def _edit_node(state: ArticleState) -> dict[str, object]:
    """Run one AI rewrite attempt and persist the result to disk."""
    from src.core.telemetry import emit_event

    attempts = state.get("attempts", 0) + 1
    await emit_event("ai_review", "pipeline.events.aiReviewStarted", f"attempt {attempts}")

    edit_result = await edit_article.ainvoke(
        {
            "raw_markdown": state["raw_markdown"],
            "feedback": state.get("feedback", ""),
            "platform": state["platform"],
            "content_type": state["content_type"],
            "perspective": state.get("review_perspective", ""),
            "image_filter_result": state.get("image_filter_result"),
        }
    )
    reviewed_markdown = edit_result["markdown"]

    image_filter_result = state.get("image_filter_result")
    assets_dir = state.get("assets_dir")
    removed_files: list[str] = []
    if image_filter_result is not None and assets_dir:
        assets_path = Path(assets_dir)
        if image_filter_result.has_promotions:
            reviewed_markdown, removed_files = remove_promotion_images_from_markdown(
                reviewed_markdown,
                image_filter_result.get_promotion_paths(),
                assets_dir=assets_path,
            )
        reviewed_markdown = ensure_relevant_images_present(
            reviewed_markdown,
            image_filter_result.get_relevant_paths(),
            assets_dir=assets_path if assets_dir else None,
            raw_markdown=state["raw_markdown"],
        )

    reviewed_path = Path(state["reviewed_path"])
    reviewed_path.parent.mkdir(parents=True, exist_ok=True)
    reviewed_path.write_text(reviewed_markdown, encoding="utf-8")
    await emit_event("ai_review", "pipeline.events.aiReviewCompleted", f"{len(reviewed_markdown)} characters")

    return {
        "reviewed_markdown": reviewed_markdown,
        "attempts": attempts,
        "review_model": edit_result.get("model", ""),
        "review_provider": edit_result.get("provider", ""),
        "removed_files": removed_files,
        "status": "reviewing",
    }


async def _validate_node(state: ArticleState) -> dict[str, object]:
    """Validate the reviewed Markdown on disk."""
    from src.core.telemetry import emit_event

    await emit_event("validation", "pipeline.events.validationStarted")
    validation_result = await validate_article.ainvoke(
        {
            "reviewed_path": state["reviewed_path"],
            "platform": state["platform"],
            "perspective": state.get("review_perspective", ""),
        }
    )

    if validation_result.ok:
        _write_success_report(state)
        await emit_event("validation", "pipeline.events.validationPassed")
        return {
            "validation_result": validation_result,
            "status": "reviewed",
            "feedback": "",
        }

    await emit_event(
        "validation",
        "pipeline.events.validationRetry",
        "; ".join(issue.message for issue in validation_result.issues[:6]),
    )
    return {
        "validation_result": validation_result,
        "status": "reviewing",
        "feedback": feedback_from_validation_issues(validation_result.issues),
    }


def _review_router(state: ArticleState) -> str:
    """Route the review sub-graph: retry, finish, or fail after max attempts."""
    validation_result = state.get("validation_result")
    if isinstance(validation_result, ValidationResult) and validation_result.ok:
        return "done"

    attempts = state.get("attempts", 0)
    max_attempts = state.get("max_attempts", 1)
    if attempts >= max_attempts:
        return "done"

    return "retry"


def _write_success_report(state: ArticleState) -> None:
    """Write the review report and persist image filter results when validation succeeds."""
    reviewed_path = Path(state["reviewed_path"])
    manifest_path = inferred_manifest_path(reviewed_path)
    if not manifest_path.exists():
        return

    write_completed_review_report(
        reviewed_path,
        manifest_path,
        model=state.get("review_model", ""),
        provider=state.get("review_provider", ""),
    )

    # Persist image filter results to manifest so review-images CLI can read them.
    _persist_image_filter_to_manifest(state, manifest_path)


def _persist_image_filter_to_manifest(state: ArticleState, manifest_path: Path) -> None:
    """Write image filter result to manifest.json if filtering was performed."""
    image_filter_result = state.get("image_filter_result")
    if image_filter_result is None:
        return

    # Collect removed_files across retries, same as the legacy pipeline.
    assets_dir = state.get("assets_dir")
    removed_files = list(state.get("removed_files") or [])
    if assets_dir:
        removed_dir = Path(assets_dir).parent / "removed"
        if removed_dir.exists():
            assets_parent = Path(assets_dir).parent
            for p in removed_dir.iterdir():
                if p.is_file():
                    rel = str(p.relative_to(assets_parent))
                    if rel not in removed_files:
                        removed_files.append(rel)

    update_manifest_with_image_filter(manifest_path, image_filter_result, removed_files=removed_files)


def build_extract_graph() -> StateGraph:
    """Return the extract-only graph: classify → crawl → download."""
    builder = StateGraph(ArticleState)
    builder.add_node("classify", _classify_node)
    builder.add_node("crawl", _crawl_node)
    builder.add_node("download", _download_node)
    builder.add_edge(START, "classify")
    builder.add_edge("classify", "crawl")
    builder.add_edge("crawl", "download")
    builder.add_edge("download", END)
    return builder


def build_ai_review_graph() -> StateGraph:
    """Return the AI-review-only graph: filter_images → ai_review sub-graph."""
    builder = StateGraph(ArticleState)
    builder.add_node("filter_images", _filter_images_node)
    builder.add_node("ai_review", build_ai_review_subgraph().compile())
    builder.add_edge(START, "filter_images")
    builder.add_edge("filter_images", "ai_review")
    builder.add_edge("ai_review", END)
    return builder


def build_upload_graph() -> StateGraph:
    """Return the upload-only graph: upload → export_upload."""
    builder = StateGraph(ArticleState)
    builder.add_node("upload", _upload_node)
    builder.add_node("export_upload", _export_upload_node)
    builder.add_edge(START, "upload")
    builder.add_edge("upload", "export_upload")
    builder.add_edge("export_upload", END)
    return builder


async def _get_checkpointer():
    """Return a LangGraph checkpointer based on the current configuration.

    The returned tuple is ``(checkpointer, close_callback)`` where *close_callback*
    is an async callable that tears down the underlying connection/pool when called.
    Callers MUST await the close callback after the graph run completes, otherwise
    SQLite connections leak and Postgres pools accumulate idle connections.
    """
    from contextlib import asynccontextmanager
    from langgraph.checkpoint.memory import MemorySaver

    checkpoint_config = load_config().checkpoint
    backend = checkpoint_config.backend.lower()

    if backend == "memory":
        _saver = MemorySaver()

        async def _close():
            pass

        return _saver, _close

    if backend == "sqlite":
        import aiosqlite
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        path = resolve_project_path(Path(checkpoint_config.sqlite_path))
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = await aiosqlite.connect(str(path))
        _saver = AsyncSqliteSaver(conn)

        async def _close():
            await conn.close()

        return _saver, _close

    if backend == "postgres":
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from psycopg_pool import AsyncConnectionPool

        connection_string = checkpoint_config.effective_postgres_connection_string()
        if not connection_string:
            raise ValueError(
                "checkpoint.backend is 'postgres' but neither checkpoint.postgres_connection_string nor DATABASE_URL is set"
            )
        # ``autocommit=True`` is required because ``AsyncPostgresSaver.setup()``
        # issues ``CREATE INDEX CONCURRENTLY``, which cannot run inside a
        # transaction block.
        pool = AsyncConnectionPool(connection_string, open=False, kwargs={"autocommit": True})
        await pool.open()
        _saver = AsyncPostgresSaver(pool)
        await _saver.setup()

        async def _close():
            await pool.close()

        return _saver, _close

    raise ValueError(f"Unsupported checkpoint backend: {checkpoint_config.backend}")


async def _get_checkpointer_ctx():
    """Async context manager for checkpointer lifecycle."""
    saver, close_callback = await _get_checkpointer()
    try:
        yield saver
    finally:
        await close_callback()


def _default_initial_state() -> ArticleState:
    """Return a skeleton ArticleState with default values."""
    return {
        "article_id": "",
        "url": "",
        "platform": "",
        "platform_label": "",
        "content_type": "article",
        "title": "",
        "article_author": "",
        "article_published_at": "",
        "output_dir": "",
        "reviewed_path": "",
        "assets_dir": "",
        "raw_markdown": "",
        "assets": [],
        "download_failed": {},
        "reviewed_markdown": "",
        "image_filter_result": None,
        "validation_result": None,
        "feedback": "",
        "attempts": 0,
        "max_attempts": 1,
        "human_approved": False,
        "review_model": "",
        "review_provider": "",
        "review_perspective": "",
        "upload_target": None,
        "removed_files": [],
        "upload_result": None,
        "upload_platform": "",
        "error": None,
        "status": "pending",
    }


async def run_extract_graph(url: str, output_dir: Path | str | None = None) -> Path:
    """Run the extract graph and return the article reviewed.md path."""
    config = load_config()
    initial_state = _default_initial_state()
    initial_state["url"] = url
    initial_state["output_dir"] = str(output_dir) if output_dir else str(config.output_dir_path)
    initial_state["max_attempts"] = config.ai.max_attempts

    checkpointer, close_cb = await _get_checkpointer()
    try:
        graph = build_extract_graph().compile(checkpointer=checkpointer)
        final_state = await graph.ainvoke(initial_state, config={"configurable": {"thread_id": f"extract:{url}"}})
    finally:
        await close_cb()
    return Path(final_state["reviewed_path"])


async def run_ai_review_graph(
    reviewed_path: Path,
    max_attempts: int | None = None,
    *,
    perspective: str | None = None,
    source_markdown: str | None = None,
) -> ValidationResult:
    """Run the AI review graph starting from an existing reviewed.md path."""
    reviewed_path = Path(reviewed_path)
    manifest_path = reviewed_path.with_name("manifest.json")
    if not manifest_path.exists():
        raise ValueError(f"Manifest not found: {manifest_path}")

    import json

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    article_data = manifest.get("article", {})
    paths_data = manifest.get("paths", {})

    raw_rel = paths_data.get("raw")
    if not raw_rel:
        raise ValueError(f"Raw Markdown path not found in manifest: {manifest_path}")
    raw_path = manifest_path.parent / raw_rel
    raw_markdown = source_markdown if source_markdown is not None else raw_path.read_text(encoding="utf-8")

    assets_dir = manifest_path.parent / paths_data.get("assets", "assets") if paths_data.get("assets") else manifest_path.parent / "assets"

    config = load_config()
    initial_state = _default_initial_state()
    initial_state.update(
        {
            "article_id": manifest.get("article_id", manifest_path.parent.name),
            "url": article_data.get("url", ""),
            "platform": article_data.get("platform", ""),
            "content_type": article_data.get("content_type", "article"),
            "title": article_data.get("title", ""),
            "output_dir": str(manifest_path.parent.parent),
            "reviewed_path": str(reviewed_path),
            "assets_dir": str(assets_dir),
            "raw_markdown": raw_markdown,
            "max_attempts": max_attempts if max_attempts is not None else config.ai.max_attempts,
            "review_perspective": perspective or "",
        }
    )

    checkpointer, close_cb = await _get_checkpointer()
    try:
        graph = build_ai_review_graph().compile(checkpointer=checkpointer)
        final_state = await graph.ainvoke(
            initial_state,
            config={"configurable": {"thread_id": f"ai-review:{reviewed_path}"}},
        )
    finally:
        await close_cb()
    validation_result = final_state.get("validation_result")
    if validation_result is None:
        raise RuntimeError("AI review graph did not produce a validation result")
    return validation_result


async def run_upload_graph(reviewed_path: Path, target: str | None = None) -> UploadResult:
    """Run the upload graph starting from an existing reviewed.md path.

    When a manifest.json exists alongside *reviewed_path*, article metadata
    and the assets directory are read from it.  When no manifest is present a
    standalone Markdown file is uploaded directly (useful with ``--target local``).
    """
    import json

    reviewed_path = Path(reviewed_path)
    manifest_path = reviewed_path.with_name("manifest.json")

    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        article_data = manifest.get("article", {})
        paths_data = manifest.get("paths", {})
        assets_rel = paths_data.get("assets", "assets")
        assets_dir = str(manifest_path.parent / assets_rel)
        initial_state = _default_initial_state()
        initial_state.update(
            {
                "article_id": manifest.get("article_id", manifest_path.parent.name),
                "url": article_data.get("url", ""),
                "platform": article_data.get("platform", ""),
                "platform_label": article_data.get("platform_label", article_data.get("platform", "")),
                "content_type": article_data.get("content_type", "article"),
                "title": article_data.get("title", ""),
                "output_dir": str(manifest_path.parent.parent),
                "reviewed_path": str(reviewed_path),
                "assets_dir": assets_dir,
                "upload_target": target,
            }
        )
    else:
        # Standalone Markdown file — upload without manifest context.
        assets_dir = str(reviewed_path.with_name("assets"))
        initial_state = _default_initial_state()
        initial_state.update(
            {
                "article_id": reviewed_path.parent.name,
                "url": "",
                "platform": "unknown",
                "content_type": "article",
                "title": reviewed_path.stem,
                "output_dir": str(reviewed_path.parent.parent),
                "reviewed_path": str(reviewed_path),
                "assets_dir": assets_dir,
                "upload_target": target,
            }
        )

    checkpointer, close_cb = await _get_checkpointer()
    try:
        graph = build_upload_graph().compile(checkpointer=checkpointer)
        final_state = await graph.ainvoke(
            initial_state,
            config={"configurable": {"thread_id": f"upload:{reviewed_path}"}},
        )
    finally:
        await close_cb()
    upload_result = final_state.get("upload_result")
    if upload_result is None:
        raise RuntimeError("Upload graph did not produce an upload result")
    return upload_result


async def run_pipeline_graph(
    url: str,
    output_dir: Path | str | None = None,
    *,
    auto_confirm: bool = False,
) -> UploadResult:
    """Run the full extract → ai-review → upload pipeline graph.

    Set *auto_confirm* to True to skip the human_review interrupt (useful for
    batch/CI runs or the `run` CLI command).
    """
    config = load_config()
    initial_state = _default_initial_state()
    initial_state["url"] = url
    initial_state["output_dir"] = str(output_dir) if output_dir else str(config.output_dir_path)
    initial_state["max_attempts"] = config.ai.max_attempts

    checkpointer, close_cb = await _get_checkpointer()
    try:
        graph = build_pipeline_graph().compile(checkpointer=checkpointer)
        final_state = await graph.ainvoke(
            initial_state,
            config={
                "configurable": {
                    "thread_id": f"pipeline:{url}",
                    "auto_confirm": auto_confirm,
                }
            },
        )
    finally:
        await close_cb()
    upload_result = final_state.get("upload_result")
    if upload_result is None:
        raise RuntimeError("Pipeline graph did not produce an upload result")
    return upload_result
