# CLAUDE.md

Noosphere is an article web extraction, AI review, sharing and storing tool.

## Project Rules

- Read `README.md`, `TODO.md`, `CHANGELOG.md`, and `skills/noosphere/SKILL.md` before changing workflow behavior.
- Keep user-facing installation, deployment, and operation guides in `docs/`. Keep repository-internal development rules in `.project/`; use this file as a compact index rather than a complete handbook.
- `references/` contains Crawl4AI and SiYuan documentation that can be used as reference when developing new features.
- Preserve clear output boundaries inside `outputs/<article_id>/`: do not edit or rewrite `raw.md`, and perform all review, editing, and AI rewriting based on `reviewed.md`. Keep `manifest.json`, `review.json`, and `assets/` tied to the same article workspace.
- Keep long prompts in `prompts/`; keep `config.json.example` easy and human-readable.
- Platform extraction strategies are documented in [.project/platform-extractors.md](.project/platform-extractors.md). When changing extractor behavior, read and update this doc.
- Record unresolved product decisions and deliberately deferred work in `TODO.md`; completed user-visible work belongs in `CHANGELOG.md` instead.

## Verification

- Run `python -m compileall src`, `python -m json.tool config.json.example`, and `git diff --check` before committing workflow changes.

## Testing

```bash
# Install with dev dependencies (includes pytest, pytest-asyncio)
pip install -e ".[dev]"

# Run all tests
python -m pytest tests/ -v

# Run a specific test file
python -m pytest tests/test_graph.py -v
```

## Docker Build

```bash
# Build and start the full stack (Noosphere + Postgres)
docker compose up --build

# Open the web workspace
# http://localhost:8080/app/

# Build the image standalone
docker build -t noosphere .

# Run with a custom host data directory
NOOSPHERE_DATA_DIR=/path/to/noosphere-data docker compose up --build
```

## Git & Changelog

See [.project/git-conventions.md](.project/git-conventions.md) for commit format, changelog management, and push/PR rules.

## Release Planning

See [.project/release-planning.md](.project/release-planning.md) for version scope limits and issue-counting rules.

## Comments

Write all comments in English. Add comments only when the WHY is non-obvious. Do not comment WHAT — names should explain that. Prefer module and class docstrings over inline comments.
