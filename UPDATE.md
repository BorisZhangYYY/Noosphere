# UPDATE

This file tracks forward-looking development notes for Noosphere. Keep README focused on current user-facing behavior, and use this file for planned work, progress notes, and implementation decisions that are not yet product documentation.

## Current Baseline

As of 2026-05-09, the project has:

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
- Platform cleaning split into extractor, cleaning flow, and rule constants.
- No legacy `src/classifier.py`, `src/wechat_mp/`, or `src/zhihu_zhuanlan/` entrypoints.

## Near-Term Roadmap

### 1. Review Report

Goal: make AI review output structured and traceable instead of only editing Markdown.

Status: implemented. `manual-review` creates `outputs/<article_id>/review.json` with fields for removed noise, preserved sections, formatting changes, image decisions, and suggested rule candidates. `ai-review` now expects structured rewrite JSON, writes the returned Markdown to `reviewed.md`, and writes only article-specific review metadata to `review.json`.

Next:

- Use completed review reports as input for rule candidate generation.

### 2. Validate Command

Goal: quickly check whether an extraction is ready for upload.

Status: foundation implemented. `validate` checks the required H1, AI summary section, main article section, local image links, Markdown links, extraction manifest, and completed review report. Long WeChat articles also receive raw/reviewed structure comparison so a wrapper-only AI review is rejected before upload.

Next:

- Add stricter schema validation for review report detail fields after the report format stabilizes.

### 3. Rule Candidate Loop

Goal: let repeated AI review findings become platform cleaning improvements.

- Store rule candidates under `outputs/rule_candidates/`.
- Prefer data-style rule suggestions first: footer markers, line patterns, tracking token patterns.
- Require tests before promoting behavior-changing cleaning logic into platform code.
- Keep rule promotion manual until the review report format is stable.

### 4. AI SDK Workflow

Goal: make external agents configure and invoke the CLI while Noosphere owns the extraction, AI review, pre-upload verification, revision loop, and upload flow.

Status: first implementation added for OpenAI and Anthropic endpoints through HTTP APIs and `config.json`. CLI commands now avoid token/key prefixes and read credentials, endpoints, prompts, and upload targets from local config. AI workflow settings live under `ai`; provider credentials and model parameters live under `ai_providers`.

Next:

- Add provider-specific integration tests with recorded local fixtures if needed.
- Add CLI ergonomics for dry-run review and upload preview.
- Keep deterministic validation as the final upload gate even after AI verification is available.

### 5. Manifest Replay

Goal: make extraction reproducible and easier to compare.

- Add a command or helper to inspect one manifest and print its raw, reviewed, asset, and source metadata paths.
- Support rerunning an extraction from a manifest URL while preserving article ID decisions when practical.
- Use manifests to compare crawler output before and after rule updates.

### 6. Asset Cleanup and Deduplication

Goal: keep local and SiYuan assets manageable.

- Detect unused local assets after review edits.
- Deduplicate repeated image URLs and repeated local files.
- Record cleanup decisions in manifest or review reports.

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

## Progress Entry Template

Use this template for future updates:

```markdown
### YYYY-MM-DD

- Goal:
- Implemented:
- Tests:
- Decisions:
- Next:
```
