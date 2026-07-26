# Noosphere TODO

This file contains only unresolved, deliberately deferred, or release-blocking work. Completed user-visible changes belong in `CHANGELOG.md`.

## Planned for v0.3.2

### Bilingual terminology glossary

The v0.3.2 feature goal is consistent terminology across translated reviews without rewriting user-authored custom prompts.

- [ ] Define the canonical glossary record: stable ID, source term, Simplified Chinese and English preferred forms, aliases, protected/no-translate flag, optional domain, and notes.
- [ ] Define deterministic matching and conflict precedence for exact terms, aliases, product names, case variants, and overlapping phrases.
- [ ] Persist glossary entries in shared application storage and provide migration-safe import/export in a human-readable format.
- [ ] Apply the glossary during AI review and translation while preserving code, URLs, quoted source text, and user-authored custom prompt content.
- [ ] Add glossary management to the web workspace with layouts that accommodate longer English descriptions without clipping.
- [ ] Expose equivalent list, create/update, delete, import, and export operations through MCP and CLI.
- [ ] Record glossary-assisted review activity in the existing per-article operation history without storing or exposing provider secrets.
- [ ] Add bilingual matching, precedence, migration, Web/MCP/CLI parity, and end-to-end review tests.

### Documentation and release quality

- [ ] Add troubleshooting cases from real extraction, provider-connectivity, image-review, and SiYuan-upload failures as they are reproduced.
- [ ] Verify every documented CLI command and MCP tool example against the v0.3.2 build before tagging.
- [ ] Run backend tests, frontend build, Docker health checks, PostgreSQL persistence checks, and public-image smoke tests before release.

## Deferred Beyond v0.3.2

- [ ] **Semantic knowledge search and RAG Q&A.** Keep the current cross-language search lightweight until the embedding model, vector storage or Elasticsearch strategy, citation model, and re-indexing lifecycle receive a separate design pass.

- [ ] **Self-healing extraction quality loop.** This is a major autonomous extraction-maintenance feature and remains explicitly deferred. Full design: [.project/self-healing-extraction.md](.project/self-healing-extraction.md).
