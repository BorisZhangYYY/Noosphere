# UPDATE

This file tracks forward-looking development notes for Noosphere. Keep README focused on current user-facing behavior, and use this file for planned work, progress notes, and implementation decisions that are not yet product documentation.

## Current Baseline

As of 2026-05-12, the project has:

- Single-article CLI workflow through `python -m src.cli`.
- Supported sources: WeChat Official Account articles and Zhihu Zhuanlan articles.
- Article workspaces under `outputs/<article_id>/` containing `raw.md`, `reviewed.md`, `manifest.json`, `noise_hints.json`, and `assets/`; `review.json` is written by manual or AI review.
- Manual extraction and upload endpoints through `python -m src.cli extract` and `python -m src.cli upload`; these remain available as unrestricted fallback operations.
- Draft review reports through `python -m src.cli manual-review`.
- System review checks through `python -m src.cli validate`; common checks run for all platforms, with platform-specific checks where implemented.
- AI review through `python -m src.cli ai-review` with OpenAI or Anthropic endpoints, including internal validation and AI verification.
- One-command extract, AI review, and upload through `python -m src.cli run`.
- Credentials, model settings, prompts, SiYuan API settings, and upload targets are read from local `config.json`; AI workflow settings and provider settings are stored separately.
- Markdown normalization for bare prose URLs during AI review.
- crawl4ai-backed first-round extraction with platform-specific cleaning rules.
- Local image downloading during extraction and SiYuan asset upload during import.
- Markdown-first SiYuan upload that preserves Markdown tables.
- Platform marker rules with tracked examples in `platform_rules.example/` and local, gitignored runtime growth in `platform_rules/`.
- Local marker rule hygiene checks through `python -m src.cli rules-review PLATFORM`.
- Modular architecture: `core`, `integrations`, `pipelines`, and `platforms`.

## Future Developments

- **Rule Promotion**: Review and refine platform marker granularity as local `platform_rules/` files grow.


## Development Log

### 2026-05-07

- Simplified the workflow to one URL per extraction and one reviewed Markdown file per upload.
- Added local image downloading for extracted Markdown and SiYuan asset upload for reviewed Markdown.
- Split output directories into `raw`, `reviewed`, `assets`, and `manifests`.
- Refactored the codebase into CLI, pipelines, core domain helpers, integrations, and platform modules.
- Moved platform cleaning into `src/platforms/<platform>/cleaning.py` and rule constants into `rules.py`.
- Removed legacy `classifier.py` and legacy platform shim packages.
- Added `manual-review` for draft structured review reports linked to extraction manifests.

### 2026-05-09

- Added `validate` for reviewed Markdown readiness checks.
- Made `upload` run review validation by default before writing to SiYuan.
- Added checks for required AI review sections, completed review reports, manifests, and local image paths.
- Added WeChat long-article structure checks that compare raw and reviewed Markdown and require clearer topic headings before upload.
- Added OpenAI and Anthropic AI provider configuration.
- Added `ai-review`, `verify`, and `run` commands for AI rewrite, pre-upload AI verification, revision loop, and one-command upload.
- Moved CLI execution toward config-only credentials and upload targets to reduce command-history leakage.
- Split long review prompts into `prompts/` files and separated AI workflow config from provider credentials.
- Added Markdown link normalization and validation so bare prose URLs do not reach SiYuan upload.

### 2026-05-11

- Grouped extraction outputs into per-article workspaces under `outputs/<article_id>/`.
- Changed AI rewrite output to structured JSON with separate `markdown` and `review` fields so `review.json` records actual article-specific review decisions without embedding the Markdown body.

### 2026-05-12

- Replaced destructive platform cleaning and rule candidate aggregation with external marker rule files, per-article `noise_hints.json`, AI prompt injection for matched markers, and AI-driven suggested marker persistence. Runtime rules live in gitignored `platform_rules/`; the repository tracks starter examples in `platform_rules.example/`.
- Added `rules-review` for deterministic local marker rule hygiene reports and safe cleanup of empty, duplicate, and invalid-category marker entries.
- Removed the public `verify` CLI command, keeping AI verification as an internal `ai-review` quality gate.
- Reused the system validation result during `ai-review` verification so one successful review attempt does not run deterministic validation twice.
- Changed `upload` into a manual endpoint that does not require `review.json` or local review validation before sending Markdown to SiYuan.
- Moved WeChat-specific system validation out of `src/core/review_validation.py` into `src/platforms/wechat_mp/review_validation.py`.
