# Noosphere TODO

Product and engineering backlog beyond the current milestone.
Items are grouped by effort / strategic value. Checked items are already done.

## ✅ Done in this milestone

1. Batch URL input for `extract` (`--batch FILE` / single URL).
2. Deduplication before extraction (skip already-extracted URLs unless `--force`).
3. Rich-based progress bars and extraction summary table.
5. Reduce vision API calls in image filtering (file-hash cache + skip description for PROMOTION images).
7. Add `--force` to `ai-review` and `upload`; both now accept a file, directory, or article ID.
8. Better error messages for unsupported URLs (list supported platforms/patterns).

---

## 🟢 Quick Wins (low effort, high user value)

4. **Add a local filesystem archive adapter**
   - Write `reviewed.md` + `assets/` to a dated folder structure without any external platform.
   - Files: `src/core/upload/adapters/local_adapter.py`, `src/core/upload/factory.py`.

5. **Reduce vision API calls in image filtering**
   - Cache image classification results by file hash.
   - Skip the description call when classification is `PROMOTION`.
   - Files: `src/core/review/image_filter.py`.

6. **Add more URL patterns / extractors**
   - Substack (`substack.com/p/*`)
   - Medium (`medium.com/@*`)
   - GitHub discussions
   - Reddit posts
   - Files: `src/platforms/`.

7. **Add `--force` to `ai-review` and `upload`**
   - Allow re-running review or re-uploading an article without manual path gymnastics.
   - Files: `src/cli.py`, `src/pipelines/ai_review.py`, `src/pipelines/upload.py`.

8. **Better error messages for unsupported URLs**
   - Suggest similar supported platforms or show the full supported list.
   - Files: `src/extractor_registry.py`, `src/cli.py`.

---

## 🟡 Medium Bets (moderate effort, significant value)

9. **Browser extension / bookmarklet**
   - One-click "Send to Noosphere" for the current page.
   - New directory: `extension/`.

10. **Simple TUI or web dashboard**
    - List articles with status: extracted / reviewed / uploaded / failed.
    - Allow re-running review or upload from the dashboard.
    - New directory: `src/tui/` or `src/web/`.

11. **Obsidian upload adapter**
    - Write `.md` + assets directly into an Obsidian vault folder.
    - Files: `src/core/upload/adapters/obsidian_adapter.py`, `src/core/upload/factory.py`.

12. **Notion upload adapter**
    - Create / update Notion pages via the Notion API.
    - Files: `src/core/upload/adapters/notion_adapter.py`.

13. **X/Twitter media download**
    - Currently text-only MVP. Download images and videos for a complete archive.
    - File: `src/platforms/x/x_extractor.py`.

14. **PDF extraction support**
    - Use `pdfplumber` or `marker` to extract text and images from PDF articles / reports.
    - New directory: `src/platforms/pdf/`.

15. **Tagging / folder rules**
    - Configurable rules like: "if URL contains `python`, upload to `/Python/` folder in SiYuan."
    - Files: `src/core/config/schema.py`, `src/core/upload/`.

16. **Read-later import**
    - Import from Pocket / Instapaper / Readwise API or export files, then run the Noosphere pipeline on each item.
    - New file: `src/integrations/readwise.py` (or generic import module).

17. **Full-text search across saved articles**
    - Build a local index (e.g., SQLite FTS or tiny Whoosh) over `outputs/*/reviewed.md`.
    - New directory: `src/search/`.

18. **Email archive copy**
    - When sending an article by email, optionally also save a copy back to the note platform.
    - Files: `src/cli.py` (email command), `src/pipelines/upload.py`.

---

## 🔴 Big Bets (high effort, strategic differentiation)

19. **Conversational AI review interface**
    - Instead of batch rewriting the whole article, let the user chat with the AI:
      "shorten this section", "add a comparison table", "explain this term".
    - New module: `src/review/conversational.py`.

20. **Semantic search + local vector index**
    - Embed all extracted articles and support natural-language queries across saved content.
    - New directory: `src/search/`, plus `src/integrations/embedding_client.py`.

21. **Mobile app or PWA**
    - Most article discovery happens on mobile. A share-sheet target would transform usage.
    - New project scope / repository.

22. **Auto-tagging and knowledge graph**
    - Use AI to extract entities, topics, and relationships; build a graph view in SiYuan or standalone.
    - New directory: `src/knowledge/`.

23. **Plugin system for extractors and adapters**
    - Allow users to write Python plugins without modifying core code.
    - Extend `src/core/registry.py` with a plugin discovery path.

24. **Multi-user / team workspace**
    - Shared article queues, comments, and curation for teams.
    - New directory: `src/team/`.

---

## Notes

- The strategic moat of Noosphere is the **AI-cleaning pipeline + Chinese-platform extractors + note-platform integration**.
- The biggest user-facing gaps today are: (1) no batch/dashboard UX, (2) limited source/destination coverage, (3) no mobile/browser entry point, (4) no archive/read-later management.
- After the current quick wins, the next most impactful cluster is **Obsidian adapter + Substack/Medium/GitHub extractors + a lightweight TUI**.
