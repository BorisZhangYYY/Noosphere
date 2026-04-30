from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Callable, Awaitable

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.common_func.article import Article
from src.common_func.siyuan import SiyuanClient, upload_report_record
from src.wechat_mp import extractor as wechat_mp
from src.zhihu_zhuanlan import extractor as zhihu_zhuanlan


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO_ROOT / "config.json"
DEFAULT_REPORT = REPO_ROOT / "outputs/p0_article_ingest_report.json"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "outputs"

Extractor = Callable[[str], Awaitable[Article]]

EXTRACTORS: dict[str, tuple[Callable[[str], bool], Extractor]] = {
    "wechat_mp": (wechat_mp.handles, wechat_mp.extract),
    "zhihu_zhuanlan": (zhihu_zhuanlan.handles, zhihu_zhuanlan.extract),
}


def load_config(path: Path = DEFAULT_CONFIG) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def platform_config(config: dict, platform: str) -> dict:
    value = config.get(platform, {})
    return value if isinstance(value, dict) else {}


def siyuan_config(config: dict) -> dict:
    value = config.get("siyuan", {})
    return value if isinstance(value, dict) else {}


def safe_filename(text: str, fallback: str = "item", max_len: int = 80) -> str:
    cleaned = text.strip()
    for char in ["/", "\\", ":", "*", "?", "\"", "<", ">", "|"]:
        cleaned = cleaned.replace(char, "-")
    cleaned = " ".join(cleaned.split())
    cleaned = cleaned.strip(" .-_")
    if not cleaned:
        cleaned = fallback
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip(" .-_")
    return cleaned or fallback


def article_output_path(output_dir: Path, article: Article, index: int) -> Path:
    title_part = safe_filename(article.title, fallback=article.platform)
    digest = hashlib.sha1(article.url.encode("utf-8")).hexdigest()[:8]
    filename = f"{index:02d}_{article.platform}_{title_part}_{digest}.md"
    return output_dir / filename


def write_article_output(output_dir: Path, article: Article, index: int) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = article_output_path(output_dir, article, index)
    path.write_text(article.to_siyuan_markdown(), encoding="utf-8")
    return path


def classify_url(url: str, config: dict | None = None) -> str:
    config = config or load_config()
    for platform, platform_config in config.items():
        for pattern in platform_config.get("url_patterns", []):
            if pattern in url:
                return platform

    for platform, (handles, _) in EXTRACTORS.items():
        if handles(url):
            return platform
    raise ValueError(f"Unsupported URL for P0: {url}")


async def extract_one(url: str, config: dict | None = None) -> Article:
    platform = classify_url(url, config)
    _, extractor = EXTRACTORS[platform]
    return await extractor(url)


async def run(
    urls: list[str],
    parent_id: str | None,
    api_base: str,
    dry_run: bool,
    upload: bool,
    output_dir: Path,
) -> list[dict]:
    config = load_config()
    sconfig = siyuan_config(config)
    resolved_api_base = api_base or sconfig.get("api_base", "http://127.0.0.1:6806")
    resolved_parent_id = parent_id or sconfig.get("default_parent_id") or None
    token_env = sconfig.get("token_env", "SIYUAN_TOKEN")
    client = None if dry_run or not upload or not resolved_parent_id else SiyuanClient(api_base=resolved_api_base, token_env=token_env)
    records = []

    for index, url in enumerate(urls, 1):
        try:
            article = await extract_one(url, config)
            local_path = write_article_output(output_dir, article, index)
            if client and resolved_parent_id:
                upload = client.upload_article_under_parent(article, resolved_parent_id)
                record = upload_report_record(article, upload)
                record["local_path"] = str(local_path)
                records.append(record)
            else:
                records.append({"ok": True, "article": asdict(article), "upload": None, "error": None, "local_path": str(local_path)})
        except Exception as exc:  # noqa: BLE001 - batch mode should report every URL.
            records.append({"ok": False, "url": url, "error": str(exc), "article": None, "upload": None, "local_path": None})
    return records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="P0: extract WeChat MP / Zhihu Zhuanlan articles and write Markdown outputs, with optional SiYuan upload.")
    parser.add_argument("urls", nargs="+", help="Article URLs to process.")
    parser.add_argument("--parent-id", help="SiYuan target notebook ID or parent document block ID when --upload is enabled.")
    parser.add_argument("--api-base", default="")
    parser.add_argument("--dry-run", action="store_true", help="Extract only; do not call SiYuan upload APIs.")
    parser.add_argument("--upload", action="store_true", help="Also upload the extracted article into SiYuan.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Directory for local Markdown outputs.")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    records = asyncio.run(run(args.urls, args.parent_id, args.api_base, args.dry_run, args.upload, args.output_dir))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

    ok_count = sum(1 for record in records if record["ok"])
    print(f"Processed {len(records)} URL(s): ok={ok_count}, failed={len(records) - ok_count}")
    print(f"Report: {args.report}")
    for record in records:
        if record["ok"]:
            article = record["article"]
            upload = record["upload"]
            suffix = f" -> {upload['hpath']}" if upload else ""
            local_path = record.get("local_path") or ""
            local_suffix = f" [{local_path}]" if local_path else ""
            print(f"- OK [{article['platform']}] {article['title']}{local_suffix}{suffix}")
        else:
            print(f"- FAIL {record.get('url')}: {record['error']}")
    return 0 if ok_count == len(records) else 1


if __name__ == "__main__":
    raise SystemExit(main())
