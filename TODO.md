# Noosphere TODO

This file contains only unresolved, deliberately deferred, or release-blocking work. Completed user-visible changes belong in `CHANGELOG.md`.

## v0.3.2.6 — Article workspace consistency and editor reliability

Goal: make article reading and editing share one stable layout while improving workbench loading, protected-image operations, and responsive inspection-rail behavior.

- [x] **Reading and editing parity.** Render the same Markdown title and content geometry in both modes and shift the article copy slightly left for better optical balance.
- [x] **Workbench loading efficiency.** Keep the existing Vditor instance across mode and theme changes and request only the editable article body needed by the workbench.
- [x] **Protected-image editing.** Remove Vditor's conflicting structural popovers, prevent destructive keyboard transactions from reaching protected images, and provide explicit image movement and recoverable state controls.
- [x] **Responsive inspection collapse.** Keep the article body in the flexible content column when the inspection rail is collapsed at tablet and small-laptop widths.
- [x] **Reflection heading hierarchy.** Keep “My Reflections” as the level-two section heading and recommend level-three Markdown headings inside the reflection, including for AI-polished output.

### Release gates

- [x] Frontend type-check and production build pass; Python compile, configuration JSON validation, and the complete test suite pass.
- [x] The frontend production dependency audit reports zero vulnerabilities; build-only development advisories are reviewed as non-runtime.
- [x] Visual smoke tests pass for read/edit parity, image controls, protected-image keyboard behavior, hidden Vditor popovers, and inspection-rail collapse.
- [x] Version metadata and changelog are prepared for `v0.3.2.6`; local Superpowers plans remain excluded from Git.
- [x] The production Docker image builds and passes a local container smoke test.
- [ ] Create the `v0.3.2.6` tag and publish release artifacts after explicit approval.

## v0.3.2.3 — Markdown reflections and anchored reading quotes

Goal: make personal reading notes fully Markdown-aware and let readers attach durable interpretations to exact passages without changing the reviewed article.

- [x] **Markdown reflection rendering.** Add an explicit Edit Markdown / Rendered Preview mode to the reflection dialog and apply one complete, responsive Markdown style system to saved reflections, draft previews, and AI-polished previews.
- [x] **Anchored reading quotes.** In read-only mode, let users select article text and create an independent Markdown interpretation. Persist the exact quote with stable prefix/suffix context and occurrence metadata, decorate resolved passages with a dashed underline, open the interpretation by clicking the passage, and provide count, navigation, editing, and deletion in the article inspection rail. Keep quote annotations out of `raw.md`, `reviewed.md`, `reflection.md`, and uploads; expose the same CRUD data through Web, MCP, and CLI.

### Release gates

- [x] Selection works across inline formatting and repeated sentences; stale anchors remain manageable instead of attaching to the wrong passage.
- [x] Frontend type-check and production build pass; Python compile, configuration JSON validation, and the complete test suite pass.
- [x] Visual smoke tests pass for creation, Markdown preview, clickable underlines, rail navigation/edit/delete, both themes/locales, and desktop/mobile layouts.
- [x] README, user guides, bundled skill, changelog, and workspace-boundary docs describe `annotations.json` and the quote workflow.

## v0.3.2.2 — Per-article reflections with AI polish

Goal: let users write a personal reflection on each reviewed article, polish it with the reviewing model in a floating dialog, and control whether the reflection travels with the uploaded document.

- [x] **Per-article reflections with AI polish.** Keep reflections out of `reviewed.md` in a sidecar `reflection.md` that is rendered as a dedicated section below the article body, written and polished through a floating dialog triggered from the article inspection rail. The dialog asks the model that performed the AI review (recorded in `review.json`, falling back to the active provider) to polish the reflection using only the article and the user's own reflection as context — preserving the user's understanding, clearly marking any expanded parts, and overwriting the reflection file on confirmation; each polish is stateless (article + current reflection only, no conversation history). An upload switch in the inspection rail decides whether the reflection travels with the document: when enabled, the uploader appends the reflection as a canonical localized section to a copy of `reviewed.md` and uploads that; when disabled, only the untouched `reviewed.md` is uploaded. Deliver the polish action in Web, CLI (`nsphr reflect`), and MCP through a manually triggered LangGraph node after the AI-review stage.
- [x] **Image-action modal stacking isolation.** Keep image delete and restore confirmation dialogs above the article outline, reader, and inspection rail in every responsive layout so directory/outline chrome never shares or exceeds the modal layer.

### Release gates

- [x] Frontend type-check and production build pass.
- [x] Python compile, configuration JSON validation, and the complete test suite pass.
- [x] Visual smoke tests pass for both themes and locales across desktop, tablet, and mobile: writing and polishing a reflection, uploading with and without the reflection section, and confirming `reviewed.md` stays untouched.
- [x] README, user guides, bundled skill, changelog, and workspace-boundary docs describe the reflection file and workflow.

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

- [ ] **AI evaluation of article reflections.** Deferred: the v0.3.2.2 polish dialog deliberately omits direct model critique and conversation history; a future version may add multi-turn evaluation of the user's reflection.
