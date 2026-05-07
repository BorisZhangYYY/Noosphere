# UPDATE

This file tracks forward-looking development notes for Noosphere. Keep README focused on current user-facing behavior, and use this file for planned work, progress notes, and implementation decisions that are not yet product documentation.

## Current Baseline

As of 2026-05-07, the project has:

- Single-article CLI workflow through `python -m src.cli`.
- Supported sources: WeChat Official Account articles and Zhihu Zhuanlan articles.
- Layered output directories: `outputs/raw/`, `outputs/reviewed/`, `outputs/assets/`, and `outputs/manifests/`.
- Draft review reports through `python -m src.cli review-report`.
- crawl4ai-backed first-round extraction with platform-specific cleaning rules.
- Local image downloading during extraction and SiYuan asset upload during import.
- Markdown-first SiYuan upload that preserves Markdown tables.
- Modular architecture: `core`, `integrations`, `pipelines`, and `platforms`.
- Platform cleaning split into extractor, cleaning flow, and rule constants.
- No legacy `src/classifier.py`, `src/wechat_mp/`, or `src/zhihu_zhuanlan/` entrypoints.

## Near-Term Roadmap

### 1. Review Report

Goal: make AI review output structured and traceable instead of only editing Markdown.

Status: foundation implemented. `review-report` creates `outputs/reviews/<article_id>.json` with fields for removed noise, preserved sections, formatting changes, image decisions, and suggested rule candidates.

Next:

- Let the agent fill review report fields during article review.
- Use completed review reports as input for rule candidate generation.

### 2. Validate Command

Goal: quickly check whether an extraction is ready for upload.

- Add `python -m src.cli validate outputs/reviewed/ARTICLE.md`.
- Validate required H1, AI summary section, Markdown body, local image paths, and manifest presence.
- Return concise CLI errors suitable for agent follow-up.

### 3. Rule Candidate Loop

Goal: let repeated AI review findings become platform cleaning improvements.

- Store rule candidates under `outputs/rule_candidates/`.
- Prefer data-style rule suggestions first: footer markers, line patterns, tracking token patterns.
- Require tests before promoting behavior-changing cleaning logic into platform code.
- Keep rule promotion manual until the review report format is stable.

### 4. Manifest Replay

Goal: make extraction reproducible and easier to compare.

- Add a command or helper to inspect one manifest and print its raw, reviewed, asset, and source metadata paths.
- Support rerunning an extraction from a manifest URL while preserving article ID decisions when practical.
- Use manifests to compare crawler output before and after rule updates.

### 5. Asset Cleanup and Deduplication

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
- Added `review-report` for draft structured review reports linked to extraction manifests.

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
