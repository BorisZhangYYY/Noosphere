# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- **LangGraph migration**: replaced the custom pipeline + direct API-call architecture with a LangGraph `StateGraph`. Includes `src/graph/` package with `ArticleState`, LangChain `@tool` wrappers, AI review sub-graph, full `extract → ai-review → upload` pipeline graph, graph-based CLI/TUI flows, configurable checkpoint persistence (PostgreSQL default in Docker, SQLite still available for local dev), and deprecation warnings for old `src/pipelines/` modules. (`src/graph/state.py`, `src/graph/tools.py`, `src/graph/graph.py`, `src/cli.py`, `src/tui/screens/`, `src/core/config/schema.py`, `tests/test_graph.py`)
- **Source metadata validation**: `ai-review` now mechanically validates that the blockquote after the H1 title includes `Source` as a Markdown link plus `Platform`, `Author`, `Published`, `Captured`, and `Type` fields. (`src/core/review/review_validation.py`, `prompts/edit_article.md`)
- **Main Article heading hierarchy validation**: `ai-review` now rejects H1 or H2 subheadings under `## Main Article`; first-level subheadings must be `###` (H3) or deeper. (`src/core/review/review_validation.py`, `prompts/edit_article.md`)
- **TUI**: interactive terminal UI launched via `nsphr tui`. Includes dashboard, extract, AI review, upload, email, image review, pipeline, and prompt management screens. (`src/tui/`)
- **Local archive upload adapter**: writes reviewed Markdown and assets to a dated local folder structure. (`src/core/upload/adapters/local_adapter.py`)
- **`nsphr` console command**: package now exposes the `nsphr` system command via `pyproject.toml`. Install with `pip install -e .` and invoke `nsphr --help`.
- `--target` flag for the `upload` CLI command, supporting `local` or `siyuan` upload targets.
- `local_archive` configuration section in `config.json`.
- **Image Filter**: AI-powered vision analysis to classify downloaded images as RELEVANT or PROMOTION before text rewrite. Promotion images (QR codes, logos, banners, ads) are removed; content images (screenshots, diagrams, photos) are preserved. (`src/core/review/image_filter.py`, `prompts/image_review.md`)
- `generate_vision()` method in `AIClient` supporting both Anthropic and OpenAI vision APIs for image content analysis. (`src/integrations/ai_client.py`)
- `review-images ARTICLE_DIR` CLI command for reviewing, listing, and restoring images removed by AI filtering. Supports `--list`, `--preview` (HTML gallery), `--restore IMAGE`, and `--restore-all`. (`src/cli.py`, `src/core/review/image_filter.py`)
- **LangGraph runtime parity test**: `tests/test_graph.py` now verifies that `run_ai_review_graph` produces identical `reviewed.md` output to the legacy `run_ai_review` pipeline under identical mocked AI responses. (`tests/test_graph.py`)
- **PostgreSQL checkpoint by default in Docker**: `CheckpointConfig` now defaults to `sqlite` for backward compatibility, but automatically selects `postgres` when `DATABASE_URL` (or `postgres_connection_string`) is present. This lets Docker deployments use Postgres without breaking local development. (`src/core/config/schema.py`, `src/graph/graph.py`, `config.json.example`)
- **Docker Compose deployment**: added `Dockerfile`, `docker-compose.yml`, `.dockerignore`, and `scripts/docker-entrypoint.sh` so the MCP service and Postgres can be started with `docker compose up`. (`Dockerfile`, `docker-compose.yml`, `.dockerignore`, `scripts/docker-entrypoint.sh`)
- **MCP Server**: new `src/mcp/server.py` exposes the Noosphere pipeline as MCP tools (`extract_article`, `review_article`, `upload_article`, `run_pipeline`) over HTTP/SSE, with strict URL validation to prevent malformed requests. (`src/mcp/server.py`, `pyproject.toml`)
- **`nsphr mcp` command**: CLI can now start the MCP server locally for development via `nsphr mcp [--host HOST] [--port PORT]`. (`src/cli.py`)

### Changed
- Updated README.md to reflect the configurable crawler architecture and AI copy-editing workflow, replacing outdated "crawl4ai with firecrawl fallback" and "AI rewrite" language.
- Restructured `skills/noosphere/` to follow Claude Code / OpenClaw skill conventions: added `references/`, `scripts/`, and `assets/`, and rewrote `SKILL.md` with standard sections and clearer trigger conditions.
- Updated `skill.sh` to act as a local development helper (`validate`, `noosphere`, `update`, `help`) and documented the correct standard installation command `npx skills add BorisZhangYYY/Noosphere --skill noosphere --agent claude-code`.
- `PromptMetadata` parser now preserves nested dict values in validation rules, enabling richer rule definitions such as field lists and minimum heading levels. (`src/core/review/prompt_metadata.py`)
- **Configurable crawler priority**: `crawler.primary` and `crawler.fallback` in `config.json` allow swapping the default extraction order without code changes. Set `"primary": "firecrawl"` to use Firecrawl first (fixes WeChat GIF extraction) and fall back to Crawl4AI, or keep `"primary": "crawl4ai"` for the original behavior. (`src/core/config/schema.py`, `src/integrations/crawler.py`)
- **AI Review prompt refactoring**: `prompts/edit_article.md` (formerly `rewrite_article.md`) now instructs the AI to act as a **copy editor** rather than a full rewriter. The AI must preserve the original article structure, section order, and image positions; only remove platform noise, fix formatting, and improve readability. (`prompts/edit_article.md`)
- **Disallowed headings validation**: `ai-review` now mechanically rejects headings such as `Additional Images`, `Appendix`, or `Supplementary Images`. Images must remain in their original narrative positions. (`src/core/review/review_validation.py`)
- **Position-aware image restoration**: `ensure_relevant_images_present()` no longer appends missing images to an `### Additional Images` dumping ground. Instead, it restores them to their original positions based on the raw markdown context, or silently skips them if the original context cannot be matched. (`src/core/review/image_filter.py`, `src/pipelines/ai_review.py`)
- `create_adapter()` now supports explicit `target` selection and auto-selects between local archive and SiYuan based on configuration.
- **AI Review Pipeline**: integrated image filtering as a pre-review phase. Before text rewrite, all local images are analyzed by vision AI; the resulting inventory is passed to the rewrite AI so it knows which images to keep or remove. (`src/pipelines/ai_review.py`)
- `download_images()` now generates relative paths from the article directory (`assets/image_xx.webp`) instead of from the `assets/` subdirectory (`image_xx.webp`), ensuring Markdown image references resolve correctly regardless of file location. (`src/integrations/assets.py`)
- Extracted `validate` command is now internal to `ai-review`.
- Extracted `rules-review` command and the entire platform-rules / noise-hints system are removed.

### Fixed
- **`nsphr mcp` startup**: use `uvicorn.Server(...).serve()` instead of `uvicorn.run()` so the server can be awaited from within the CLI's async main loop without raising "asyncio.run() cannot be called from a running event loop". (`src/cli.py`)
- **LangGraph Postgres checkpoint setup**: pass `kwargs={"autocommit": True}` to `AsyncConnectionPool` so `AsyncPostgresSaver.setup()` can run `CREATE INDEX CONCURRENTLY` outside a transaction block. (`src/graph/graph.py`)
- **MCP upload/run_pipeline tool messages**: `upload_article` and `run_pipeline` no longer try to read a non-existent `platform` attribute from `UploadResult`; they report the uploaded `hpath` and `created` flag. (`src/mcp/server.py`)
- **MCP URL validation**: reject `ftp://` and strip leading/trailing whitespace from URLs before forwarding them to crawlers. (`src/mcp/server.py`)
- **WeChat MP duplicate cover image detection**: `clean_body()` now uses a generic pattern (image-only heading followed by a short publisher heading) instead of a hard-coded list of media names. This correctly removes duplicate cover banners for any publisher, not just a whitelist of known outlets. (`src/platforms/wechat_mp/mp_extractor.py`)
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
- **LangGraph SQLite checkpoint**: `_get_checkpointer()` now returns `AsyncSqliteSaver` (using `aiosqlite`) instead of the sync `SqliteSaver`, so async graph runners (`run_*_graph`) no longer fail with `NotImplementedError` when `checkpoint.backend` is `sqlite`. Added `aiosqlite` as a direct dependency. (`src/graph/graph.py`, `pyproject.toml`)
- **LangGraph — article metadata preservation**: `_crawl_node` now passes `platform_label`, `author`, and `published_at` through graph state so `_download_node` writes a complete `manifest.json`. (`src/graph/graph.py`, `src/graph/state.py`)
- **LangGraph — image filter manifest**: the AI review graph now calls `update_manifest_with_image_filter` on success, so `nsphr review-images --list` can read the filter inventory. (`src/graph/graph.py`)
- **LangGraph — graceful image-filter degradation**: `_filter_images_node` now catches vision AI exceptions and falls back to unfiltered review, matching legacy behaviour. (`src/graph/graph.py`)
- **LangGraph — upload platform recording**: `uploaded.platform` in `manifest.json` now records the upload adapter's `platform_name` instead of the article source platform. (`src/graph/graph.py`, `src/graph/tools.py`)
- **LangGraph — upload adapters return `UploadResult`**: `UploadAdapter.upload()` now returns `UploadResult` with `doc_id`/`notebook_id`/`created` fields preserved from `SiyuanClient`. (`src/core/upload/adapter.py`, adapters)
- **LangGraph — standalone Markdown uploads**: `run_upload_graph` no longer requires `manifest.json` next to the Markdown file. (`src/graph/graph.py`)
- **LangGraph — checkpointer lifecycle**: `_get_checkpointer()` returns a `(saver, close_callback)` tuple; graph runners await the close callback to prevent aiosqlite connection leaks. Postgres backend now uses `AsyncPostgresSaver` + `AsyncConnectionPool`. (`src/graph/graph.py`)
- **LangGraph — surfaced manifest write errors**: `_export_upload_node` logs OSError/JSONDecodeError at WARNING instead of silently passing. (`src/graph/graph.py`)

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
