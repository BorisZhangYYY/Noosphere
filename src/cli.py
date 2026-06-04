"""
CLI command definitions and entry points. Currently supported:
- extract: Extract an article from a website.
- upload: Upload a Markdown file to Siyuan.
- ai-review: AI-powered rewrite and format validation.
- run: Pipeline of extract → ai-review → upload.
- email: Send Markdown-styled emails via SMTP.
"""
from __future__ import annotations

import argparse
import asyncio
import re
from pathlib import Path

from src.core.config.config import load_config
from src.core.paths.paths import get_paths


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract articles, optionally AI-review them, and upload Markdown to SiYuan."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract_parser = subparsers.add_parser("extract", help="Extract one article URL into outputs/ARTICLE_ID/.")
    extract_parser.add_argument("url", help="Article URL to extract.")

    upload_parser = subparsers.add_parser("upload", help="Upload one Markdown file to SiYuan.")
    upload_parser.add_argument("file", type=Path, help="Markdown file to upload.")

    ai_review_parser = subparsers.add_parser("ai-review", help="Use the configured AI model to rewrite and check one reviewed Markdown file.")
    ai_review_parser.add_argument("file", type=Path, help="Reviewed Markdown file to rewrite.")

    run_parser = subparsers.add_parser("run", help="Extract one URL, AI-review it, then upload it to SiYuan.")
    run_parser.add_argument("url", help="Article URL to extract.")

    email_parser = subparsers.add_parser("email", help="Send reviewed article as HTML email via SMTP.")
    email_parser.add_argument("article_id", help="Article ID to send as email.")
    email_parser.add_argument("--to", required=True, help="Recipient email address (must be in allowed_recipients).")

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        if args.command == "extract":
            from src.pipelines.extract import extract_to_output

            path = asyncio.run(extract_to_output(args.url, get_paths().output_dir))
            print(f"Reviewed draft: {path}")
            print(f"Next: edit manually and upload, or run: python -m src.cli ai-review {path}")
            return 0

        if args.command == "upload":
            if not args.file.exists():
                print(f"Error: Markdown file not found: {args.file}")
                return 1
            from src.pipelines.upload import upload_markdown_file

            hpath = upload_markdown_file(args.file)
            print(f"Uploaded: {hpath}")
            return 0

        if args.command == "ai-review":
            from src.core.review.review_validation import format_validation_issues
            from src.pipelines.ai_review import run_ai_review

            result = run_ai_review(args.file)
            if result.ok:
                print(f"AI reviewed: {result.reviewed_path}")
                return 0
            print(f"AI review failed after {result.attempts} attempt(s).")
            print(format_validation_issues(result.validation.issues))
            return 1

        if args.command == "run":
            from src.pipelines.ai_review import run_ai_review
            from src.pipelines.extract import extract_to_output
            from src.pipelines.upload import upload_markdown_file

            # Pipeline: extract -> ai-review -> upload. Any step failure aborts the chain.
            reviewed_path = asyncio.run(extract_to_output(args.url, get_paths().output_dir))
            result = run_ai_review(reviewed_path)
            if not result.ok:
                print(f"AI review failed after {result.attempts} attempt(s): {reviewed_path}")
                return 1
            hpath = upload_markdown_file(reviewed_path)
            print(f"Uploaded: {hpath}")
            return 0

        if args.command == "email":
            from src.core.email_report import EmailReport, write_report
            from src.integrations.email_adapter import EmailAdapter
            from src.integrations.markdown_to_email import MarkdownToEmailRenderer

            # --- Load SMTP configuration ---
            config = load_config()
            smtp_config = config.get("smtp")
            if not smtp_config:
                print("Error: SMTP not configured in config.json")
                return 1

            # --- Validate recipient against allowlist ---
            allowed = smtp_config.get("allowed_recipients", [])
            if args.to not in allowed:
                print(f"Error: Recipient '{args.to}' is not in allowed_recipients list")
                return 1

            # --- Load reviewed article ---
            paths = get_paths()
            reviewed_md = paths.article_reviewed_path(args.article_id)
            if not reviewed_md.exists():
                print(f"Error: Article not found: {paths.article_dir(args.article_id)}")
                return 1
            markdown_text = reviewed_md.read_text(encoding="utf-8")

            # Derive email subject from the article title (first H1)
            title_match = re.search(r"^#\s+(.+)$", markdown_text, re.MULTILINE)
            article_title = title_match.group(1).strip() if title_match else args.article_id

            assets_dir = paths.article_assets_dir(args.article_id)

            # --- Render Markdown to HTML (images embedded as base64) ---
            renderer = MarkdownToEmailRenderer()
            html_body = renderer.render(markdown_text, assets_dir=assets_dir, subject_title=article_title)

            header_note = f'<p style="margin-bottom: 1em; color: #666; font-size: 0.9em;">[Shared by {smtp_config["sender_name"]} via Noosphere]</p>'
            html_body = header_note + html_body

            subject = f"[Shared by {smtp_config['sender_name']} via Noosphere] {article_title}"

            # --- Send email ---
            adapter = EmailAdapter(
                host=smtp_config["host"],
                port=smtp_config["port"],
                user=smtp_config["user"],
                password=smtp_config["password"],
                sender_name=smtp_config["sender_name"],
                allowed_recipients=allowed,
            )
            result = adapter.send(
                article_id=args.article_id,
                recipient=args.to,
                html_body=html_body,
                subject=subject,
            )

            # --- Persist send report for audit/debugging ---
            report = EmailReport(
                article_id=args.article_id,
                recipient=args.to,
                subject=subject,
                success=result.success,
                error=result.message if not result.success else None,
            )
            report_path = write_report(args.article_id, report, paths)
            print(f"Email report: {report_path}")

            if result.success:
                print(f"Email sent successfully to {args.to}")
                return 0
            print(f"Error: {result.message}")
            return 1

    except Exception as exc:
        # Catch-all: CLI surfaces a concise message instead of a full traceback.
        print(f"Error: {exc}")
        return 1

    print(f"Error: unsupported command: {args.command}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
