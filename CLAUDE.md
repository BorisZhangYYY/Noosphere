# CLAUDE.md

Noosphere is an article web extraction, AI review, and SiYuan upload tool.

## Project Rules

- Read `README.md`, `SKILL.md`, and `UPDATE.md` before changing workflow behavior.
- `references/` contains Crawl4AI and SiYuan documentation that can be used as reference when developing new features.
- Preserve clear output boundaries inside `outputs/<article_id>/`: do not edit or rewrite `raw.md`, and perform all review, editing, and AI rewriting based on `reviewed.md`. Keep `manifest.json`, `review.json`, and `assets/` tied to the same article workspace.
- Keep long prompts in `prompts/`; keep `config.json.example` easy and human-readable.

## Verification

- Run focused tests for every behavior change.
- Run `pytest -q`, `python -m compileall src`, `python -m json.tool config.json.example`, and `git diff --check` before committing broad workflow changes.

## Git

- Before every commit, read UPDATE.md and record today's development progress with the date.
- Keep commits grouped by intent: implementation, docs, and small corrections separately.
- Never commit `config.json`, `outputs/`, API keys, SiYuan tokens, or generated caches.
- Never commit **superpowers-related** plans, keeping them local. 
