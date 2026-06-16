"""Scan outputs/ directory and build article status list."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class ArticleStatus:
    """Lightweight snapshot of one article in outputs/."""
    article_id: str
    title: str
    platform: str
    platform_label: str
    url: str
    dir_path: Path
    status: str  # "extracted" | "reviewed" | "uploaded" | "failed"
    updated_at: str = ""
    uploaded_platform: str = ""
    uploaded_hpath: str = ""


@dataclass
class DashboardSnapshot:
    articles: list[ArticleStatus] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.articles)

    @property
    def extracted(self) -> int:
        return sum(1 for a in self.articles if a.status == "extracted")

    @property
    def reviewed(self) -> int:
        return sum(1 for a in self.articles if a.status == "reviewed")

    @property
    def uploaded(self) -> int:
        return sum(1 for a in self.articles if a.status == "uploaded")

    @property
    def failed(self) -> int:
        return sum(1 for a in self.articles if a.status == "failed")


def scan_articles(output_dir: Path) -> DashboardSnapshot:
    """Walk *output_dir* and build a snapshot of every article found."""
    articles: list[ArticleStatus] = []
    if not output_dir.exists():
        return DashboardSnapshot()

    for manifest_path in sorted(output_dir.rglob("manifest.json"), reverse=True):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        article_dir = manifest_path.parent
        article_meta = manifest.get("article", {})
        title = article_meta.get("title", article_dir.name)
        platform = article_meta.get("platform", "unknown")
        platform_label = article_meta.get("platform_label", platform)
        url = article_meta.get("url", "")

        # Determine status
        uploaded_info = manifest.get("uploaded", {})
        review_path = article_dir / "review.json"
        is_reviewed = False
        updated_at = ""
        if review_path.exists():
            try:
                review = json.loads(review_path.read_text(encoding="utf-8"))
                if review.get("status") == "reviewed":
                    is_reviewed = True
                updated_at = review.get("updated_at", "")
            except (OSError, json.JSONDecodeError):
                pass

        if not updated_at:
            updated_at = article_meta.get("extracted_at", "")

        if uploaded_info.get("hpath"):
            status = "uploaded"
        elif is_reviewed:
            status = "reviewed"
        else:
            # Check for error markers
            has_error = manifest.get("error") or article_meta.get("status") == "error"
            status = "failed" if has_error else "extracted"

        articles.append(ArticleStatus(
            article_id=article_dir.name,
            title=title,
            platform=platform,
            platform_label=platform_label,
            url=url,
            dir_path=article_dir,
            status=status,
            updated_at=updated_at,
            uploaded_platform=uploaded_info.get("platform", ""),
            uploaded_hpath=uploaded_info.get("hpath", ""),
        ))

    # Sort by updated_at descending (most recent first)
    articles.sort(key=lambda a: a.updated_at, reverse=True)
    return DashboardSnapshot(articles=articles)
