# Search and batch workspace

These first-version features are included in v0.3.2.7.

## Full-text search

Choose **Full-text search** beneath **Workspace** in the main navigation, or enter a query in the Knowledge sidebar and press Enter. The existing sidebar list still filters article metadata while typing.

Search covers the reviewed article text shown in the editor, including its title and headings. Reflections, quote annotations, raw source text and protected source metadata are excluded. The sidebar's live metadata filter remains separate. Multiple terms must occur in the article text; quoted terms match a sequence of normalized tokens. Chinese characters are indexed individually, so two-character Chinese queries work alongside English names and version numbers. This is lexical search, not semantic question answering.

Each article has one body excerpt with highlighted matches. Local article images in excerpts display as thumbnails. Filter by collection (including descendants), platform and capture date. Click an excerpt to open its matching passage; every occurrence of the search terms in the article receives a light background and red underline. These marks remain while viewing the search destination, move together with the text during rapid scrolling and resizing, stay inside the reader's visible boundary, and clear in Edit mode or when leaving the search destination. Quote annotation underlines remain independent. If the source changed after the search, the workspace asks you to search again instead of highlighting a stale location.

The local `search.sqlite3` index is derived data. Each search reconciles reviewed-file signatures, including external file edits and removals; unchanged content is reused. Existing indexes automatically remove legacy annotation, reflection, source, title and author fields on the next search, without a manual rebuild. **Rebuild index** recreates the index, including after index corruption. Raw Markdown, personal notes and annotations are not modified by indexing. Deleted article markers exclude leftover files. The first search over a large library can take longer. A background indexing queue remains future work. Large-library benchmarking is not part of the current verification scope.

CLI:

```bash
nsphr search '知识管理' --json
nsphr search '"Agent v0.3.2.6"' --scope reviewed --limit 30 --offset 0 --json
nsphr search 'reading notes' --scope reviewed --collection-id COLLECTION_ID --json
```

MCP: `search_library(query, scope, collection_id, limit, offset)`. Scope accepts `reviewed`; the legacy default `all` is an alias for the same body-only search. Other scopes are rejected consistently by HTTP, CLI and MCP.

HTTP: `GET /api/v1/search?q=...&scope=...&collection=...&platform=...&after=YYYY-MM-DD&before=YYYY-MM-DD&limit=30&offset=0`; rebuild with `POST /api/v1/search/rebuild`. Existing authentication applies to all search endpoints.

## Batch workspace

Choose **Batch capture** from the **+** menu in the Knowledge sidebar. Paste one URL per line, or load a UTF-8 text file up to 1 MB. A batch accepts up to 100 URLs. Lines beginning with `#` are ignored by the text importer. Submitting a batch opens its progress in the batch workspace.

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
