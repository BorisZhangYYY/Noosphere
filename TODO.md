# Noosphere TODO

This file contains only unresolved, deliberately deferred, or release-blocking work. Completed user-visible changes belong in `CHANGELOG.md`.

## Planned for v0.3.2

### Developer-oriented knowledge organization

The v0.3.2 goal is to make article organization predictable for a developer-oriented workflow without turning Noosphere into a general-purpose note-taking or personal-profile application.

Two of the eight issue slots are already consumed by the provider-capability layout fix and reviewed-title recovery recorded under `[Unreleased]` in `CHANGELOG.md`. The approved Docker Compose restart correction remains pre-scope Issue 0.

- [ ] **Issue 3 — Built-in developer processing profile and starter taxonomy.** Provide one versioned, product-owned developer profile that seeds a stable two-level category tree. It must contain no imported personal data and no dependency on another project.
- [ ] **Issue 4 — Closed-set category management.** Let users create, rename, and retire categories explicitly; automatic classification may select existing category IDs or `Inbox`, but may not create categories.
- [ ] **Issue 5 — Multi-label article facets.** Add many-to-many labels for central topics/entities and content forms while preserving exactly one primary category path per article.
- [ ] **Issue 6 — Profile-aware automatic organization.** Classify against the active profile, closed taxonomy, and existing labels; persist reason and confidence, and route uncertain results to `Inbox`.
- [ ] **Issue 7 — Protected metadata editing boundary.** Separate structured source metadata from editable article content, permanently lock system fields, and expose controlled inputs only for genuinely missing enrichable fields.
- [ ] **Issue 8 — Evidence-backed AI metadata enrichment.** Allow review to fill only missing enrichable fields, require source evidence and provenance, reject overwrites, and record every accepted or reverted enrichment.

### Documentation and release quality

- [ ] Add troubleshooting cases from real extraction, provider-connectivity, image-review, and SiYuan-upload failures as they are reproduced.
- [ ] Verify every documented CLI command and MCP tool example against the v0.3.2 build before tagging.
- [ ] Run backend tests, frontend build, Docker health checks, PostgreSQL persistence checks, and public-image smoke tests before release.

## Deferred Beyond v0.3.2

- [ ] **Bilingual terminology glossary.** Define canonical multilingual terms, deterministic matching, protected/no-translate behavior, import/export, Web/MCP/CLI parity, and review-history integration in a later version.

- [ ] **Semantic knowledge search and RAG Q&A.** Keep the current cross-language search lightweight until the embedding model, vector storage or Elasticsearch strategy, citation model, and re-indexing lifecycle receive a separate design pass.

- [ ] **Self-healing extraction quality loop.** This is a major autonomous extraction-maintenance feature and remains explicitly deferred. Full design: [.project/self-healing-extraction.md](.project/self-healing-extraction.md).
