# Noosphere TODO

This file contains only unresolved, deliberately deferred, or release-blocking work. Completed user-visible changes belong in `CHANGELOG.md`.

## Planned for v0.3.2

### User-owned knowledge organization

The v0.3.2 goal is to make article organization predictable while keeping Noosphere focused on article processing and MCP support for a separate knowledge workspace. Noosphere must not import, scan, or depend on an external personal-profile project.

Two of the eight issue slots are already consumed by completed work recorded under `[Unreleased]` in `CHANGELOG.md`. The approved Docker Compose restart correction remains pre-scope Issue 0.

- [ ] **Issue 7 — Protected metadata editing boundary.** Separate structured source metadata from editable article content, permanently lock system fields, and expose controlled inputs only for genuinely missing enrichable fields.
- [ ] **Issue 8 — Evidence-backed AI metadata enrichment.** Allow review to fill only missing enrichable fields, require source evidence and provenance, reject overwrites, and record every accepted or reverted enrichment.

### Documentation and release quality

- [ ] Add troubleshooting cases from real extraction, provider-connectivity, image-review, and SiYuan-upload failures as they are reproduced.
- [ ] Verify every documented CLI command and MCP tool example against the v0.3.2 build before tagging.
- [ ] Run backend tests, frontend build, Docker health checks, PostgreSQL persistence checks, and public-image smoke tests before release.

## Deferred Beyond v0.3.2

- [ ] **Multi-label article facets.** Add many-to-many labels for central topics/entities and content forms only after the primary two-level category workflow has proved stable.

- [ ] **Optional consumer-owned personalization adapters.** If another project later consumes Noosphere taxonomy or article data, keep that integration outside Noosphere's core and define it through a separate versioned contract.

- [ ] **Bilingual terminology glossary.** Define canonical multilingual terms, deterministic matching, protected/no-translate behavior, import/export, Web/MCP/CLI parity, and review-history integration in a later version.

- [ ] **Semantic knowledge search and RAG Q&A.** Keep the current cross-language search lightweight until the embedding model, vector storage or Elasticsearch strategy, citation model, and re-indexing lifecycle receive a separate design pass.

- [ ] **Self-healing extraction quality loop.** This is a major autonomous extraction-maintenance feature and remains explicitly deferred. Full design: [.project/self-healing-extraction.md](.project/self-healing-extraction.md).
