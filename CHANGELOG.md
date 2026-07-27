# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- (2026-07-27) Added an empty, user-owned taxonomy foundation: new workspaces no longer receive product-owned categories or profiles, while existing user-created bilingual category paths remain intact across Web, MCP, and CLI.
- (2026-07-27) Added two-level category management to Review Studio, Web API, MCP, and CLI: users can create, rename, describe, retire, and restore their own categories, while deeper nesting and assignment to retired categories are rejected.
- (2026-07-27) Added a dedicated three-column knowledge workspace with a category-and-article tree, article outline, read-only Markdown reader, responsive small-screen layout, and direct navigation to category management, the overview, and the full article workbench.
- (2026-07-27) Added closed-set automatic organization: AI review can select only active user-configured category IDs, persists its reason and confidence, and leaves an article unclassified when no category is a sufficiently strong match.
- (2026-07-27) Added protected article metadata boundaries across Web, MCP, and CLI: article prose is edited separately, trusted source fields are rebuilt canonically for storage and export, and only genuinely missing author or publication values can be filled through controlled inputs.

### Fixed

- (2026-07-27) Restart PostgreSQL automatically with Docker Desktop and the Docker daemon by applying the same `unless-stopped` policy used by the Noosphere service.
- (2026-07-27) Keep provider capability indicators on one line by presenting compact, accessible text/image icons instead of repeated visible labels.
- (2026-07-27) Prefer the current reviewed Markdown heading in article lists and details, preventing a crawler fallback such as `微信公众号文章` from hiding the title recovered during AI review.

## [0.3.1.5] - 2026-07-26

### Added

- Added soft article deletion backed by persistent recycle-bin records, including multi-select deletion, batch restore, permanent removal, and database cleanup for article taxonomy and operation history.
- Added explicit text and image capability badges to AI provider cards so vision-enabled models are distinguishable at a glance.
- Added retry controls for failed capture runs; retries preserve the original URL and pipeline settings while retaining the failed run as history.

### Fixed

- Restyled custom review-perspective metadata fields with the active day/night theme and responsive field layout.
- Canonicalized the complete source metadata block before article display so images cannot split `Captured` from `Type`; restored lead images now appear only below the metadata separator, and blurred removed-image previews no longer dominate the reader.
- Marked failed capture runs as recovered when a later AI re-review of the same article succeeds, while retaining the original failure in the event history.
- Kept article files browsable when PostgreSQL-backed taxonomy or activity metadata is temporarily unavailable instead of returning an unhelpful server error.
- Replaced empty or generic background-job failures with actionable upstream status and error details.

### Changed

- Reorganized project documentation around a concise README and dedicated user guides for installation, CLI, MCP, configuration, and portable data; added core concepts, project structure, FAQ, contribution, license, and support links.
- Clarified repository guidance so development starts by reading the active TODO and completed work moves to the changelog instead of accumulating in the task list.
- Replaced the completed v0.3.1 task inventory with a focused v0.3.2 plan for a bilingual terminology glossary, cross-interface management, and release verification.
- Documented that PostgreSQL is a required service in Docker Compose, how the application degrades when it is unavailable, and how to restart the complete stack.

## [0.3.1] - 2026-07-22

### Added
- Deterministic review-output assembly: models return typed content slots while
  Noosphere owns source metadata, headings, section order, and image placement.
- Independent image-review provider selection with an explicit vision-capable
  declaration; missing vision configuration preserves images and skips safely.
- A dedicated Review Studio for built-in localized perspectives and custom
  review prompt/template configuration.
- Review Studio now presents immutable shared rules separately from each
  perspective and its Markdown template, with recognized-field guidance and
  persistent custom perspective creation and removal.
- Resilient long-article review with bounded concurrent chunks, persistent
  successful-part caching, recursive retry splits, and source-preserving
  fallback for provider timeouts or empty part responses.
- (2026-07-22) Single-language review output can follow the interface, preserve
  the source language, or explicitly target English or Simplified Chinese from
  the web UI, CLI, and MCP tools; switching the UI never rewrites old articles.
- (2026-07-22) Bilingual taxonomy names and descriptions with aliases and
  canonical identity matching, plus lightweight cross-language library search.
- (2026-07-22) Append-only per-article capture, review, re-review, and upload
  history with visible review and upload counts in the inspection rail.
- (2026-07-22) A sticky article outline that follows the current heading and
  scrolls the full article surface to a selected section.
- (2026-07-22) Hierarchical library category selectors with parent totals and
  per-subcategory article counts.
- (2026-07-22) Review-perspective selection for the MCP `review_article` and
  `run_pipeline` tools and the CLI `ai-review` and `run` commands.
- (2026-07-22) Full business-operation parity across web, MCP, and CLI for
  article editing, bilingual taxonomy assignment, image recovery, review
  perspectives, masked runtime settings, provider testing, and job inspection.
- (2026-07-22) Structured MCP responses and asynchronous capture, re-review,
  and upload tools with unified pollable job records.
- (2026-07-22) Machine-readable `--json` output for core CLI workflows and all
  workspace-management commands.

### Changed
- Markdown validation is now a diagnostic instead of a model retry gate; final
  structural correctness comes from deterministic application rendering.
- Article inspection no longer presents the retired mechanical-validation
  status block.
- (2026-07-22) The pipeline now offers AI review with a human upload checkpoint
  or one-click AI review and SiYuan upload; the former capture-only manual mode
  has been removed.
- (2026-07-22) Built-in source-faithful and beginner-friendly perspectives now
  have immutable English and Chinese definitions selected by interface locale.
- (2026-07-22) Article reading now uses one document scroll surface while the
  top toolbar, outline, and inspection rail remain sticky.
- (2026-07-22) Web handlers, MCP tools, and CLI commands now delegate to one
  application service so validation and persisted state cannot drift between
  interfaces.

### Fixed
- WeChat Firecrawl fallback now recovers author/publication metadata, removes
  reader chrome and recommendation/contact tails, and keeps actual article
  images without retaining fake page URLs.
- Reviewed output deterministically restores any source image a text-only model
  omits, while the article API hides stale asset files left by earlier captures.
- Dark-mode reviewed status badges now use a readable high-contrast foreground,
  border, and translucent background.
- (2026-07-22) Desktop article reading now keeps the toolbar, reader frame,
  outline, and inspection rail fixed to the viewport while only the document
  content scrolls; the toolbar no longer adds a blurred background panel.
- (2026-07-22) Active article review jobs are recovered after navigation and
  repeated review requests resume the existing job instead of conflicting.
- (2026-07-22) Read-only article mode now disables classification, AI review,
  and upload controls until editing is enabled.
- (2026-07-22) Fenced code blocks preserve source line breaks and wrap safely
  inside the editor surface.
- Vision-capable provider changes can be reapplied even when the provider is
  already active, and newly marked models immediately become available for the
  independent image-review role.
- Settings dropdowns now float above following sections, the image-review role
  aligns with provider details, and taxonomy counts share one right edge.
- Web taxonomy updates now preserve bilingual names, descriptions, and aliases
  before writing the canonical assignment.

## [0.3.0] - 2026-07-21

### Added
- (2026-07-21) **`noosphere-setup` skill**: a dedicated setup skill that guides
  users through cloning, dependency installation, `config.json` creation, and
  validation. The main `noosphere` skill delegates first-time configuration to
  this skill so the core workflow stays focused on extraction and review.
- (2026-07-21) **Git conventions document**: extracted commit format, changelog
  rules, and push/PR policies into `.project/git-conventions.md`, referenced
  from CLAUDE.md for a leaner agent instruction file.
- (2026-07-21) **CLAUDE.md improvements**: added Testing and Docker Build
  sections with concrete commands for local development and containerized
  deployment.
- (2026-07-21) Reversible inline image review for human editors: removed images
  stay visible in a blurred state, reveal on hover, and can be deleted or
  restored after an explicit confirmation without modifying `raw.md`.
- (2026-07-21) Typed review-output contracts that compose shared constraints,
  one perspective, and a pure Markdown template, then deterministically render
  the model response before LangGraph validation and retry.
- (2026-07-20) Two web review modes: capture-only manual review and the
  recommended AI review followed by human second review.
- (2026-07-20) An editable Pipeline prompt workspace that composes a common
  cleanup prompt, a selected reading perspective, and its output template,
  with built-in source-faithful and novice perspectives.
- (2026-07-20) Automatic two-level article classification with AI-created tag
  descriptions, persistent SQLite/PostgreSQL storage, library filtering, and
  manual tag/subtag reassignment.
- (2026-07-20) Background SiYuan upload jobs with stage progress that continue
  across page navigation, plus clickable kept and AI-removed image inventories.
- (2026-07-20) Vditor instant-rendering Markdown editing for `reviewed.md`,
  including local runtime assets, code rendering, explicit read-only/edit
  modes, draft saves, and manual or repeated SiYuan uploads.
- (2026-07-20) Observable web pipeline events for extraction, image review,
  AI copy-editing, and validation, with streamed reviewed Markdown before the
  human review checkpoint.
- (2026-07-20) A reusable globe brand mark for the sidebar and browser favicon,
  plus denser day/night scenery with additional clouds, wind, birds, stars,
  and shooting stars.
- (2026-07-20) A multi-profile provider workspace with Kimi, MiniMax, Zhipu AI,
  Volcengine, and custom templates, provider-specific visual marks, explicit
  active-profile selection, final endpoint previews, and full URL parsing.
- (2026-07-20) Local-only, no-store secret reveal actions for AI provider keys,
  Firecrawl keys, and SiYuan tokens while keeping normal settings responses masked.
- A React web workspace at `/app/` with responsive Library, article reader,
  Pipeline, Sources, and Settings pages plus a layered animated day/night theme.
- English and Simplified Chinese web localization with browser-language
  detection, a persistent sidebar language switch, localized relative times,
  status labels, forms, empty states, and accessibility text.
- A versioned REST API for article manifests, reviewed Markdown, local assets,
  masked configuration, and asynchronous web-initiated pipeline jobs.
- A frontend build stage in the Docker image, including all web runtime assets
  in the final image without requiring Node.js at runtime.
- A portable single-directory deployment layout under `.noosphere/` for
  configuration, article workspaces, assets, archives, caches, logs, backups,
  and PostgreSQL data.
- Named AI provider profiles with independent Anthropic Messages, OpenAI Chat
  Completions, or OpenAI Responses protocols and real connection tests for AI
  providers and Firecrawl.

### Changed
- (2026-07-21) **README and skill install simplified**: installation now uses
  a single `npx skills add` command with the full GitHub URL. Removed `skill.sh`
  developer helper references from the public README. The `--agent claude-code`
  flag is no longer required.
- (2026-07-21) **`.gitignore` overhaul**: reorganized with clear section headers,
  removed stale patterns, and added coverage for frontend build artifacts,
  Claude Code agent workspaces, logs, and `skills-lock.json`.
- (2026-07-21) **Python requirement bumped to 3.11**: `datetime.UTC` usage in
  `CatalogStore` requires 3.11+. The Docker image already runs Python 3.11.
- (2026-07-21) Article review pages now keep the library/status toolbar fixed
  while the document scrolls, collapse source metadata by default, place
  classification before AI re-review, and use more deliberate action spacing.
- (2026-07-21) The Settings section rail now reveals one compact label at a
  time and responds to pointer movement with a proximity wave without covering
  the settings form; provider connection and activation actions are compact.
- (2026-07-21) Pipeline output templates now contain only Markdown structure
  and content fields; preservation rules live in the common or perspective
  prompts, with legacy profiles upgraded automatically.
- (2026-07-20) Web capture no longer uploads automatically. Upload is an
  explicit background action after the selected human review checkpoint.
- (2026-07-20) Configured provider protocol is fixed to that profile while the
  provider template selector is shown only when creating a new configuration.
- (2026-07-20) Source platforms and crawler engines now use separate,
  consistently sized sections, and the Kimi description names the Moonshot AI
  Open Platform.
- (2026-07-20) The Settings workspace now uses the available content width,
  shows all provider configurations together, and uses themed inline scrolling
  selectors instead of browser-native popup menus.
- Docker Compose now bind-mounts one configurable host data directory and
  forces the checkpoint backend to PostgreSQL while retaining SQLite defaults
  for local development.
- Runtime paths and local archive output resolve beneath `NOOSPHERE_HOME`, and
  `NOOSPHERE_CONFIG` plus `NOOSPHERE_OUTPUT_DIR` select mounted locations.
- The web settings API writes `config.json` atomically with restrictive file
  permissions and preserves existing secrets when secret inputs are blank.
- The settings page now persists all named provider profiles and selects the
  crawler fallback from only the opposite crawler or the disabled state.

### Fixed
- (2026-07-21) Switching the active AI provider now uses a dedicated atomic
  settings endpoint, persists the selected model, bypasses stale HTTP/query
  caches, and confirms the effective provider after a page revisit.
- (2026-07-21) Vditor code-block copy controls now use an explicit clipboard
  path and are no longer swallowed by the instant-render source-toggle guard.
- (2026-07-20) The article editor now uses Vditor WYSIWYG mode with matched
  light/dark content themes, keeps special blocks rendered when clicked, and
  removes editor structure markers that exposed Markdown syntax.
- (2026-07-20) Article source metadata now falls back to the reviewed/raw
  Markdown block when legacy manifests omit author or publication time.
- (2026-07-20) The Vditor surface now follows Noosphere theme colors without
  its default toolbar, white sheet, disabled opacity, or nested dark border.
- (2026-07-20) Settings selectors now open as scrollable popovers above nearby
  fields without changing document flow, provider profiles can be deleted, and
  Firecrawl credentials are hidden when Firecrawl is not selected.
- (2026-07-20) Article metadata preserves line breaks, Markdown code structures
  render correctly, and the SiYuan upload action is no longer permanently
  disabled.
- (2026-07-20) Primary and fallback crawler controls now reserve matching helper
  rows, and complete AI request URLs with query strings no longer receive a
  duplicate protocol path.
- Docker image builds now install Playwright system dependencies as root before
  installing Chromium in the non-root runtime user's writable browser cache.
- MCP article identifiers reject path separators and traversal values before
  resolving an article workspace; upload targets now reject unsupported values.
- Local archive configuration examples now match the supported `enabled` and
  `output_dir` fields.
- Deployment environment overrides now take precedence over persisted
  checkpoint settings, preventing Docker's example SQLite value from masking
  the PostgreSQL service.
- Settings no longer disappear after refresh, and primary/fallback crawler
  selections can no longer resolve to the same implementation.
- Docker builds now retry Playwright system dependency installation when a
  Debian mirror returns a transient download error.

## [0.2.0] - 2026-07-15

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
