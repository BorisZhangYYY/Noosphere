from __future__ import annotations

import smtplib
import re
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from pathlib import Path


@dataclass
class EmailResult:
    success: bool
    message: str
    details: dict


class EmailAdapter:
    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        sender_name: str,
        allowed_recipients: list[str],
    ):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.sender_name = sender_name
        self.allowed_recipients = allowed_recipients

    def send(
        self,
        article_id: str,
        recipient: str,
        html_body: str,
        subject: str,
        plain_body: str = "",
        attachments: list[Path] | None = None,
    ) -> EmailResult:
        # Validate recipient against whitelist
        if recipient not in self.allowed_recipients:
            return EmailResult(
                success=False,
                message=f"Recipient '{recipient}' is not allowed. Rejection reason: not in recipient whitelist.",
                details={"article_id": article_id, "recipient": recipient},
            )

        # Build MIME message
        plain = plain_body or self._strip_html(html_body)
        msg = self._build_message(recipient, subject, html_body, plain)

        # Attach inline images if provided
        if attachments:
            self._attach_inline_images(msg, attachments)

        # Send via SMTP
        try:
            server = smtplib.SMTP(self.host, self.port, timeout=30)
            try:
                server.starttls()
            except smtplib.SMTPNotSupportedError:
                pass  # Server doesn't support STARTTLS, continue without it
            server.login(self.user, self.password)

            from_addr = f"{self.sender_name} <{self.user}>"
            server.sendmail(from_addr, [recipient], msg.as_string())

            # Set success details before quit to avoid issues
            server.quit()
            return EmailResult(
                success=True,
                message="Email sent successfully",
                details={"article_id": article_id, "recipient": recipient},
            )
        except Exception as e:
            return EmailResult(
                success=False,
                message=f"Failed to send email: {str(e)}",
                details={"article_id": article_id, "recipient": recipient},
            )

    def _build_message(
        self,
        recipient: str,
        subject: str,
        html_body: str,
        plain_body: str,
    ) -> MIMEMultipart:
        msg = MIMEMultipart("alternative")
        msg["From"] = f"{self.sender_name} <{self.user}>"
        msg["To"] = recipient
        msg["Subject"] = subject

        # Add plain text part
        if plain_body:
            text_part = MIMEText(plain_body, "plain")
            msg.attach(text_part)

        # Add HTML part
        html_part = MIMEText(html_body, "html")
        msg.attach(html_part)

        return msg

    def _attach_inline_images(
        self, msg: MIMEMultipart, attachments: list[Path]
    ) -> None:
        for img_path in attachments:
            if not img_path.exists():
                continue
            with open(img_path, "rb") as f:
                img_data = f.read()
            image = MIMEImage(img_data)
            image.add_header("Content-ID", f"<{img_path.stem}>")
            image.add_header("Content-Disposition", "inline")
            msg.attach(image)

    def _strip_html(self, html: str) -> str:
        # Remove HTML tags
        text = re.sub(r"<[^>]+>", "", html)
        # Decode common HTML entities
        text = text.replace("&nbsp;", " ")
        text = text.replace("&lt;", "<")
        text = text.replace("&gt;", ">")
        text = text.replace("&amp;", "&")
        text = text.replace("&quot;", '"')
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text)
        return text.strip()
