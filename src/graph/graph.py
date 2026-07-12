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
from src.core.review.image_filter import (
    ensure_relevant_images_present,
    remove_promotion_images_from_markdown,
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
        "content_type": article.content_type,
        "title": article.title,
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
        platform_label=state["platform"],
        url=state["url"],
        title=state.get("title", ""),
        markdown=state["raw_markdown"],
        content_type=state["content_type"],
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
    assets_dir = state.get("assets_dir")
    if not assets_dir or not Path(assets_dir).exists():
        return {
            "image_filter_result": None,
            "status": "image_filtered",
        }

    result = await filter_images.ainvoke(
        {
            "raw_markdown": state["raw_markdown"],
            "article_title": state.get("title", ""),
            "article_summary": "",
            "assets_dir": assets_dir,
        }
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
    upload_result = await upload_article.ainvoke(
        {"reviewed_path": state["reviewed_path"], "title": None}
    )
    return {
        "upload_result": upload_result,
        "status": "uploaded",
    }


def _export_upload_node(state: ArticleState) -> dict[str, object]:
    """Record upload result in manifest.json for backward compatibility."""
    import json
    from datetime import datetime

    manifest_path = Path(state["reviewed_path"]).with_name("manifest.json")
    if not manifest_path.exists():
        return {}

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        upload_result = state.get("upload_result")
        hpath = upload_result.hpath if upload_result else ""
        manifest["uploaded"] = {
            "platform": state["platform"],
            "hpath": hpath,
            "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except (OSError, json.JSONDecodeError):
        pass

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
    attempts = state.get("attempts", 0) + 1

    edit_result = await edit_article.ainvoke(
        {
            "raw_markdown": state["raw_markdown"],
            "feedback": state.get("feedback", ""),
            "platform": state["platform"],
            "content_type": state["content_type"],
            "image_filter_result": state.get("image_filter_result"),
        }
    )
    reviewed_markdown = edit_result["markdown"]

    image_filter_result = state.get("image_filter_result")
    assets_dir = state.get("assets_dir")
    if image_filter_result is not None and assets_dir:
        if image_filter_result.has_promotions:
            reviewed_markdown, _ = remove_promotion_images_from_markdown(
                reviewed_markdown,
                image_filter_result.get_promotion_paths(),
                assets_dir=Path(assets_dir),
            )
        reviewed_markdown = ensure_relevant_images_present(
            reviewed_markdown,
            image_filter_result.get_relevant_paths(),
            assets_dir=Path(assets_dir) if assets_dir else None,
            raw_markdown=state["raw_markdown"],
        )

    reviewed_path = Path(state["reviewed_path"])
    reviewed_path.parent.mkdir(parents=True, exist_ok=True)
    reviewed_path.write_text(reviewed_markdown, encoding="utf-8")

    return {
        "reviewed_markdown": reviewed_markdown,
        "attempts": attempts,
        "review_model": edit_result.get("model", ""),
        "review_provider": edit_result.get("provider", ""),
        "status": "reviewing",
    }


async def _validate_node(state: ArticleState) -> dict[str, object]:
    """Validate the reviewed Markdown on disk."""
    validation_result = await validate_article.ainvoke(
        {
            "reviewed_path": state["reviewed_path"],
            "platform": state["platform"],
        }
    )

    if validation_result.ok:
        _write_success_report(state)
        return {
            "validation_result": validation_result,
            "status": "reviewed",
            "feedback": "",
        }

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
    """Write the review report when validation succeeds."""
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
