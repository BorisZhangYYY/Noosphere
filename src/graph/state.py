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
    content_type: str

    # Crawl / extract outputs
    raw_markdown: str
    assets: list[Asset]

    # AI review outputs
    reviewed_markdown: str
    image_filter_result: ImageFilterResult | None
    validation_result: ValidationResult | None
    feedback: str
    attempts: int

    # Upload outputs
    upload_result: UploadResult | None

    # Error / status
    error: str | None
    status: Literal[
        "pending",
        "classified",
        "crawled",
        "assets_downloaded",
        "image_filtered",
        "reviewed",
        "validated",
        "uploaded",
        "failed",
    ]
