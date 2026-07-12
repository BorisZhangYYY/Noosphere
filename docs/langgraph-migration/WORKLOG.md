# LangGraph Migration Worklog

> Persistent progress tracker for the `feat/langgraph-migration` branch.  
> Updated at the end of every session so a fresh context can resume exactly here.

## Branch

`feat/langgraph-migration`

## Goal

Replace the custom pipeline + direct API-call architecture with a LangGraph `StateGraph`.  
State is persisted via LangGraph checkpointing (`SqliteSaver` by default, `PostgresSaver` optional).  
`outputs/<article_id>/` remains the protected article workspace as long as current CLAUDE.md rules apply.

## Migration Plan (single branch, sequential commits)

1. **[DONE] Phase 0 — Dependencies & skeleton**
   - Add `langgraph`, `langchain-core` to `pyproject.toml`.
   - Create `src/graph/` package skeleton.
   - Define `ArticleState` TypedDict.

2. **[DONE] Phase 1 — Tool wrappers**
   - Wrap existing functions as LangChain tools:
     - `classify_url`
     - `crawl_url`
     - `download_images`
     - `filter_images`
     - `edit_article`
     - `validate_article`
     - `upload_article`

3. **[DONE] Phase 2 — AI review sub-graph**
   - Port `edit → validate → retry` loop from `src/pipelines/ai_review.py` to a StateGraph.
   - Keep filesystem outputs for backward compatibility.
   - Verify parity against sample articles. **(deferred to Phase 7 runtime validation)**

4. **[DONE] Phase 3 — Full pipeline graph**
   - Model `extract → ai-review → upload` as a single StateGraph.
   - Add `human_review` interrupt and config-driven auto-confirm.
   - Filesystem exports are handled by `crawl`, `download`, and `export_upload` nodes.

5. **[DONE] Phase 4 — CLI migration**
   - Update `src/cli.py` commands to invoke the graph.
   - Preserve existing CLI UX (progress messages, error handling).

6. **[DONE] Phase 5 — TUI migration**
   - Update `src/tui/screens/extract.py`, `review.py`, `upload.py`, `pipeline.py` to use graph.
   - Handle graph progress/status in TUI.

7. **[DONE] Phase 6 — Checkpoint persistence**
   - Wire `SqliteSaver` (default) and `PostgresSaver` (optional).
   - Add config schema entries.

8. **[DONE] Phase 7 — Cleanup & tests**
   - Mark old pipeline modules (`src/pipelines/extract.py`, `ai_review.py`, `upload.py`) as deprecated.
   - Add unit/integration tests for graph nodes and checkpointer factory.
   - Run full verification suite.
   - Runtime parity verification against sample articles remains an ongoing validation task.

## Current Status

- **Completed:** All phases (0–7) of the LangGraph migration.
- **Branch is ready for PR:** the graph-based pipeline replaces the old custom pipeline + direct API-call architecture.
- **Next action:** User review and approval to open a PR from `feat/langgraph-migration` to `main`. Runtime parity verification against live sample articles is recommended before merge.

## Decisions & Notes

- Keep CLI commands unchanged from user perspective.
- Keep `outputs/<article_id>/` as protected workspace; checkpoint is for orchestration state.
- Do not auto-merge PRs; user approval required per CLAUDE.md.
- `edit_article` tool returns `{markdown, model, provider}` so the review report can record the actual AI model/provider used.
- `human_review` node supports `configurable.auto_confirm` and `configurable.skip_human_review` to bypass the interrupt for batch/CI use.
- Added `upload_target` state field and tool parameter so the upload graph honors the CLI `--target` flag.
- Checkpoint backend defaults to SQLite (`.noosphere/checkpoints.sqlite`); set `checkpoint.backend` to `memory` or `postgres` to switch.
- Old pipeline modules in `src/pipelines/` now emit DeprecationWarnings; they will be removed in a future release after parity verification.

## Last Updated

2026-07-12

## Latest Commit on This Branch

`8e1d90e` — feat(graph): add configurable checkpoint persistence
