# CLAUDE.md

Noosphere is an article web extraction, AI review, sharing and storing tool.

## Project Rules

- Read `README.md`, `skills/noosphere/SKILL.md`, and `CHANGELOG.md` before changing workflow behavior.
- `references/` contains Crawl4AI and SiYuan documentation that can be used as reference when developing new features.
- Preserve clear output boundaries inside `outputs/<article_id>/`: do not edit or rewrite `raw.md`, and perform all review, editing, and AI rewriting based on `reviewed.md`. Keep `manifest.json`, `review.json`, and `assets/` tied to the same article workspace.
- Keep long prompts in `prompts/`; keep `config.json.example` easy and human-readable.

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

## Comments

Write all comments in English. Add comments only when the WHY is non-obvious. Do not comment WHAT — names should explain that. Prefer module and class docstrings over inline comments.
