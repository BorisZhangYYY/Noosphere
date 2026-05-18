# test/test_email_report.py
from __future__ import annotations

from src.core.email_report import EmailReport, write_report
import json
from pathlib import Path


def test_email_report_dataclass_fields():
    report = EmailReport(
        article_id="abc123",
        recipient="friend@example.com",
        subject="[Noosphere 用户 张三 向你分享] Test Title",
        success=True,
        sent_at="2026-05-15T10:30:00+08:00",
        error=None,
    )
    assert report.article_id == "abc123"
    assert report.recipient == "friend@example.com"
    assert report.success is True
    assert report.error is None


def test_email_report_with_error():
    report = EmailReport(
        article_id="abc123",
        recipient="friend@example.com",
        subject="[Noosphere 用户 张三 向你分享] Test Title",
        success=False,
        sent_at="2026-05-15T10:30:00+08:00",
        error="SMTP authentication failed",
    )
    assert report.success is False
    assert report.error == "SMTP authentication failed"


def test_write_report(tmp_path):
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    article_dir = outputs / "abc123"
    article_dir.mkdir()

    report = EmailReport(
        article_id="abc123",
        recipient="friend@example.com",
        subject="[Noosphere 用户 张三 向你分享] Test Title",
        success=True,
        sent_at="2026-05-15T10:30:00+08:00",
        error=None,
    )
    write_report("abc123", report, output_dir=outputs)

    report_path = article_dir / "email_report.json"
    assert report_path.exists()
    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert data["article_id"] == "abc123"
    assert data["success"] is True