# src/core/email_report.py
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.core.config.config import configured_output_dir


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


def write_report(article_id: str, report: EmailReport, output_dir: Path | None = None) -> Path:
    output_dir = output_dir or configured_output_dir({})
    article_dir = output_dir / article_id
    article_dir.mkdir(parents=True, exist_ok=True)
    path = article_dir / "email_report.json"
    path.write_text(json.dumps(asdict(report), ensure_ascii=False, indent=2), encoding="utf-8")
    return path