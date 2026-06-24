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
