# Noosphere TODO

This file contains only unresolved, deliberately deferred, or release-blocking work. Completed user-visible changes belong in `CHANGELOG.md`.

## Deferred Beyond v0.3.2

- [ ] **Multi-label article facets.** Add many-to-many labels for central topics/entities and content forms only after the primary two-level category workflow has proved stable.

- [ ] **Optional consumer-owned personalization adapters.** If another project later consumes Noosphere taxonomy or article data, keep that integration outside Noosphere's core and define it through a separate versioned contract.

- [ ] **Bilingual terminology glossary.** Define canonical multilingual terms, deterministic matching, protected/no-translate behavior, import/export, Web/MCP/CLI parity, and review-history integration in a later version.

- [ ] **Semantic knowledge search and RAG Q&A.** Keep the current cross-language search lightweight until the embedding model, vector storage or Elasticsearch strategy, citation model, and re-indexing lifecycle receive a separate design pass.

- [ ] **Self-healing extraction quality loop.** This is a major autonomous extraction-maintenance feature and remains explicitly deferred. Full design: [.project/self-healing-extraction.md](.project/self-healing-extraction.md).
