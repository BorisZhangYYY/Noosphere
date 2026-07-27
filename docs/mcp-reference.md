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
- `list_article_images`
- `set_article_image_state`

Content updates affect the editable reviewed copy. Image state operations use the asset identity reported by `list_article_images`.

### Knowledge organization

- `list_taxonomy`
- `classify_article`

Safe classification flow:

1. Call `list_taxonomy` using the preferred locale.
2. Select an existing `tag_id` and optional `subtag_id`.
3. Call `classify_article` with the stable IDs.
4. Supply bilingual localization objects only when intentionally creating a new category path.

Localized names are presentation data, not category identities. This prevents `AI Agent`, `Agents`, and `智能体` from becoming unrelated categories.

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
