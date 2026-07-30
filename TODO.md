# Noosphere TODO

This file contains only unresolved, deliberately deferred, or release-blocking work. Completed user-visible changes belong in `CHANGELOG.md`.

## v0.3.2.1 — Hierarchical collections and workspace polish

Goal: replace the detached two-level taxonomy with a document-like collection tree that is created and navigated in context, while bringing the article workspace to the intended persistent three-column design.

- [x] **Unlimited collection tree.** Add user-owned collection index nodes with arbitrary nesting, inline creation, rename, recoverable deletion, and restoration.
- [x] **Article placement and migration.** Place each article in one index document or leave it unfiled at the workspace level, and migrate existing two-level taxonomy paths and assignments without losing data.
- [x] **Closed-set AI placement.** Let AI select only an existing index-document ID, never create one, and leave unmatched or low-confidence articles unfiled at the workspace level.
- [x] **Shared interface contract.** Replace taxonomy operations with collection-tree and article-placement operations across the application service, Web API, MCP, and CLI.
- [x] **Persistent knowledge sidebar.** Keep the primary navigation visible, render clickable index documents and their nested articles directly in the sidebar, and create child indexes in context.
- [x] **Article navigation hierarchy.** Add the intended toolbar, save state, clickable collection breadcrumbs, and visible collection path chips around the article title.
- [x] **Compact workspace utilities.** Move Settings to the bottom utility dock, present sources in a Help dialog, relocate Capture to the knowledge-workspace heading, and restyle the inspection rail as focused sections.
- [x] **Responsive and accessible finish.** Verify the new workspace in both themes and locales across desktop, tablet, mobile, keyboard, loading, empty, and error states.

### Release gates

- [x] Frontend type-check and production build pass.
- [x] Python compile, configuration JSON validation, and the complete test suite pass.
- [x] Existing SQLite taxonomy data migrates to collections; PostgreSQL schema creation and migration remain compatible.
- [x] Visual smoke tests pass for light/dark themes, Chinese/English, desktop/tablet/mobile, collection creation, article movement, and root fallback.
- [x] README, user guides, bundled skill, and changelog describe collections rather than the retired two-level taxonomy.

## Deferred Beyond v0.3.2

- [ ] **Multi-label article facets.** Add many-to-many labels for central topics/entities and content forms only after the primary Collection-placement workflow has proved stable.

- [ ] **Optional consumer-owned personalization adapters.** If another project later consumes Noosphere Collection or article data, keep that integration outside Noosphere's core and define it through a separate versioned contract.

- [ ] **Bilingual terminology glossary.** Define canonical multilingual terms, deterministic matching, protected/no-translate behavior, import/export, Web/MCP/CLI parity, and review-history integration in a later version.

- [ ] **Semantic knowledge search and RAG Q&A.** Keep the current cross-language search lightweight until the embedding model, vector storage or Elasticsearch strategy, citation model, and re-indexing lifecycle receive a separate design pass.

- [ ] **Self-healing extraction quality loop.** This is a major autonomous extraction-maintenance feature and remains explicitly deferred. Full design: [.project/self-healing-extraction.md](.project/self-healing-extraction.md).
