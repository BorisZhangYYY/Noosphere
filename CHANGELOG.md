# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- **Batch extraction**: `extract` command now accepts `--batch FILE` with one URL per line, or a single positional URL. (`src/cli.py`)
- Rich-based progress bars and an extraction summary table for batch mode. (`src/cli.py`)
- `--force` flag for `ai-review` and `upload`; both commands now accept a Markdown file, article directory, or article ID. (`src/cli.py`)
- Upload result tracking: successful uploads record `uploaded` metadata in `manifest.json`. (`src/cli.py`)
- Persistent file-hash cache for image classification results in `.noosphere/image_filter_cache.json`. (`src/core/review/image_filter.py`)

### Changed
- `extract` help text updated to reflect single-URL and batch-URL support.
- `upload` and `ai-review` help text updated to reflect file / directory / article-ID support.
- Image filtering now skips the description Vision API call for images classified as `PROMOTION`, cutting API usage roughly in half for promotional content. (`src/core/review/image_filter.py`)
- Unsupported URL errors now list all supported platforms and their URL patterns. (`src/core/registry.py`)

### Fixed
- Deduplication before extraction: URLs already present in an existing `manifest.json` are skipped unless `--force` is used. (`src/cli.py`, `src/core/paths/output_paths.py`)
- `ai-review` and `upload` skip already-completed work unless `--force` is used. (`src/cli.py`)
- `ai-review` now records **all** files currently in `removed/` in `manifest.json`, not just those moved during the final retry iteration. (`src/pipelines/ai_review.py`)
- `review-images --list` falls back to scanning the `removed/` directory when `manifest.json` lacks a `removed_files` record. (`src/cli.py`)
- `run` command now records the upload result in `manifest.json` just like the standalone `upload` command. (`src/cli.py`)

## [0.1.1] - 2026-06-12

### Added
- **Image Filter**: AI-powered vision analysis to classify downloaded images as RELEVANT or PROMOTION before text rewrite. Promotion images (QR codes, logos, banners, ads) are removed; content images (screenshots, diagrams, photos) are preserved. (`src/core/review/image_filter.py`, `prompts/image_review.md`)
- `generate_vision()` method in `AIClient` supporting both Anthropic and OpenAI vision APIs for image content analysis. (`src/integrations/ai_client.py`)
- `review-images ARTICLE_DIR` CLI command for reviewing, listing, and restoring images removed by AI filtering. Supports `--list`, `--preview` (HTML gallery), `--restore IMAGE`, and `--restore-all`. (`src/cli.py`, `src/core/review/image_filter.py`)

### Changed
- **AI Review Pipeline**: integrated image filtering as a pre-review phase. Before text rewrite, all local images are analyzed by vision AI; the resulting inventory is passed to the rewrite AI so it knows which images to keep or remove. (`src/pipelines/ai_review.py`)
- `download_images()` now generates relative paths from the article directory (`assets/image_xx.webp`) instead of from the `assets/` subdirectory (`image_xx.webp`), ensuring Markdown image references resolve correctly regardless of file location. (`src/integrations/assets.py`)

### Fixed
- `_collect_local_images()` in `image_filter.py` now correctly resolves image paths relative to the `assets/` directory, fixing a bug where image filtering silently found zero images and had no effect.
- AI review pipeline now physically moves identified promotion images to `removed/` and records `removed_files` in `manifest.json`, making them visible to the `review-images` restore CLI. (`src/pipelines/ai_review.py`, `src/core/review/image_filter.py`)

### Architecture
- **Extractor registry**: replaced hardcoded `EXTRACTORS` dict with `@register_extractor` decorator and dynamic discovery. New platforms add a directory + decorator; zero changes to existing code. (`src/core/registry.py`)
- **Upload layer**: introduced `UploadAdapter` ABC with `SiyuanAdapter` implementation and `create_adapter()` factory. `pipelines/upload.py` reduced from 80 lines to 6 lines of pure delegation. (`src/core/upload/`)
- **Image download**: replaced side-effectful `download_markdown_images(markdown_path)` with pure `download_images(markdown, asset_dir)` → `(updated_markdown, result)`. `raw.md` is written once and never mutated. (`src/integrations/assets.py`)
- **Validation rules**: extracted from YAML frontmatter in prompt files instead of hardcoded Python. `resolve_prompt()` returns `(prompt_body, PromptMetadata)` so the AI review pipeline passes metadata to the validator. Prompt and validator stay in sync automatically. (`src/core/review/prompt_metadata.py`)
- **Config cache**: unified caching in `load_config()` module-level cache. All callers see the same `Config` object. Removed `crawler.py` private `_crawler_config_cache`. Added `clear_config_cache()` for tests and hot-reload. (`src/core/config/config.py`)
- **BaseArticleExtractor**: split monolithic `extract()` into `_crawl()` and `_parse()` phase methods. Default web platforms use the default `_parse()`; special platforms (e.g. Xiaoheihe) may override it. (`src/core/base_extractor.py`)

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
- `extract.py`: corrected `download_images` parameter from `assets_root` to `asset_dir`.
- `ai_client.py`: increased default `timeout_seconds` from 300 to 600 and added explicit `sock_read` timeout to prevent hangs on long AI review requests.
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
