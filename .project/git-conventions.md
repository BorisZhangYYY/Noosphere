# Git Conventions

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

## Changelog

Follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format. Maintain `CHANGELOG.md` at repo root. Group entries under `[Unreleased]` and versioned sections.

Categories: `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`.

## Before Every Commit

- Read `CHANGELOG.md` and record **user-notable** changes (not implementation details) under `[Unreleased]` with the date.
- Keep commits grouped by intent: implementation, docs, and small corrections separately.

## What NOT to Commit

- `config.json`, `outputs/`, API keys, SiYuan tokens, or generated caches.
- **Superpowers-related** plans — keep them local.

## Pushing & PRs

- **All commits, pull request creation, and pull request merges must be approved by the user. Do not push branches, open PRs, or merge PRs without explicit user approval.**
