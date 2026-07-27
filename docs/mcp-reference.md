# MCP Reference

The MCP service exposes structured Noosphere operations over SSE at `http://localhost:8080/sse`. It uses the same application service, database, article workspaces, taxonomy, and settings as the web interface and CLI.

## Tool Groups

### Pipeline

- `extract_article`
- `review_article`
- `upload_article`
- `run_pipeline`
- `start_capture`
- `start_review`
- `start_upload`

The first four tools are synchronous. The `start_*` tools create background jobs for clients that should avoid holding one request open during a long extraction, review, or upload.

### Article workspace

- `list_articles`
- `get_article`
- `update_article_content`
- `update_missing_article_metadata`
- `list_article_images`
- `set_article_image_state`

Content updates affect editable prose; Noosphere restores protected source metadata before storing or exporting `reviewed.md`. `get_article` returns current metadata provenance and enrichment history. `update_missing_article_metadata` accepts only Author and Published values that were absent from the captured source. During AI review, candidate values additionally require an exact captured-text excerpt and are recorded as accepted or reverted. Image state operations use the asset identity reported by `list_article_images`.

### Knowledge organization

- `list_taxonomy`
- `create_taxonomy_category`
- `update_taxonomy_category`
- `classify_article`

Safe classification flow:

1. Call `list_taxonomy` using the preferred locale.
2. If the intended category is missing, create it explicitly with `create_taxonomy_category`; pass a top-level `parent_id` only for the optional second level.
3. Select an active `tag_id` and optional `subtag_id`.
4. Call `classify_article` with the stable IDs.

Use `update_taxonomy_category` to localize, rename, describe, retire, or restore a category. Localized names are presentation data, not category identities.

### Review design

- `list_review_perspectives`
- `save_review_perspective`
- `delete_review_perspective`

Built-in perspectives are read-only. Custom perspectives can define their own prompt and output-template content.

### Runtime settings

- `get_runtime_settings`
- `update_runtime_settings`
- `activate_ai_provider`
- `test_runtime_service`

Secrets are masked and cannot be revealed through MCP. An agent may update an explicitly supplied secret, but it cannot read the stored value back.

### Observability

- `get_job`
- `list_jobs`

Poll `get_job` after a `start_*` call. Repeated starts for the same active article operation return the existing job where the operation is idempotent.

## Article Classification Example

An MCP client should reason over canonical IDs rather than labels:

```text
list_taxonomy(locale="en-US")
  -> tag_id="USER_CATEGORY_ID"
  -> subtag_id="USER_SUBCATEGORY_ID"

classify_article(
  article_id="ARTICLE_ID",
  tag_id="USER_CATEGORY_ID",
  subtag_id="USER_SUBCATEGORY_ID"
)
```

Noosphere does not seed categories. Configure the user-owned taxonomy first, then classify with the returned stable IDs. If the interface later switches to Chinese, the article remains assigned to the same IDs while the returned labels use their Chinese localization.

## Long Operations

Prefer background jobs for long articles or slow providers:

```text
start_capture(url=...)
  -> job_id

get_job(job_id=...)
  -> status, progress, logs, result or error
```

Job state is server-side. The operation continues when the initiating browser page or MCP conversation is no longer open.
