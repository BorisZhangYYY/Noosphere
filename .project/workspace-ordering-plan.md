# Workspace ordering

Version: v0.3.3.2. Scope added on 2026-10-13; implementation verified on 2026-10-14 in the existing editor worktree. These two outcomes join the two editor-handle outcomes, for four scoped product issues.

## Behavior

- Categories reorder among siblings and retain their complete hierarchy and contents. Articles reorder only within their existing category. Unfiled articles form their own root scope.
- Sidebar and category index pages share saved ordering. Keyboard Alt + Up/Down uses the same operation as drag/drop.
- A dashed boundary outlines the allowed scope. Insertion lines identify before/after placement. Foreign scopes are dimmed and forbidden targets receive a red border, prohibited drop effect and feedback.
- Feedback is positioned outside normal flow so drag startup does not move the source row. The original row remains a legal no-op destination. Active workspace drags are blocked at document capture before they can insert text into an editor or other inputs.

## Storage and safeguards

`noosphere_workspace_order` stores kind, entry ID, scope ID and position independently of article classification. Schema creation works without altering existing SQLite/PostgreSQL tables. Ordering transactions serialize concurrent ordering writes and recheck current category ownership. Article lists retain capture ordering for other workspace views and expose a separate `workspaceOrder` for category display. Collection tree order is locale-independent once manually saved; unranked categories use alphabetical fallback.

The relative-movement request uses source, target, side and existing scope. The server derives all active peers itself, including peers hidden by a search filter. Unknown, retired, foreign or reclassified source/target entries are rejected. Ordering never writes collection ownership, reason, confidence, source, placement timestamps or article files. Actual classification changes clear stale saved positions; same-category AI reviews retain the order.

The Web route, MCP `reorder_workspace` and CLI `collections order` call the shared application operation. Existing explicit placement controls remain independent.

## Verification

- 300 backend tests pass, including saved/restored category ordering, nested-parent invariants, AI provenance preservation, rejected cross-category and stale-classification requests, root ordering, no-op writes, scope validation, HTTP behavior and MCP/CLI wiring.
- 51 frontend tests pass; type-check, production build, source compilation, configuration validation and diff checks pass.
- Browser regressions exercise both workspace surfaces, allowed/forbidden drag events, root and hierarchy limits, keyboard ordering, refresh persistence, unchanged source files and attempts to drop into the editable article. A separate native mouse case verifies a stable source position and a persisted article move. Desktop/light and tablet/dark screenshots show the boundaries, insertion lines and forbidden feedback.
- All 27 browser cases pass, including the existing editor, draft, selection, history, reading, image, authentication and route cases.

The local example preview uses an isolated temporary database and six sample articles at port 65164. No release, commit or deployment is implied. Version branching and metadata remain pending v0.3.3.1 release/merge-back.

## Index arrow alignment follow-up

The separate eighth v0.3.3.2 outcome explicitly places each index row's navigation arrow in its final grid column. Categories have an optional count cell while articles do not, so automatic placement previously left article arrows one column inward. Both desktop and narrow grids now use the final column, retaining the same 10px right inset. Browser geometry checks on the existing preview pass for all five rows at 1440px, 1024px and 390px, in both themes and each row's hover state. Production build/type-check and diff checks pass. No ordering or article data is changed by this display correction.

## Release handoff — 2026-10-14

Release operations are authorized. v0.3.3.1 publication and PR #45 merge-back are complete, and v0.3.3.2 is prepared from merged main at `cc42f85`. Final production verification is recorded in [release-v0.3.3.2-verification.md](release-v0.3.3.2-verification.md). Earlier development-base and no-publication statements above describe the implementation phase.
