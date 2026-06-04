# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Pydantic v2 schema models for configuration (`src/core/config/schema.py`).
- AI feedback length limit (`MAX_FEEDBACK_CHARS = 2000`) to prevent context window overflow during review loops.
- Parallel async image download with `asyncio.Semaphore(5)` concurrency limit in `download_markdown_images()`.
- Firecrawl fallback when Crawl4AI fails or throws exceptions, transparent to all extractors.
- Xiaoheihe share URL resolution to canonical `/app/bbs/link/{id}` for Firecrawl fallback.
- `crawler` configuration section with `fallback` and `firecrawl` subsections in `config.json`.
- `extract_title_from_markdown()` helper for title extraction when HTML is unavailable.
- `fallback_used` tracking in `CrawledPage` and `Article.extra`.

### Changed
- Migrated `extractor_registry.py` and `src/core/paths/paths.py` to use the Pydantic `Config` model.
- Migrated path management to a deer-flow-inspired layered architecture: runtime layer (`src.core.paths`) and application layer (`Paths` class with lazy singleton).
- Unified entire pipeline under async/await: `run_ai_review()`, `upload_markdown_file()`, `download_markdown_images()`, and `AIClient.generate_text()` are now async.
- CLI entry point simplified to a single `asyncio.run(_main_async(args))` call; all pipeline commands run in one async context.
- Hardened local image upload logic in `upload_markdown_file`: added basename fallback for SiYuan response keys and warnings for missing uploads; documented the pipeline and helpers.
- `crawl_page()` now catches Crawl4AI exceptions and attempts Firecrawl fallback before surfacing errors.
- `BaseArticleExtractor` and `XiaoheiheExtractor` fall back to markdown-based title extraction.
- Simplified `ai-review` pipeline from 3 AI calls (rewrite + metadata + verification) to 1 AI rewrite call with deterministic machine-validation feedback loop.

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

### Removed
- Removed standalone `validate` CLI command; validation is now internal to `ai-review`.
- Removed `rules-review` CLI command and the entire platform-rules / noise-hints system.
- Removed `review.json` detailed metadata fields (`summary`, `removed_noise`, `preserved_sections`, `formatting_changes`, `image_decisions`, `platform_noise_actions`, `suggested_platform_markers`) and `pre_upload_review`.
- Deleted metadata prompts (`review_metadata.md`, `review_metadata_social.md`) and verification prompts (`pre_upload_review.md`, `pre_upload_review_social.md`).
- Removed all bare-dict config accessor functions (`ai_config()`, `siyuan_config()`, `crawler_config()`, `resolve_ai_api_key()`, `resolve_siyuan_token()`, `configured_output_dir()`, etc.); all configuration access now goes through the Pydantic `Config` model.

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
