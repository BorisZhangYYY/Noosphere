# Noosphere TODO

Product and engineering backlog beyond the current milestone.
Items are grouped by effort / strategic value. Checked items are already done.

## ✅ Done in this milestone

1. Batch URL input for `extract` (`--batch FILE` / single URL).
2. Deduplication before extraction (skip already-extracted URLs unless `--force`).
3. Rich-based progress bars and extraction summary table.
4. Reduce vision API calls in image filtering (file-hash cache + skip description for PROMOTION images).
5. Add `--force` to `ai-review` and `upload`; both now accept a file, directory, or article ID.
6. Better error messages for unsupported URLs (list supported platforms/patterns).
7. Local filesystem archive adapter (`src/core/upload/adapters/local_adapter.py`).
8. Simple TUI dashboard (`nsphr tui`) for extract / ai-review / upload / email / image review.

---

## 🧭 LangGraph Architecture Rewrite Roadmap

Goal: replace the custom pipeline + direct API-call architecture with a **LangGraph StateGraph** so the workflow is explicit, state is persisted in SQLite/Postgres, and future GUI / dashboard / knowledge-base features can query a real database instead of scanning `outputs/`.

### Target state model (`ArticleState`)

```python
class ArticleState(TypedDict):
    article_id: str
    url: str
    platform: str
    content_type: str
    raw_markdown: str
    reviewed_markdown: str
    assets: list[Asset]
    image_filter_result: ImageFilterResult | None
    validation_result: ValidationResult | None
    upload_result: UploadResult | None
    attempts: int
    error: str | None
    status: Literal[
        "pending",
        "crawled",
        "image_filtered",
        "reviewed",
        "validated",
        "uploaded",
        "failed",
    ]
```

### Graph nodes

| Node | Responsibility |
|---|---|
| `classify` | URL classification, select extractor. |
| `crawl` | Invoke crawler tool (Crawl4AI / Firecrawl configurable). |
| `download_images` | Download remote images, rewrite Markdown links, build asset list. |
| `image_filter` | Vision-AI classification of images as `RELEVANT` or `PROMOTION`. |
| `edit` | LLM copy-editing based on the prompt template and image inventory. |
| `postprocess_images` | Remove promotion images and restore accidentally dropped relevant ones. |
| `validate` | Deterministic validation driven by prompt metadata. |
| `human_review` | LangGraph `interrupt` for user confirmation or manual edit. |
| `upload` | Invoke the active upload adapter (SiYuan / local archive). |
| `notify` | Record result, optional email, metrics. |
| `export` | Write `raw.md`, `reviewed.md`, `manifest.json`, `review.json` as debug / human-readable artifacts. |

### Conditional edges

- `crawl` failure → `error_handler` → END.
- `crawl` success → `download_images` → `image_filter`.
- `edit` → `postprocess_images` → `validate`.
- `validate` fails + `attempts < max_attempts` → `edit` (feedback loop).
- `validate` fails + `attempts >= max_attempts` → `human_review` → END.
- `validate` success → `human_review` (configurable auto-confirm).
- `human_review` confirms → `upload` → `notify` → `export` → END.

### Persistence strategy

- LangGraph checkpoint store (`SqliteSaver` default, `PostgresSaver` optional) is used for **orchestration state**: which node ran, retry counts, validation feedback, and human-in-the-loop interrupts. This enables resumable pipelines and future GUI status dashboards.
- `outputs/<article_id>/` **remains the protected article workspace** as long as the current boundary rules apply: `raw.md` is never edited, all editing happens on `reviewed.md`, and `manifest.json`, `review.json`, and `assets/` stay tied to the same article workspace.
- The `export` node writes/updates `raw.md`, `reviewed.md`, `manifest.json`, and `review.json` from the graph state so the filesystem view stays consistent with the checkpoint.
- Existing `manifest.json` / `review.json` fields can be mirrored into checkpoint metadata or a relational `articles` table for querying, but the article content and assets continue to live in `outputs/<article_id>/`.
- Future GUI reads the checkpoint / DB for pipeline status and history, and reads `outputs/<article_id>/reviewed.md` + `assets/` for article content.

### CLI compatibility

Keep existing commands but implement them as graph invocations. Each command still writes the familiar `outputs/<article_id>/` files:

| Command | Graph invocation |
|---|---|
| `nsphr extract URL` | Run graph through `download_images`; checkpoint at `image_filtered`; write `raw.md`, `reviewed.md`, `manifest.json`. |
| `nsphr ai-review ID` | Resume from checkpoint, run `edit → validate` loop; update `reviewed.md` and `review.json`. |
| `nsphr upload ID` | Resume from checkpoint, run `upload → notify → export`; update `manifest.json`. |
| `nsphr run URL` | Run full graph end-to-end. |

### Migration phases

1. **Phase 0 — Foundation**
   - Add `langgraph`, `langchain-core` dependencies.
   - Define `ArticleState` and tool abstractions: `CrawlTool`, `VisionTool`, `EditTool`, `ValidateTool`, `UploadTool`.
   - Set up `SqliteSaver` and a minimal `export` node.

2. **Phase 1 — AI review sub-graph**
   - Port the `edit → validate → retry` loop from `src/pipelines/ai_review.py` to a LangGraph sub-graph.
   - Keep filesystem outputs for backward compatibility.
   - Verify parity on a few sample articles.

3. **Phase 2 — Full pipeline graph**
   - Model `extract → ai-review → upload` as a single StateGraph.
   - Add `human_review` interrupt and config-driven auto-confirm.
   - Replace custom retry/validation loops entirely.

4. **Phase 3 — Database + API surface**
   - Add Postgres checkpoint option.
   - Design `articles`, `assets`, `uploads`, `reviews` tables.
   - Provide a small REST API for GUI / dashboard queries.

5. **Phase 4 — Knowledge base extensions**
   - Entity/topic extraction node.
   - Vector index + full-text search.
   - Knowledge-graph generation (see [karpathy-llm-wiki](https://github.com/Astro-Han/karpathy-llm-wiki) for inspiration).
   - Tagging, relations, and exploratory UI.

### Reference

- [karpathy-llm-wiki](https://github.com/Astro-Han/karpathy-llm-wiki) — inspiration for knowledge-graph / RAG presentation layer.

---

## 🟢 Quick Wins (low effort, high user value)

1. **Add more URL patterns / extractors**
   - Substack (`substack.com/p/*`)
   - Medium (`medium.com/@*`)
   - GitHub discussions
   - Reddit posts
   - Files: `src/platforms/`.

2. **Obsidian upload adapter**
   - Write `.md` + assets directly into an Obsidian vault folder.
   - Files: `src/core/upload/adapters/obsidian_adapter.py`, `src/core/upload/factory.py`.

3. **Configurable output templates with matching mechanical validation**
   - Let users define a custom Markdown template in config (required headings, metadata block fields, heading hierarchy rules).
   - AI rewrites according to the configured template; the same template drives deterministic post-rewrite validation.
   - Builds on the metadata-driven validator introduced in `src/core/review/prompt_metadata.py` and `src/core/review/review_validation.py`.
   - Files: `src/core/config/schema.py`, `src/core/review/prompt_metadata.py`, `src/core/review/review_validation.py`, `prompts/`.

---

## 🟡 Medium Bets (moderate effort, significant value)

1. **Browser extension / bookmarklet**
   - One-click "Send to Noosphere" for the current page.
   - New directory: `extension/`.

2. **Notion upload adapter**
   - Create / update Notion pages via the Notion API.
   - Files: `src/core/upload/adapters/notion_adapter.py`.

3. **X/Twitter media download**
   - Currently text-only MVP. Download images and videos for a complete archive.
   - File: `src/platforms/x/x_extractor.py`.

4. **PDF extraction support**
   - Use `pdfplumber` or `marker` to extract text and images from PDF articles / reports.
   - New directory: `src/platforms/pdf/`.

5. **Tagging / folder rules**
   - Configurable rules like: "if URL contains `python`, upload to `/Python/` folder in SiYuan."
   - Files: `src/core/config/schema.py`, `src/core/upload/`.

6. **Read-later import**
   - Import from Pocket / Instapaper / Readwise API or export files, then run the Noosphere pipeline on each item.
   - New file: `src/integrations/readwise.py` (or generic import module).

7. **Full-text search across saved articles**
   - Build a local index (e.g., SQLite FTS or tiny Whoosh) over `outputs/*/reviewed.md`.
   - New directory: `src/search/`.

8. **Email archive copy**
   - When sending an article by email, optionally also save a copy back to the note platform.
   - Files: `src/cli.py` (email command), `src/pipelines/upload.py`.

---

## 🔴 Big Bets (high effort, strategic differentiation)

1. **Conversational AI review interface**
   - Instead of batch rewriting the whole article, let the user chat with the AI:
     "shorten this section", "add a comparison table", "explain this term".
   - New module: `src/review/conversational.py`.

2. **Semantic search + local vector index**
   - Embed all extracted articles and support natural-language queries across saved content.
   - New directory: `src/search/`, plus `src/integrations/embedding_client.py`.

3. **Mobile app or PWA**
   - Most article discovery happens on mobile. A share-sheet target would transform usage.
   - New project scope / repository.

4. **Auto-tagging and knowledge graph**
   - Use AI to extract entities, topics, and relationships; build a graph view in SiYuan or standalone.
   - New directory: `src/knowledge/`.

5. **Plugin system for extractors and adapters**
   - Allow users to write Python plugins without modifying core code.
   - Extend `src/core/registry.py` with a plugin discovery path.

6. **Multi-user / team workspace**
   - Shared article queues, comments, and curation for teams.
   - New directory: `src/team/`.

---

## Notes

- The strategic moat of Noosphere is the **AI-cleaning pipeline + Chinese-platform extractors + note-platform integration**.
- The biggest user-facing gaps today are: (1) no batch/dashboard UX, (2) limited source/destination coverage, (3) no mobile/browser entry point, (4) no archive/read-later management.
- After the current quick wins, the next most impactful cluster is **Obsidian adapter + Substack/Medium/GitHub extractors + a lightweight TUI**.
