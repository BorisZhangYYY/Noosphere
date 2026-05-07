from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from src.core.config import DEFAULT_OUTPUT_DIR


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract one supported article into Markdown, then upload a reviewed Markdown file to SiYuan."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract_parser = subparsers.add_parser("extract", help="Extract one article URL into outputs/raw and outputs/reviewed.")
    extract_parser.add_argument("url", help="Article URL to extract.")
    extract_parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Directory for extracted Markdown.")

    upload_parser = subparsers.add_parser("upload", help="Upload one reviewed Markdown file to SiYuan.")
    upload_parser.add_argument("file", type=Path, help="Reviewed Markdown file to upload.")
    upload_parser.add_argument("--parent-id", help="SiYuan target notebook ID or parent document block ID.")
    upload_parser.add_argument("--api-base", default="", help="SiYuan API base URL.")
    upload_parser.add_argument("--title", help="Override the document title inferred from the first H1 or filename.")

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        if args.command == "extract":
            from src.pipelines.extract import extract_to_output

            path = asyncio.run(extract_to_output(args.url, args.output_dir))
            print(f"Reviewed draft: {path}")
            print("Next: review and edit this Markdown file, then run `python src/classifier.py upload FILE`.")
            return 0

        if args.command == "upload":
            if not args.file.exists():
                print(f"Error: Markdown file not found: {args.file}")
                return 1
            from src.pipelines.upload import upload_markdown_file

            hpath = upload_markdown_file(args.file, args.parent_id, args.api_base, args.title)
            print(f"Uploaded: {hpath}")
            return 0

    except Exception as exc:  # noqa: BLE001 - CLI should show a concise error.
        print(f"Error: {exc}")
        return 1

    print(f"Error: unsupported command: {args.command}")
    return 1
