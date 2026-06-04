# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Firecrawl fallback when Crawl4AI fails or throws exceptions, transparent to all extractors.
- Xiaoheihe share URL resolution to canonical `/app/bbs/link/{id}` for Firecrawl fallback.
- `crawler` configuration section with `fallback` and `firecrawl` subsections in `config.json`.
- `extract_title_from_markdown()` helper for title extraction when HTML is unavailable.
- `fallback_used` tracking in `CrawledPage` and `Article.extra`.

### Changed
- Migrated path management to a deer-flow-inspired layered architecture: runtime layer (`src.core.paths`) and application layer (`Paths` class with lazy singleton).
- `crawl_page()` now catches Crawl4AI exceptions and attempts Firecrawl fallback before surfacing errors.
- `BaseArticleExtractor` and `XiaoheiheExtractor` fall back to markdown-based title extraction.

### Fixed
- `XiaoheiheExtractor.handles()` now matches all three configured URL patterns (`bbs/post_share`, `app/bbs/link/`, `api.xiaoheihe.cn`).
- Firecrawl client checks HTTP status with `raise_for_status()` before parsing JSON.
- Firecrawl fallback failure now returns the Firecrawl error page instead of the original Crawl4AI failure.
- `extract_title_from_markdown()` skips lines inside fenced and indented code blocks.
- `firecrawl_enabled()` is now case-insensitive (`"Firecrawl"` works).
- `aiohttp.ClientSession` uses `trust_env=True` to respect `HTTP_PROXY`/`HTTPS_PROXY` env vars.
- `crawl_page()` caches config to avoid re-reading `config.json` from disk on every call.
- `crawl_page()` logs fallback messages to `sys.stderr` instead of `stdout`.
- `XiaoheiheExtractor` falls back to `page.markdown` when HTML-based extraction yields empty content.

## [0.1.0] - 2026-05-22

### Added
- Extract articles from WeChat public accounts, Zhihu Zhuanlan, Xiaoheihe, and X (Twitter).
- Download images locally during extraction, with asset upload support.
- AI review workflow with three stages: rewrite, metadata generation, and pre-upload verification.
- Deterministic system validation for reviewed Markdown (`validate` command).
- One-command full workflow (`run` command): extract → ai-review → upload.
- Upload reviewed Markdown to SiYuan note platform.
- Send reviewed articles as HTML email via SMTP (`email` command).
- Platform marker rules with local rule hygiene checks (`rules-review` command).
- Support for OpenAI, Anthropic, Kimi, and MiniMax AI providers.
