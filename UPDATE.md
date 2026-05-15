# UPDATE

This file tracks forward-looking development notes for Noosphere.

Keep `README.md` focused on current user-facing behavior. Use this file for planned work, progress notes, architecture decisions, and implementation details that are not yet stable enough to become product documentation.

## Current Baseline

As of 2026-05-13, the project has:

- Single-article CLI workflow through `python -m src.cli`.
- Supported article sources:
  - WeChat public account articles: `mp.weixin.qq.com/s/...`
  - Zhihu Zhuanlan articles: `zhuanlan.zhihu.com/p/...`
  - Xiaoheihe posts: `xiaoheihe.cn/bbs/post_share?...`
- Article workspaces under `outputs/<article_id>/`.
- Each article workspace may contain:
  - `raw.md`: first-round crawler output
  - `reviewed.md`: editable and uploadable Markdown
  - `manifest.json`: source metadata, output paths, crawl status, image download results, and platform information
  - `noise_hints.json`: platform marker hits used as AI review context
  - `assets/`: downloaded local image assets
  - `review.json`: article-specific AI review metadata written by `ai-review`
- Manual extraction and upload/import endpoints:
  - `python -m src.cli extract URL`
  - `python -m src.cli upload outputs/ARTICLE_ID/reviewed.md`
- One-command workflow through:
  - `python -m src.cli run URL`
- Deterministic system review checks through:
  - `python -m src.cli validate outputs/ARTICLE_ID/reviewed.md`
- AI review workflow through:
  - `python -m src.cli ai-review outputs/ARTICLE_ID/reviewed.md`
- OpenAI and Anthropic provider support for AI review.
- AI rewrite output uses structured JSON with separate `markdown` and `review` fields.
- `review.json` stores only article-specific review metadata and does not embed the full Markdown body.
- `validate` runs common Markdown/report readiness checks for all platforms and dispatches source-platform-specific checks from `src/platforms/<platform>/` when implemented.
- `upload` is a manual endpoint. It does not require `review.json` or deterministic validation to pass before importing the Markdown.
- Runtime credentials, model settings, prompt paths, and upload target settings are read from local `config.json`.
- Markdown normalization for bare prose URLs during AI review.
- `crawl4ai`-backed first-round extraction with source-platform-specific cleaning rules.
- Local image downloading during extraction.
- Markdown-first import flow that preserves Markdown tables where supported by the destination platform.
- Platform marker rules with tracked starter examples in `platform_rules.example/`.
- Local runtime marker rules in gitignored `platform_rules/`.
- Local marker rule hygiene checks through:
  - `python -m src.cli rules-review PLATFORM`
- Modular architecture:
  - `core`
  - `integrations`
  - `pipelines`
  - `platforms`

## Architecture Direction

Noosphere should remain source-platform-aware but destination-platform-agnostic.

Source platforms determine how articles are extracted, cleaned, normalized, and validated. For example, WeChat, Zhihu, and Xiaoheihe may each require different crawler handling, noise rules, marker rules, image handling, and platform-specific validation.

Destination platforms should be handled through upload or export adapters. The current implementation may support a specific note-taking platform first, but the long-term design should allow additional destinations without rewriting the extraction and review pipeline.

The target architecture is:

```text
article URL
  → extraction
  → local Markdown and assets
  → AI review
  → deterministic validation
  → destination adapter
  → note-taking, knowledge-management, or sharing platform
```

This means the core pipeline should produce clean, portable Markdown first. Destination-specific behavior should be isolated in adapters.

Examples of possible destination adapters:

```text
siyuan_adapter
notion_adapter
obsidian_export_adapter
feishu_adapter
email_share_adapter
static_markdown_export_adapter
```

The reviewed Markdown should avoid unnecessary assumptions about the final destination unless the active adapter explicitly requires them.

## Future Developments

### 1. Platform Integration

Support integration with more article platforms and note-taking platforms. The first priority is to make the crawling, cleaning, asset handling, and upload/import workflows work across different platforms.

#### Article Platforms

| Platform | Status |
|----------|--------|
| WeChat public account articles | ✅ |
| Zhihu Zhuanlan | ✅ |
| Xiaoheihe posts | ✅ |
| Xiaohongshu | ⬜ |

#### Note-taking Platforms

| Platform | Status |
|----------|--------|
| SiYuan | ✅ |
| Feishu | ⬜ |

### 2. Sharing Mechanism

Design a sharing mechanism so reviewed articles can be sent to specified recipients after extraction and AI review.

The sharing workflow should support multiple delivery formats while keeping the reviewed article structure consistent across different output targets. The same processed content should be reusable for note-taking platform upload, HTML rendering, email delivery, or link-based sharing.

Planned directions:

- **Markdown sharing**: send the reviewed Markdown content directly to specified recipients.
- **HTML email rendering**: render the reviewed Markdown into HTML and embed it directly inside the email body.
- **Link-based sharing**: generate a shareable link for the reviewed article that recipients can open directly.
- **Recipient configuration**: allow users to configure recipients, sharing templates, and related options.

## Development Log

### 2026-05-07

- Simplified the workflow to one URL per extraction and one reviewed Markdown file per upload.
- Added local image downloading for extracted Markdown.
- Added asset upload behavior for the initial destination platform.
- Split output directories into `raw`, `reviewed`, `assets`, and `manifests`.
- Refactored the codebase into CLI, pipelines, core domain helpers, integrations, and platform modules.
- Moved platform cleaning into `src/platforms/<platform>/cleaning.py` and rule constants into `rules.py`.
- Removed legacy `classifier.py` and legacy platform shim packages.

### 2026-05-09

- Added `validate` for reviewed Markdown readiness checks.
- Made `upload` run review validation by default before writing to the destination platform.
- Added checks for required AI review sections, completed review reports, manifests, and local image paths.
- Added WeChat long-article structure checks that compare raw and reviewed Markdown and require clearer topic headings before upload.
- Added OpenAI and Anthropic AI provider configuration.
- Added `ai-review`, `verify`, and `run` commands for AI rewrite, pre-upload AI verification, revision loop, and one-command upload.
- Moved CLI execution toward config-only credentials and upload targets to reduce command-history leakage.
- Split long review prompts into `prompts/` files and separated AI workflow config from provider credentials.
- Added Markdown link normalization and validation so bare prose URLs do not reach upload/import.

### 2026-05-11

- Grouped extraction outputs into per-article workspaces under `outputs/<article_id>/`.
- Changed AI rewrite output to structured JSON with separate `markdown` and `review` fields so `review.json` records actual article-specific review decisions without embedding the Markdown body.

### 2026-05-12

- Replaced destructive platform cleaning and rule candidate aggregation with external marker rule files, per-article `noise_hints.json`, AI prompt injection for matched markers, and AI-driven suggested marker persistence.
- Kept runtime rules in gitignored `platform_rules/`.
- Kept starter marker examples in `platform_rules.example/`.
- Added `rules-review` for deterministic local marker rule hygiene reports.
- Added safe cleanup for empty, duplicate, and invalid-category marker entries.
- Removed the public `verify` CLI command, keeping AI verification as an internal `ai-review` quality gate.
- Reused the system validation result during `ai-review` verification so one successful review attempt does not run deterministic validation twice.
- Changed `upload` into a manual endpoint that does not require `review.json` or local review validation before importing Markdown.
- Moved WeChat-specific system validation out of `src/core/review_validation.py` into `src/platforms/wechat_mp/review_validation.py`.

### 2026-05-13

- Added system validation to reject article body content before `## AI Summary`, while still allowing the title, source metadata block, and separator before the summary section.
- Added Xiaoheihe post extraction support for `xiaoheihe.cn/bbs/post_share` links.