from __future__ import annotations

import json

from src.core.review_validation import validate_reviewed_markdown


def write_article_dir_manifest_and_report(
    article_dir,
    article_id: str = "article",
    status: str = "reviewed",
    summary: str = "Reviewed and cleaned.",
) -> None:
    (article_dir / "manifest.json").write_text(
        json.dumps({"article_id": article_id, "article": {"title": "Article"}}),
        encoding="utf-8",
    )
    (article_dir / "review.json").write_text(
        json.dumps(
            {
                "article_id": article_id,
                "status": status,
                "review": {
                    "summary": summary,
                    "removed_noise": [],
                    "preserved_sections": [],
                    "formatting_changes": [],
                    "image_decisions": [],
                },
            }
        ),
        encoding="utf-8",
    )


def write_wechat_manifest_and_report(article_dir, article_id: str = "article") -> None:
    (article_dir / "raw.md").write_text(long_wechat_raw_markdown(), encoding="utf-8")
    (article_dir / "manifest.json").write_text(
        json.dumps(
            {
                "article_id": article_id,
                "article": {"title": "Article", "platform": "wechat_mp"},
                "paths": {
                    "raw": "raw.md",
                    "reviewed": "reviewed.md",
                    "manifest": "manifest.json",
                },
            }
        ),
        encoding="utf-8",
    )
    (article_dir / "review.json").write_text(
        json.dumps(
            {
                "article_id": article_id,
                "status": "reviewed",
                "review": {
                    "summary": "Reviewed and restructured.",
                    "removed_noise": ["Removed footer noise."],
                    "preserved_sections": ["Preserved core article sections."],
                    "formatting_changes": ["Added topic headings."],
                    "image_decisions": [],
                },
            }
        ),
        encoding="utf-8",
    )


def long_wechat_raw_markdown() -> str:
    paragraph = "这是一段用于模拟微信公众号长文章的正文，包含融资、产品、用户、团队和行业判断等信息。"
    body = "\n".join([paragraph for _ in range(140)])
    return f"# Title\n\n> 平台：微信公众号\n\n---\n\n## 原始融资标题\n\n{body}\n\n## 团队介绍\n\n{body}\n"


def test_validate_reviewed_markdown_requires_review_structure(tmp_path):
    article_dir = tmp_path / "article"
    article_dir.mkdir()
    reviewed_path = article_dir / "reviewed.md"
    reviewed_path.write_text("# Title\n\nBody\n", encoding="utf-8")

    result = validate_reviewed_markdown(reviewed_path)

    codes = {issue.code for issue in result.issues}
    assert result.ok is False
    assert "missing_ai_summary" in codes
    assert "missing_main_article" in codes
    assert "missing_manifest" in codes
    assert "missing_review_report" in codes


def test_validate_reviewed_markdown_accepts_completed_review(tmp_path):
    article_dir = tmp_path / "article"
    article_dir.mkdir()
    reviewed_path = article_dir / "reviewed.md"
    reviewed_path.write_text(
        "# Title\n\n## AI Summary\n\n- Summary\n\n---\n\n## Main Article\n\nBody\n",
        encoding="utf-8",
    )
    write_article_dir_manifest_and_report(article_dir)

    result = validate_reviewed_markdown(reviewed_path)

    assert result.ok is True


def test_validate_reviewed_markdown_allows_source_block_before_ai_summary(tmp_path):
    article_dir = tmp_path / "article"
    article_dir.mkdir()
    reviewed_path = article_dir / "reviewed.md"
    reviewed_path.write_text(
        "# Title\n\n"
        "> 来源：[https://example.com/article](https://example.com/article)\n"
        "> 平台：微信公众号\n"
        "> 作者：Author\n"
        "> 发布时间：2026年4月28日 11:13\n"
        "> 抓取时间：2026-05-12T19:10:44+08:00\n\n"
        "---\n\n"
        "## AI Summary\n\n"
        "- Summary\n\n"
        "---\n\n"
        "## Main Article\n\n"
        "Body\n",
        encoding="utf-8",
    )
    write_article_dir_manifest_and_report(article_dir)

    result = validate_reviewed_markdown(reviewed_path)

    assert result.ok is True


def test_validate_reviewed_markdown_rejects_body_before_ai_summary(tmp_path):
    article_dir = tmp_path / "article"
    article_dir.mkdir()
    assets_dir = article_dir / "assets"
    assets_dir.mkdir()
    (assets_dir / "image_01.webp").write_bytes(b"image")
    reviewed_path = article_dir / "reviewed.md"
    reviewed_path.write_text(
        "# Title\n\n"
        "> 来源：[https://example.com/article](https://example.com/article)\n"
        "> 平台：微信公众号\n\n"
        "---\n\n"
        "先看一页 AI PPT 效果图，已经追上古法 PPT 了。\n"
        "![Image](assets/image_01.webp)\n\n"
        "## AI Summary\n\n"
        "- Summary\n\n"
        "---\n\n"
        "## Main Article\n\n"
        "Body\n",
        encoding="utf-8",
    )
    write_article_dir_manifest_and_report(article_dir)

    result = validate_reviewed_markdown(reviewed_path)

    assert {issue.code for issue in result.issues} == {"content_before_ai_summary"}


def test_validate_reviewed_markdown_accepts_article_directory_layout(tmp_path):
    article_dir = tmp_path / "article"
    article_dir.mkdir()
    reviewed_path = article_dir / "reviewed.md"
    reviewed_path.write_text(
        "# Title\n\n## AI Summary\n\n- Summary\n\n---\n\n## Main Article\n\nBody\n",
        encoding="utf-8",
    )
    write_article_dir_manifest_and_report(article_dir)

    result = validate_reviewed_markdown(reviewed_path)

    assert result.ok is True


def test_validate_reviewed_markdown_rejects_empty_ai_summary(tmp_path):
    article_dir = tmp_path / "article"
    article_dir.mkdir()
    reviewed_path = article_dir / "reviewed.md"
    reviewed_path.write_text(
        "# Title\n\n## AI Summary\n\n## Main Article\n\nBody\n",
        encoding="utf-8",
    )
    write_article_dir_manifest_and_report(article_dir)

    result = validate_reviewed_markdown(reviewed_path)

    assert {issue.code for issue in result.issues} == {"empty_ai_summary"}


def test_validate_reviewed_markdown_rejects_draft_review_report(tmp_path):
    article_dir = tmp_path / "article"
    article_dir.mkdir()
    reviewed_path = article_dir / "reviewed.md"
    reviewed_path.write_text(
        "# Title\n\n## AI Summary\n\n- Summary\n\n---\n\n## Main Article\n\nBody\n",
        encoding="utf-8",
    )
    write_article_dir_manifest_and_report(article_dir, status="draft", summary="")

    result = validate_reviewed_markdown(reviewed_path)

    assert {issue.code for issue in result.issues} == {"review_report_not_reviewed", "missing_review_summary"}


def test_validate_reviewed_markdown_rejects_remote_images(tmp_path):
    article_dir = tmp_path / "article"
    article_dir.mkdir()
    reviewed_path = article_dir / "reviewed.md"
    reviewed_path.write_text(
        "# Title\n\n## AI Summary\n\n- Summary\n\n---\n\n## Main Article\n\n![alt](https://example.com/a.png)\n",
        encoding="utf-8",
    )
    write_article_dir_manifest_and_report(article_dir)

    result = validate_reviewed_markdown(reviewed_path)

    assert {issue.code for issue in result.issues} == {"remote_image_link"}


def test_validate_reviewed_markdown_rejects_bare_urls(tmp_path):
    article_dir = tmp_path / "article"
    article_dir.mkdir()
    reviewed_path = article_dir / "reviewed.md"
    reviewed_path.write_text(
        "# Title\n\n"
        "## AI Summary\n\n"
        "- Summary\n\n"
        "---\n\n"
        "## Main Article\n\n"
        "- 相关链接：https://example.com/article\n",
        encoding="utf-8",
    )
    write_article_dir_manifest_and_report(article_dir)

    result = validate_reviewed_markdown(reviewed_path)

    assert {issue.code for issue in result.issues} == {"bare_url"}


def test_validate_reviewed_markdown_accepts_markdown_links(tmp_path):
    article_dir = tmp_path / "article"
    article_dir.mkdir()
    reviewed_path = article_dir / "reviewed.md"
    reviewed_path.write_text(
        "# Title\n\n"
        "## AI Summary\n\n"
        "- Summary\n\n"
        "---\n\n"
        "## Main Article\n\n"
        "- [相关链接](https://example.com/article)\n",
        encoding="utf-8",
    )
    write_article_dir_manifest_and_report(article_dir)

    result = validate_reviewed_markdown(reviewed_path)

    assert result.ok is True


def test_validate_reviewed_markdown_rejects_missing_local_images(tmp_path):
    article_dir = tmp_path / "article"
    article_dir.mkdir()
    reviewed_path = article_dir / "reviewed.md"
    reviewed_path.write_text(
        "# Title\n\n## AI Summary\n\n- Summary\n\n---\n\n## Main Article\n\n![alt](../assets/missing.png)\n",
        encoding="utf-8",
    )
    write_article_dir_manifest_and_report(article_dir)

    result = validate_reviewed_markdown(reviewed_path)

    assert {issue.code for issue in result.issues} == {"missing_local_image"}


def test_validate_wechat_long_article_rejects_weak_structure(tmp_path):
    article_dir = tmp_path / "article"
    article_dir.mkdir()
    reviewed_path = article_dir / "reviewed.md"
    reviewed_path.write_text(
        "# Title\n\n"
        "## AI Summary\n\n"
        "- Summary\n\n"
        "---\n\n"
        "## Main Article\n\n"
        "### 原始融资标题\n\n"
        "Body\n\n"
        "### 团队介绍\n\n"
        "Body\n",
        encoding="utf-8",
    )
    write_wechat_manifest_and_report(article_dir)

    result = validate_reviewed_markdown(reviewed_path)

    codes = {issue.code for issue in result.issues}
    assert "weak_article_structure" in codes


def test_validate_wechat_long_article_accepts_restructured_article(tmp_path):
    article_dir = tmp_path / "article"
    article_dir.mkdir()
    reviewed_path = article_dir / "reviewed.md"
    reviewed_path.write_text(
        "# Title\n\n"
        "## AI Summary\n\n"
        "- Summary\n\n"
        "---\n\n"
        "## Main Article\n\n"
        "### 背景与核心事实\n\n"
        "Body\n\n"
        "### 关键机制\n\n"
        "Body\n\n"
        "### 主要案例\n\n"
        "Body\n\n"
        "### 影响分析\n\n"
        "Body\n\n"
        "### 相关角色\n\n"
        "Body\n\n"
        "### 结论与问题\n\n"
        "Body\n",
        encoding="utf-8",
    )
    write_wechat_manifest_and_report(article_dir)

    result = validate_reviewed_markdown(reviewed_path)

    assert result.ok is True
