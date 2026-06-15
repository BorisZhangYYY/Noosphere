# CLAUDE.md

Noosphere is an article web extraction, AI review, sharing and storing tool.

## Project Rules

- Read `README.md`, `SKILL.md`, and `CHANGELOG.md` before changing workflow behavior.
- `references/` contains Crawl4AI and SiYuan documentation that can be used as reference when developing new features.
- Preserve clear output boundaries inside `outputs/<article_id>/`: do not edit or rewrite `raw.md`, and perform all review, editing, and AI rewriting based on `reviewed.md`. Keep `manifest.json`, `review.json`, and `assets/` tied to the same article workspace.
- Keep long prompts in `prompts/`; keep `config.json.example` easy and human-readable.

## Verification

- Run `python -m compileall src`, `python -m json.tool config.json.example`, and `git diff --check` before committing workflow changes.

## Git

- Before every commit, read CHANGELOG.md and record notable changes under [Unreleased] with the date.
- Keep commits grouped by intent: implementation, docs, and small corrections separately.
- Never commit `config.json`, `outputs/`, API keys, SiYuan tokens, or generated caches.
- Never commit **superpowers-related** plans, keeping them local.
- **All commits, pull request creation, and pull request merges must be approved by the user. Do not push branches, open PRs, or merge PRs without explicit user approval.**

## Changelog

Follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format. Maintain `CHANGELOG.md` at repo root. Group entries under `[Unreleased]` and versioned sections.

Categories: `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`.

## Commits

Use conventional commits with scope when applicable:

| Prefix | Meaning |
|--------|---------|
| `feat(scope):` | New feature |
| `fix(scope):` | Bug fix |
| `refactor(scope):` | Code change without behavior change |
| `docs(scope):` | Documentation only |
| `test(scope):` | Test changes |
| `chore(scope):` | Tooling, config, dependencies |

Examples:
- `feat(wechat_mp): add author extraction from meta tag`
- `refactor(core): move ai_review.py into review/ subdirectory`

## Comments

Write all comments in English. Add comments only when the WHY is non-obvious. Do not comment WHAT — names should explain that. Prefer module and class docstrings over inline comments. 
