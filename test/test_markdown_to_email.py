# test/test_markdown_to_email.py
from __future__ import annotations

from src.integrations.markdown_to_email import MarkdownToEmailRenderer


def test_renders_h2_heading():
    md = "## AI Summary\n- point one\n"
    html = MarkdownToEmailRenderer().render(md, assets_dir="")
    assert "<h2" in html and "AI Summary" in html and "</h2>" in html
    assert "<li" in html and "point one" in html and "</li>" in html


def test_strips_article_title_if_in_subject():
    md = "# Actual Title\n\n## AI Summary\n- note"
    html = MarkdownToEmailRenderer().render(md, assets_dir="", subject_title="Actual Title")
    assert html.count("Actual Title") == 0  # title not in body


def test_preserves_hr_separator():
    md = "## AI Summary\n- note\n\n---\n\n## Main Article\nContent"
    html = MarkdownToEmailRenderer().render(md, assets_dir="")
    assert "<hr" in html


def test_inline_styles_no_style_block():
    md = "**bold** and *italic*"
    html = MarkdownToEmailRenderer().render(md, assets_dir="")
    assert "<style>" not in html
    assert "font-weight" in html or "font-style" in html or "<strong>" in html
