# UPDATE

This file tracks forward-looking development notes for Noosphere. Keep README focused on current user-facing behavior, and use this file for planned work, progress notes, and implementation decisions that are not yet product documentation.

## Current Baseline

As of 2026-05-11, the project has:

- Single-article CLI workflow through `python -m src.cli`.
- Supported sources: WeChat Official Account articles and Zhihu Zhuanlan articles.
- Article workspaces under `outputs/<article_id>/` containing `raw.md`, `reviewed.md`, `manifest.json`, `review.json`, and `assets/`.
- Draft review reports through `python -m src.cli manual-review`.
- Review readiness checks through `python -m src.cli validate`.
- AI review through `python -m src.cli ai-review` with OpenAI or Anthropic endpoints.
- One-command extract, AI review, verification, and upload through `python -m src.cli run`.
- Credentials, model settings, prompts, SiYuan API settings, and upload targets are read from local `config.json`; AI workflow settings and provider settings are stored separately.
- Upload validation that blocks unreviewed Markdown before writing to SiYuan.
- Markdown normalization for bare prose URLs before AI-reviewed content is uploaded.
- crawl4ai-backed first-round extraction with platform-specific cleaning rules.
- Local image downloading during extraction and SiYuan asset upload during import.
- Markdown-first SiYuan upload that preserves Markdown tables.
- Modular architecture: `core`, `integrations`, `pipelines`, and `platforms`.

## Future Developments

- **Rule Candidate Loop**: Let repeated AI review findings become platform cleaning improvements.


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
