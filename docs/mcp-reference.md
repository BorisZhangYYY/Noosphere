# MCP Reference

The MCP service exposes structured Noosphere operations over SSE at `http://localhost:8080/sse`. It uses the same application service, database, article workspaces, Collections, and settings as the web interface and CLI.

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

- `list_collections`
- `create_collection`
- `update_collection`
- `delete_collection`
- `restore_collection`
- `place_article`

Safe organization flow:

1. Call `list_collections`.
2. Create missing structure explicitly with `create_collection`; `parent_id` may identify a Collection at any depth.
3. Select one active `collection_id`.
4. Call `place_article`, or omit `collection_id` to place the article at the Collection root.

Use `update_collection` to rename or describe a Collection. `delete_collection` and `restore_collection` operate recoverably on the complete descendant subtree. Automatic AI placement is closed-set: it may select an existing active ID but never create, rename, or propose a Collection.

When a user explicitly names a missing destination, an MCP client may instead pass `collection_path`, `create_missing=true`, and a non-empty `collection_description` to `place_article`. Noosphere creates only the final path segment; every parent segment must already exist. The creation flag is never inferred from an AI classification result.

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

## Article Placement Example

An MCP client should reason over stable IDs rather than names:

```text
list_collections()
  -> id="AI_ID"
  -> children[].id="AI_INTERVIEWS_ID"

place_article(
  article_id="ARTICLE_ID",
  collection_id="AI_INTERVIEWS_ID"
)
```

Noosphere does not seed Collections. Build the user-owned hierarchy first, then place with returned stable IDs. Calling `place_article(article_id="ARTICLE_ID")` returns the article to the root.

For an explicitly user-directed missing leaf:

```text
place_article(
  article_id="ARTICLE_ID",
  collection_path=["AI 相关", "AI 测评"],
  create_missing=true,
  collection_description="以正文中的模型能力、基准测试和真实使用体验为主。"
)
```

This call may create `AI 测评` only when `AI 相关` already exists. Without `create_missing=true`, the same missing path is rejected.

## Long Operations

Prefer background jobs for long articles or slow providers:

```text
start_capture(url=...)
  -> job_id

get_job(job_id=...)
  -> status, progress, logs, result or error
```

Job state is server-side. The operation continues when the initiating browser page or MCP conversation is no longer open.
