from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from src.core.config import configured_output_dir, load_config


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract one supported article into Markdown, then upload a reviewed Markdown file to SiYuan."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract_parser = subparsers.add_parser("extract", help="Extract one article URL into outputs/raw and outputs/reviewed.")
    extract_parser.add_argument("url", help="Article URL to extract.")

    upload_parser = subparsers.add_parser("upload", help="Upload one reviewed Markdown file to SiYuan.")
    upload_parser.add_argument("file", type=Path, help="Reviewed Markdown file to upload.")

    review_parser = subparsers.add_parser("manual-review", help="Create one draft review report JSON for a reviewed Markdown file.")
    review_parser.add_argument("file", type=Path, help="Reviewed Markdown file to describe.")
    review_parser.add_argument("--manifest", type=Path, help="Extraction manifest path. Defaults to outputs/manifests/ARTICLE.json.")
    review_parser.add_argument("--overwrite", action="store_true", help="Overwrite an existing review report.")

    validate_parser = subparsers.add_parser("validate", help="Validate one reviewed Markdown file before upload.")
    validate_parser.add_argument("file", type=Path, help="Reviewed Markdown file to validate.")

    ai_review_parser = subparsers.add_parser("ai-review", help="Use the configured AI model to rewrite and verify one reviewed Markdown file.")
    ai_review_parser.add_argument("file", type=Path, help="Reviewed Markdown file to rewrite.")

    verify_parser = subparsers.add_parser("verify", help="Run the configured AI pre-upload review for one Markdown file.")
    verify_parser.add_argument("file", type=Path, help="Reviewed Markdown file to verify.")

    run_parser = subparsers.add_parser("run", help="Extract one URL, AI-review it, then upload it to SiYuan.")
    run_parser.add_argument("url", help="Article URL to extract.")

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        if args.command == "extract":
            from src.pipelines.extract import extract_to_output

            path = asyncio.run(extract_to_output(args.url, configured_output_dir(load_config())))
            print(f"Reviewed draft: {path}")
            print("Next: rewrite the reviewed Markdown, create and fill a review report, then validate before upload.")
            return 0

        if args.command == "upload":
            if not args.file.exists():
                print(f"Error: Markdown file not found: {args.file}")
                return 1
            from src.pipelines.upload import upload_markdown_file

            hpath = upload_markdown_file(args.file)
            print(f"Uploaded: {hpath}")
            return 0

        if args.command == "manual-review":
            from src.pipelines.manual_review import create_manual_review_report

            path = create_manual_review_report(args.file, manifest_path=args.manifest, overwrite=args.overwrite)
            print(f"Review report: {path}")
            return 0

        if args.command == "validate":
            from src.core.review_validation import format_validation_issues
            from src.pipelines.validate import validate_reviewed_file

            result = validate_reviewed_file(args.file)
            if result.ok:
                print(f"Valid: {args.file}")
                return 0
            print("Invalid reviewed Markdown:")
            print(format_validation_issues(result.issues))
            return 1

        if args.command == "ai-review":
            from src.core.review_validation import format_validation_issues
            from src.pipelines.ai_review import run_ai_review

            result = run_ai_review(args.file)
            if result.ok:
                print(f"AI reviewed: {result.reviewed_path}")
                return 0
            print(f"AI review failed after {result.attempts} attempt(s).")
            if not result.validation.ok:
                print(format_validation_issues(result.validation.issues))
            if result.verification and result.verification.summary:
                print(result.verification.summary)
            return 1

        if args.command == "verify":
            from src.pipelines.ai_review import verify_reviewed_article

            result = verify_reviewed_article(args.file)
            if result.passed:
                print(f"AI verification passed: {args.file}")
                return 0
            print("AI verification failed:")
            if result.summary:
                print(result.summary)
            for issue in result.issues:
                print(f"- {issue.severity}: {issue.message} {issue.revision_instruction}".strip())
            return 1

        if args.command == "run":
            from src.pipelines.ai_review import run_ai_review
            from src.pipelines.extract import extract_to_output
            from src.pipelines.upload import upload_markdown_file

            reviewed_path = asyncio.run(extract_to_output(args.url, configured_output_dir(load_config())))
            result = run_ai_review(reviewed_path)
            if not result.ok:
                print(f"AI review failed after {result.attempts} attempt(s): {reviewed_path}")
                return 1
            hpath = upload_markdown_file(reviewed_path)
            print(f"Uploaded: {hpath}")
            return 0

    except Exception as exc:  # noqa: BLE001 - CLI should show a concise error.
        print(f"Error: {exc}")
        return 1

    print(f"Error: unsupported command: {args.command}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
