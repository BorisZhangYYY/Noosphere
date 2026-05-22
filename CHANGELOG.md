# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [0.1.0] - 2026-05-22

### Added
- X (Twitter) social post extraction via oEmbed API MVP.
- Email sharing via SMTP with HTML rendering and inline image embedding.
- AI review workflow with three stages: rewrite, metadata generation, and pre-upload verification.
- Deterministic system validation for reviewed Markdown (`validate` command).
- Platform marker rules with local rule hygiene checks (`rules-review` command).
- Local image downloading during extraction with asset upload support.
- One-command full workflow (`run` command): extract → ai-review → upload.
- Support for WeChat public account articles, Zhihu Zhuanlan, and Xiaoheihe posts.
- SiYuan note platform upload adapter.
- OpenAI and Anthropic-compatible AI provider support (including Kimi and MiniMax endpoints).
- Structured JSON AI rewrite output with separate `markdown` and `review` fields.

### Changed
- Restructured `src/core/` into topical subdirectories: `models/`, `config/`, `paths/`, `review/`, `rules/`, `markdown/`.
- Renamed ambiguous core files for clarity (`ai_review.py` → `ai_review_data.py`, `markdown.py` → `cleaner.py`, etc.).
- Migrated `UPDATE.md` to `CHANGELOG.md` with Keep a Changelog format.
- Rewrote `CLAUDE.md` with development conventions for changelog, commits, and comments.
