# src/core/email_report.py
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.core.paths.paths import Paths, get_paths

"""Email report persistence for shared articles.

Records the result of sending a reviewed article via email, including
recipient, subject, success status, and any error message. Reports are
written to outputs/<article_id>/email_report.json.
"""

@dataclass
class EmailReport:
    article_id: str
    recipient: str
    subject: str
    success: bool
    sent_at: str | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        if self.sent_at is None:
            self.sent_at = datetime.now(timezone.utc).isoformat()


def write_report(article_id: str, report: EmailReport, paths: Paths | None = None) -> Path:
    paths = paths or get_paths()
    paths.ensure_article_dirs(article_id)
    path = paths.article_email_report_path(article_id)
    path.write_text(json.dumps(asdict(report), ensure_ascii=False, indent=2), encoding="utf-8")
    return path