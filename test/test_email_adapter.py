from __future__ import annotations
import smtplib
from unittest.mock import patch, MagicMock
from src.integrations.email_adapter import EmailAdapter, EmailResult


@patch("smtplib.SMTP")
def test_validate_recipient_whitelist(mock_smtp):
    mock_instance = MagicMock()
    mock_smtp.return_value = mock_instance

    adapter = EmailAdapter(
        host="smtp.example.com",
        port=587,
        user="sender@example.com",
        password="pass",
        sender_name="张三",
        allowed_recipients=["friend@example.com"],
    )
    result = adapter.send(
        article_id="abc123",
        recipient="friend@example.com",
        html_body="<p>Test</p>",
        subject="Test",
    )
    assert result.success is True
    assert "not allowed" not in result.message


def test_reject_recipient_not_in_whitelist():
    adapter = EmailAdapter(
        host="smtp.example.com",
        port=587,
        user="sender@example.com",
        password="pass",
        sender_name="张三",
        allowed_recipients=["friend@example.com"],
    )
    result = adapter.send(
        article_id="abc123",
        recipient="stranger@example.com",
        html_body="<p>Test</p>",
        subject="Test",
    )
    assert result.success is False
    assert "not allowed" in result.message


def test_build_mime_multipart():
    adapter = EmailAdapter(
        host="smtp.example.com",
        port=587,
        user="sender@example.com",
        password="pass",
        sender_name="张三",
        allowed_recipients=["friend@example.com"],
    )
    msg = adapter._build_message(
        recipient="friend@example.com",
        subject="Test Subject",
        html_body="<p>Hello</p>",
        plain_body="Hello",
    )
    msg_str = msg.as_string()
    assert "multipart/alternative" in msg_str
    assert "text/html" in msg_str
    assert "text/plain" in msg_str
