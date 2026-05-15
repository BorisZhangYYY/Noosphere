# src/integrations/markdown_to_email.py
from __future__ import annotations

import base64
import re
from pathlib import Path

import markdown


class MarkdownToEmailRenderer:
    """Render Markdown to email-safe HTML with inline styles and embedded images."""

    def render(self, markdown_text: str, assets_dir: str | Path = "", subject_title: str = "") -> str:
        """
        Convert Markdown to email-safe HTML.

        Args:
            markdown_text: The markdown content to render.
            assets_dir: Directory path for resolving local image references.
            subject_title: Article title to strip from body if present (to avoid duplication in email subject).

        Returns:
            Email-safe HTML string with inline styles and embedded images.
        """
        # Strip article title from body if it matches subject_title
        text = self._strip_article_title(markdown_text, subject_title)

        # Convert Markdown to HTML
        html = self._markdown_to_html(text)

        # Process images: embed as base64 or use file:// URI
        html = self._process_images(html, assets_dir)

        # Apply email-safe inline styles
        html = self._apply_inline_styles(html)

        return html

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _strip_article_title(self, text: str, subject_title: str) -> str:
        """Remove the first '# Title' line if it matches subject_title."""
        if not subject_title:
            return text

        # Match first line that is exactly "# <subject_title>" (case-sensitive)
        pattern = r"^#\s+" + re.escape(subject_title) + r"\s*(?:\n|$)"
        return re.sub(pattern, "", text, count=1, flags=re.MULTILINE)

    def _markdown_to_html(self, text: str) -> str:
        """Convert Markdown to HTML with full element support."""
        return markdown.markdown(
            text,
            extensions=[
                "fenced_code",
                "tables",
                "nl2br",
                "attr_list",
            ],
            extension_configs={
                "attr_list": {},
            },
        )

    def _process_images(self, html: str, assets_dir: str | Path) -> str:
        """Process <img> tags: embed as base64 data URI if local file exists, else use file:// URI."""
        assets_path = Path(assets_dir) if assets_dir else Path()

        def replace_image(match: re.Match) -> str:
            src = match.group(1)
            alt = match.group(2) or ""
            title = match.group(3) or ""

            # Skip external URLs and data URIs
            if src.startswith(("http://", "https://", "data:", "file://")):
                return match.group(0)

            image_path = assets_path / src if assets_path else Path(src)

            if image_path.exists() and image_path.is_file():
                try:
                    mime_type, _ = self._guess_mime_type(src)
                    b64_data = base64.b64encode(image_path.read_bytes()).decode("utf-8")
                    return f'<img src="data:{mime_type};base64,{b64_data}" alt="{alt}"{self._title_attr(title)}>'
                except Exception:
                    pass

            # Fallback to file:// URI
            file_uri = image_path.resolve().as_uri()
            return f'<img src="{file_uri}" alt="{alt}"{self._title_attr(title)}>'

        return re.sub(r'<img\s+src="([^"]+)"(?:\s+alt="([^"]*)")?(?:\s+title="([^"]*)")?\s*/?>', replace_image, html)

    @staticmethod
    def _guess_mime_type(src: str) -> tuple[str, str]:
        """Guess MIME type from file extension."""
        import mimetypes
        mime_type: str | None = mimetypes.guess_type(src)[0]
        ext = Path(src).suffix.lower()
        defaults = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".svg": "image/svg+xml",
        }
        return mime_type or defaults.get(ext, "image/png"), ext

    @staticmethod
    def _title_attr(title: str) -> str:
        """Return title attribute string if title is non-empty."""
        return f' title="{title}"' if title else ""

    def _apply_inline_styles(self, html: str) -> str:
        """Apply email-safe inline styles to HTML elements (no <style> block)."""
        # Tables: borderless with clean padding
        html = re.sub(r"<table>", '<table style="border-collapse:collapse;border-spacing:0;width:100%;">', html)
        html = re.sub(r"<th>", '<th style="padding:8px 12px;text-align:left;font-weight:bold;background:#f5f5f5;">', html)
        html = re.sub(r"<td>", '<td style="padding:8px 12px;border-bottom:1px solid #eee;">', html)

        # Headings
        html = re.sub(r"<h2>", '<h2 style="margin:24px 0 12px;font-size:1.5em;font-weight:bold;">', html)
        html = re.sub(r"<h3>", '<h3 style="margin:20px 0 10px;font-size:1.25em;font-weight:bold;">', html)
        html = re.sub(r"<h4>", '<h4 style="margin:16px 0 8px;font-size:1.1em;font-weight:bold;">', html)
        html = re.sub(r"<h5>", '<h5 style="margin:14px 0 6px;font-size:1em;font-weight:bold;">', html)
        html = re.sub(r"<h6>", '<h6 style="margin:12px 0 4px;font-size:0.9em;font-weight:bold;">', html)

        # Horizontal rules
        html = re.sub(r"<hr\s*/?>", '<hr style="border:none;border-top:1px solid #ddd;margin:24px 0;">', html)

        # Blockquotes
        html = re.sub(
            r"<blockquote>",
            '<blockquote style="margin:16px 0;padding:4px 16px;border-left:4px solid #ddd;color:#555;">',
            html,
        )

        # Code blocks (inside <pre><code>)
        html = re.sub(
            r"<pre>",
            '<pre style="margin:12px 0;padding:12px;background:#f5f5f5;border-radius:4px;overflow-x:auto;font-size:14px;line-height:1.5;">',
            html,
        )

        # Inline code
        html = re.sub(
            r"<code>",
            '<code style="font-family:monospace;background:#f0f0f0;padding:2px 6px;border-radius:3px;font-size:0.9em;">',
            html,
        )

        # Lists
        html = re.sub(r"<ul>", '<ul style="margin:12px 0;padding-left:24px;">', html)
        html = re.sub(r"<ol>", '<ol style="margin:12px 0;padding-left:24px;">', html)
        html = re.sub(r"<li>", '<li style="margin:4px 0;">', html)

        # Links: keep inline style
        html = re.sub(
            r"<a\s+href=",
            '<a style="color:#1a73e8;text-decoration:underline;" href=',
            html,
        )

        # Paragraphs
        html = re.sub(r"<p>", '<p style="margin:0 0 12px;">', html)

        # Strong and em
        html = re.sub(r"<strong>", '<strong style="font-weight:bold;">', html)
        html = re.sub(r"<em>", '<em style="font-style:italic;">', html)

        return html
