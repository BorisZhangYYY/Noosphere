# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- **Source metadata validation**: `ai-review` now mechanically validates that the blockquote after the H1 title includes `Source` as a Markdown link plus `Platform`, `Author`, `Published`, `Captured`, and `Type` fields. (`src/core/review/review_validation.py`, `prompts/rewrite_article.md`)
- **Main Article heading hierarchy validation**: `ai-review` now rejects H1 or H2 subheadings under `## Main Article`; first-level subheadings must be `###` (H3) or deeper. (`src/core/review/review_validation.py`, `prompts/rewrite_article.md`)
- **TUI**: interactive terminal UI launched via `nsphr tui`. Includes dashboard, extract, AI review, upload, email, image review, pipeline, and prompt management screens. (`src/tui/`)
- **Local archive upload adapter**: writes reviewed Markdown and assets to a dated local folder structure. (`src/core/upload/adapters/local_adapter.py`)
- **`nsphr` console command**: package now exposes the `nsphr` system command via `pyproject.toml`. Install with `pip install -e .` and invoke `nsphr --help`.
- `--target` flag for the `upload` CLI command, supporting `local` or `siyuan` upload targets.
- `local_archive` configuration section in `config.json`.
- **Image Filter**: AI-powered vision analysis to classify downloaded images as RELEVANT or PROMOTION before text rewrite. Promotion images (QR codes, logos, banners, ads) are removed; content images (screenshots, diagrams, photos) are preserved. (`src/core/review/image_filter.py`, `prompts/image_review.md`)
- `generate_vision()` method in `AIClient` supporting both Anthropic and OpenAI vision APIs for image content analysis. (`src/integrations/ai_client.py`)
- `review-images ARTICLE_DIR` CLI command for reviewing, listing, and restoring images removed by AI filtering. Supports `--list`, `--preview` (HTML gallery), `--restore IMAGE`, and `--restore-all`. (`src/cli.py`, `src/core/review/image_filter.py`)

### Changed
- `PromptMetadata` parser now preserves nested dict values in validation rules, enabling richer rule definitions such as field lists and minimum heading levels. (`src/core/review/prompt_metadata.py`)
- `TODO.md`: added configurable output templates with matching mechanical validation to the backlog.
- `create_adapter()` now supports explicit `target` selection and auto-selects between local archive and SiYuan based on configuration.
- **AI Review Pipeline**: integrated image filtering as a pre-review phase. Before text rewrite, all local images are analyzed by vision AI; the resulting inventory is passed to the rewrite AI so it knows which images to keep or remove. (`src/pipelines/ai_review.py`)
- `download_images()` now generates relative paths from the article directory (`assets/image_xx.webp`) instead of from the `assets/` subdirectory (`image_xx.webp`), ensuring Markdown image references resolve correctly regardless of file location. (`src/integrations/assets.py`)
- Extracted `validate` command is now internal to `ai-review`.
- Extracted `rules-review` command and the entire platform-rules / noise-hints system are removed.

### Fixed
- Source metadata validator now tolerates blank lines between the H1 title and the metadata blockquote.
- Main Article heading hierarchy validator now reports the first invalid H2 subheading instead of stopping before it.
- Heading validators now ignore headings inside fenced code blocks, preventing false positives from code examples.
- TUI colour consistency: `markdown_viewer` and `progress_panel` now use `ERROR` and `ACCENT` theme constants instead of hard-coded `[red]` / `[cyan]`.
- Removed unused `status_colour()` helper and its import.
- Windows `open` action in TUI now passes `shell=True` to `explorer`.
- `open_in_editor()` now reports a clear error when `EDITOR` is not found instead of silently failing.
- `LocalAdapter` asset copy now uses `dirs_exist_ok=True` to avoid `FileExistsError` on re-upload.
- `_collect_local_images()` in `image_filter.py` now correctly resolves image paths relative to the `assets/` directory, fixing a bug where image filtering silently found zero images and had no effect.
- AI review pipeline now physically moves identified promotion images to `removed/` and records `removed_files` in `manifest.json`, making them visible to the `review-images` restore CLI. (`src/pipelines/ai_review.py`, `src/core/review/image_filter.py`)

### Architecture
- **Extractor registry**: replaced hardcoded `EXTRACTORS` dict with `@register_extractor` decorator and dynamic discovery. New platforms add a directory + decorator; zero changes to existing code. (`src/core/registry.py`)
- **Upload layer**: introduced `UploadAdapter` ABC with `SiyuanAdapter` implementation and `create_adapter()` factory. `pipelines/upload.py` reduced from 80 lines to 6 lines of pure delegation. (`src/core/upload/`)
- **Image download**: replaced side-effectful `download_markdown_images(markdown_path)` with pure `download_images(markdown, asset_dir)` → `(updated_markdown, result)`. `raw.md` is written once and never mutated. (`src/integrations/assets.py`)
- **Validation rules**: extracted from YAML frontmatter in prompt files instead of hardcoded Python. `resolve_prompt()` returns `(prompt_body, PromptMetadata)` so the AI review pipeline passes metadata to the validator. Prompt and validator stay in sync automatically. (`src/core/review/prompt_metadata.py`)
- **Config cache**: unified caching in `load_config()` module-level cache. All callers see the same `Config` object. Removed `crawler.py` private `_crawler_config_cache`. Added `clear_config_cache()` for tests and hot-reload. (`src/core/config/config.py`)
- **BaseArticleExtractor**: split monolithic `extract()` into `_crawl()` and `_parse()` phase methods. Default web platforms use the default `_parse()`; special platforms (e.g. Xiaoheihe) may override it. (`src/core/base_extractor.py`)

## [0.1.2] - 2026-06-15

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
