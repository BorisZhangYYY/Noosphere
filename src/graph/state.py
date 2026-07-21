"""LangGraph state definitions for the Noosphere article pipeline."""
from __future__ import annotations

from typing import Literal, TypedDict

from src.core.models.article import UploadResult
from src.core.review.image_filter import ImageFilterResult
from src.core.review.review_validation import ValidationResult


class Asset(TypedDict):
    """A downloaded image asset referenced by the article."""

    filename: str
    original_url: str
    local_path: str


class ArticleState(TypedDict):
    """Shared state passed between graph nodes.

    checkpoint is the primary orchestration store, but outputs/<article_id>/
    remains the protected article workspace under current CLAUDE.md rules.
    """

    article_id: str
    url: str
    platform: str
    platform_label: str
    content_type: str
    title: str

    # Crawl / extract metadata (preserved from the Article extractor)
    article_author: str
    article_published_at: str

    # Workspace paths
    output_dir: str
    reviewed_path: str
    assets_dir: str

    # Crawl / extract outputs
    raw_markdown: str
    assets: list[Asset]
    download_failed: dict[str, str]

    # AI review outputs
    reviewed_markdown: str
    image_filter_result: ImageFilterResult | None
    validation_result: ValidationResult | None
    feedback: str
    attempts: int
    max_attempts: int
    human_approved: bool
    review_model: str
    review_provider: str
    review_perspective: str
    upload_target: str | None

    # Image filter tracking (persisted to manifest on success)
    removed_files: list[str]

    # Upload outputs
    upload_result: UploadResult | None
    upload_platform: str  # adapter.platform_name (target, not source platform)

    # Error / status
    error: str | None
    status: Literal[
        "pending",
        "classified",
        "crawled",
        "assets_downloaded",
        "image_filtered",
        "reviewing",
        "reviewed",
        "classified",
        "validated",
        "approved",
        "uploaded",
        "failed",
    ]
