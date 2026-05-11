# CLAUDE.md

Noosphere is an article web extraction, AI review, and SiYuan upload tool.

## Project Rules

- Read `README.md`, `SKILL.md`, and `UPDATE.md` before changing workflow behavior.
- `references/` contains Crawl4AI and SiYuan documentation that can be used as reference when developing new features.
- Preserve clear output boundaries for `outputs/raw`, `outputs/reviewed`, `outputs/assets`, `outputs/manifests`, and `outputs/reviews`; do not edit or rewrite files in `outputs/raw`, and perform all review, editing, and AI rewriting based on `outputs/reviewed`.
- Keep long prompts in `prompts/`; keep `config.json.example` easy and human-readable.

## Verification

- Run focused tests for every behavior change.
- Run `pytest -q`, `python -m compileall src`, `python -m json.tool config.json.example`, and `git diff --check` before committing broad workflow changes.

## Git

- Keep commits grouped by intent: implementation, docs, and small corrections separately.
- Never commit `config.json`, `outputs/`, API keys, SiYuan tokens, or generated caches.
