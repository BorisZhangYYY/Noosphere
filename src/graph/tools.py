"""LangChain tool wrappers for Noosphere pipeline operations.

Each existing operation (crawl, filter images, edit, validate, upload) is wrapped
as a tool so the LangGraph nodes can invoke them uniformly.
"""
from __future__ import annotations

from pathlib import Path

from langchain_core.tools import tool

from src.core.config.config import load_config
from src.core.markdown.links import normalize_markdown_links
from src.core.models.article import Article, UploadResult
from src.core.review.ai_review_data import prepare_rewritten_markdown
from src.core.review.image_filter import (
    ImageFilterResult,
    analyze_images_before_review,
)
from src.core.review.prompt_metadata import parse_prompt
from src.core.review.review_validation import ValidationResult, validate_reviewed_markdown
from src.core.upload.factory import create_adapter
from src.extractor_registry import classify_url as _classify_url, extract_one
from src.integrations.ai_client import AIClient, resolve_ai_settings
from src.integrations.assets import download_images as _download_images
from src.integrations.assets import DownloadedImage
from src.graph.state import Asset


@tool
def classify_url(url: str) -> str:
    """Classify a URL into a registered platform key (e.g. wechat_mp, zhihu)."""
    return _classify_url(url)


@tool
async def crawl_url(url: str) -> Article:
    """Extract an article from a URL using the registered platform extractor.

    Returns an Article dataclass containing raw Markdown and metadata.
    """
    return await extract_one(url)


@tool
async def download_images(raw_markdown: str, asset_dir: str) -> tuple[str, list[Asset]]:
    """Download remote images referenced in *raw_markdown* into *asset_dir*.

    Returns the updated Markdown with local image paths and a list of downloaded
    assets.
    """
    updated_markdown, result = await _download_images(raw_markdown, Path(asset_dir))
    assets = [_downloaded_image_to_asset(image) for image in result.downloaded]
    return updated_markdown, assets


@tool
async def filter_images(
    raw_markdown: str,
    article_title: str,
    article_summary: str,
    assets_dir: str,
) -> ImageFilterResult:
    """Analyze local images and classify them as RELEVANT or PROMOTION.

    Uses the configured AI vision model. Images that cannot be analyzed are
    conservatively marked as relevant.
    """
    config = load_config()
    client = AIClient(resolve_ai_settings(config))
    image_review_prompt = config.ai.resolve_prompt(
        "image_review_prompt", "image_review_prompt_path"
    )[0]
    return await analyze_images_before_review(
        markdown=raw_markdown,
        article_title=article_title,
        article_summary=article_summary,
        assets_dir=Path(assets_dir),
        client=client,
        image_review_prompt=image_review_prompt,
    )


@tool
async def edit_article(
    raw_markdown: str,
    feedback: str,
    platform: str,
    content_type: str,
    image_filter_result: ImageFilterResult | None = None,
) -> str:
    """Perform one AI rewrite attempt for the article.

    Returns the rewritten Markdown. The caller (the review sub-graph) is
    responsible for validation and retry loop management.
    """
    config = load_config()
    settings = resolve_ai_settings(config)
    client = AIClient(settings)

    rewrite_prompt, _ = config.ai.resolve_prompt(
        "rewrite_prompt", "rewrite_prompt_path", platform=platform
    )
    resolved_rewrite_prompt = rewrite_prompt.replace("{model}", settings.model)

    user_prompt = _build_rewrite_user_prompt(
        raw_markdown=raw_markdown,
        feedback=feedback,
        image_filter_result=image_filter_result,
    )

    response = await client.generate_text(resolved_rewrite_prompt, user_prompt)
    return normalize_markdown_links(prepare_rewritten_markdown(response.text, content_type))


@tool
def validate_article(reviewed_path: str, platform: str) -> ValidationResult:
    """Validate a reviewed Markdown file at *reviewed_path*.

    Uses validation rules from the configured rewrite prompt for *platform*.
    """
    config = load_config()
    rewrite_prompt = config.ai.resolve_prompt(
        "rewrite_prompt", "rewrite_prompt_path", platform=platform
    )[0]
    prompt_metadata = parse_prompt(rewrite_prompt).metadata
    return validate_reviewed_markdown(Path(reviewed_path), prompt_metadata)


@tool
async def upload_article(reviewed_path: str, title: str | None = None) -> UploadResult:
    """Upload a reviewed Markdown file to the configured target platform."""
    adapter = create_adapter()
    identifier = await adapter.upload(Path(reviewed_path), title=title)

    # Adapters currently return a platform-specific string identifier.
    # Normalize it into UploadResult for graph state; core fields are filled
    # when available from the adapter return value.
    return UploadResult(
        doc_id=identifier,
        notebook_id="",
        hpath=identifier,
        created=True,
    )


def _downloaded_image_to_asset(image: DownloadedImage) -> Asset:
    return {
        "filename": image.local_path.name,
        "original_url": image.source_url,
        "local_path": str(image.local_path),
    }


def _build_rewrite_user_prompt(
    raw_markdown: str,
    feedback: str,
    image_filter_result: ImageFilterResult | None,
) -> str:
    parts = [
        "Below is the original crawled article. Please read it in full:",
        raw_markdown,
    ]

    if image_filter_result is not None and (
        image_filter_result.relevant_images or image_filter_result.promotion_images
    ):
        parts.append("")
        parts.append(image_filter_result.build_inventory_for_prompt())
        parts.append(
            "IMPORTANT: When rewriting the article, you MUST preserve all images listed under "
            "'Images to KEEP' by keeping their `![...](...)`` markdown references in the output. "
            "You MUST remove all images listed under 'Images to REMOVE'. Do NOT fabricate new image paths."
        )

    if feedback:
        parts.extend([
            "",
            "Previous rewrite failed validation. Please fix the following issues and rewrite the article:",
            feedback,
        ])

    return "\n\n".join(parts)
