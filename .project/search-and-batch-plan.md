# Full-text search and batch workspace proposal

Status: first local search and batch iterations implemented on 2026-09-20; the full proposal below is not yet complete or assigned a release version. Current behavior and deferred capabilities are documented in `docs/search-and-batches.md` and `TODO.md`. These are separate iterations after the reliability release. Each iteration stays within eight product issues.

## Full-text search

Goal: find a remembered passage and return to its context, including the user's reflections and annotations.

1. Search title, author, reviewed body, reflections and annotations. Label the matching field and group multiple passages under one article. Keep raw source an explicit optional scope to avoid duplicate results.
2. Add a dedicated results page using the existing search entry. Support quoted phrases, keywords, collection/subtree, source, time and content-scope filters; preserve query/filter state in the URL.
3. Return readable highlighted snippets with a passage link. Store source offsets and article revisions with hits. Re-resolve anchors against the current content; disclose a changed passage instead of jumping to unrelated text.
4. Start with a rebuildable SQLite FTS5 sidecar index for both current single-instance deployments. Share Chinese/English normalization and tokenization in the application, with a versioned tokenizer. Validate two-character Chinese terms, mixed English names, punctuation, versions and exact phrases on a real query corpus before selecting the tokenizer. FTS5's trigram full-text matching alone cannot cover terms shorter than three characters: https://www.sqlite.org/fts5.html.
5. Persist indexing work and update it on edits, AI review, reflection/annotation changes, collection changes, trash, permanent deletion and restoration. Filter deleted/inaccessible articles against current state before returning hits. Reconcile external file changes at startup/manual rebuild. Expose index freshness and rebuild progress. The index never becomes the source of truth.
6. Establish relevance and performance acceptance tests: known passages must be found; personal content stays local; deleted results disappear; interrupted indexing resumes. Earlier large-library latency targets are deferred; the user excluded large-library benchmarking on 2026-09-21. Use small functional regressions in the current scope. No large-library performance claim is made.

No new search service is required initially. Multiple application instances would require revisiting index ownership/storage. Semantic search and citation-based Q&A remain later work; ordinary search does not call a model.

## Batch workspace

Goal: make a batch of links inspectable and recoverable using the existing durable background-job machinery.

1. Accept pasted URLs or a text file. Preview valid/invalid links, duplicates within the batch and matches in the existing library. Skip existing articles by default; explicitly choose re-extraction or re-review. Preserve source identifiers when normalizing URLs.
2. Snapshot the batch's workflow, model/provider, language, review perspective and target collection. Offer capture-only or capture-plus-review; upload requires an explicitly selected, configured destination. Preserve user-owned collection boundaries.
3. Persist batch and item records linked to existing jobs. Display one row per article with stage, status, elapsed time and actionable error; filter queued/running/completed/skipped/failed/cancelled items. Keep the batch discoverable after navigation or restart.
4. Save stage outputs and input revisions. Retry only failed work when prior outputs remain valid. Use stage idempotency keys and reconcile uncertain upload outcomes before retrying, so restarting does not silently duplicate delivery.
5. Reuse bounded execution with site/provider limits and capped backoff. Pause stops dequeuing and lets in-flight work finish. Cancel immediately removes pending work and cooperatively interrupts running work where possible; it cannot reverse completed uploads or model usage. After restart, surface interrupted items and require explicit resume for externally consequential stages.
6. Support bulk movement into existing collections and export of failed URLs/errors. Avoid rerunning successful items just to retry a few failures.
7. Record provider-reported usage when available; label missing usage and price estimates. Add cost budgets after measurement is reliable. Do not present estimates as final bills.

Acceptance scenarios: duplicate-heavy input; mixed success/failure; rate limits; pause/resume; service restart mid-review; uncertain upload acknowledgement; stale article revision; retry without repeating completed delivery. Reflections and annotations remain outside uploads.

## Sequence

Finish reliability validation first. Implement search as the next independent feature scope, then the batch workspace. Full backup/import and recoverable review history remain separately tracked in TODO.md. No release dates or feature completion are implied by this proposal.
