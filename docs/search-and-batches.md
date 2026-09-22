# Search and batch workspace

These first-version features are included in v0.3.2.7.

## Full-text search

Choose **Full-text search** in the Knowledge sidebar, or enter a query in the sidebar and press Enter. The existing sidebar list still filters article metadata while typing.

Search covers titles, authors, reviewed articles, reflections and annotations. Choose **Original** explicitly to search raw source text. Multiple terms must occur in the same content field; quoted terms match a sequence of normalized tokens. Chinese characters are indexed individually, so two-character Chinese queries work alongside English names and version numbers. This is lexical search, not semantic question answering.

Results group matching fields under each article and highlight matching excerpts. Filter by collection (including descendants), platform and capture date. Opening a passage displays a larger source-text context inside the article. If its source changed after the search, the workspace asks you to search again instead of displaying a stale passage as current. This first version does not automatically scroll the rendered article to a matching paragraph.

The local `search.sqlite3` index is derived data. Each search reconciles file signatures, including external file edits and removals; unchanged content is reused. **Rebuild index** recreates the index, including after index corruption. Raw Markdown, personal notes and annotations are not modified by indexing. Deleted article markers exclude leftover files. The first search over a large library can take longer. A background indexing queue remains future work. Large-library benchmarking is not part of the current verification scope.

CLI:

```bash
nsphr search '知识管理' --json
nsphr search '"Agent v0.3.2.6"' --scope reviewed --limit 30 --offset 0 --json
nsphr search 'reading notes' --scope reflection --collection-id COLLECTION_ID --json
```

MCP: `search_library(query, scope, collection_id, limit, offset)`.

HTTP: `GET /api/v1/search?q=...&scope=...&collection=...&platform=...&after=YYYY-MM-DD&before=YYYY-MM-DD&limit=30&offset=0`; rebuild with `POST /api/v1/search/rebuild`. Existing authentication applies to all search endpoints.

## Batch workspace

Choose **Batch workspace** in the sidebar. Paste one URL per line, or load a UTF-8 text file up to 1 MB. A batch accepts up to 100 URLs. Lines beginning with `#` are ignored by the text importer.

Use **Check URLs** to preview invalid URLs, within-batch duplicates and already captured articles. URL fragments and hostname casing are normalized; query parameters remain intact so source identifiers are preserved. Existing articles are skipped. Use the individual article review action to review an existing article again.

Choose **Capture only** or **Capture and AI review**, an output language and an existing target collection. The current review perspective and provider are recorded at submission. If the configuration changes, subsequent stages stop and report that change; restore the original settings or submit a new batch. No credentials are stored in job payloads. The first version uses this configuration guard rather than persisting provider credentials or implementing full configuration snapshots.

The batch table shows each URL, stage, status and error. A failed review can reuse its completed capture. **Retry failed** retries failed items; **Retry item** retries one failed row. Completed items are retained. **Export failures** downloads URLs with commented error messages, ready to inspect or edit before another submission.

**Pause** stops starting new stages after the in-flight stage finishes. **Cancel pending** leaves completed work intact and cancels remaining pending work after the in-flight stage completes. These actions cannot reverse a crawler/model request already sent. Restarted running batches are marked interrupted; explicitly resume pending work or retry failed work. Paused jobs are retained in history. The first version runs items sequentially inside each batch and shares the service's global job concurrency limit with other work.

Batch processing does not automatically upload articles. Upload remains an explicit article action. Automated delivery, forced recapture, reliable cost accounting, provider-specific rate limits/backoff and bulk movement of existing articles remain later iterations.

MCP: `preview_batch`, `start_batch`, `control_batch`, and existing `get_job` / `list_jobs(kind="batch")`.

CLI status: `nsphr jobs list --kind batch --json` and `nsphr jobs show JOB_ID --json`. Batch submission/control is currently available through Web, HTTP and MCP.

HTTP:

- `POST /api/v1/batches/preview`: `{ "urls": ["https://..."] }`
- `POST /api/v1/batches`: URLs plus `mode` (`capture` or `review`), optional `perspective`, `language` (`source`, `zh-CN`, `en-US`) and `collectionId`.
- `GET /api/v1/batches`: retained batch history.
- `POST /api/v1/batches/BATCH_ID`: `{ "action": "pause|resume|retry|cancel" }`. Retry accepts an optional `itemIds` array.
