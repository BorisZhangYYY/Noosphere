# Editor handle placement and hover continuity

Version: v0.3.3.2. Scope frozen: 2026-10-13. Both product issues are implemented and verified locally.

The subsequent workspace-ordering request adds two outcomes to this version, documented in [workspace-ordering-plan.md](workspace-ordering-plan.md).

## Development base

The existing editor worktree at `codex/v0.3.3.1`, commit `b70a4b8`, contains the latest block operations. Remote main remains at `c23561b` and does not yet include that editor. The original main checkout contains unrelated uncommitted changes and is preserved. This iteration is an uncommitted follow-up in the editor worktree; version metadata and release branching remain pending the normal v0.3.3.1 release/merge lifecycle.

## Scoped behavior

1. All block and whole-list handles use a two-column, three-row six-dot grip. The whole-list grip adds enclosing brackets and a subtle accent background to communicate its group scope; individual items retain plain dots. Whole blocks and lists share the fixed leftmost gutter column. List-item handles sit directly in the adjacent right column, including nested items. Headings retain their fold triangle in the second column. Direction buttons align with the selected handle.
2. The visible reading area's entire left margin participates in row selection. Vertical ranges retain nested-item scopes and fill block/list gaps. The previous narrow, first-line-only corridor is removed, so horizontal movement from multiline content or indentation remains selectable through both handles. Handle hover still determines item versus whole-list movement scope.

The editor reserves a 52px left content inset for both handle slots and their clearance. Ordered lists retain extra marker clearance at every viewport width so four- and five-digit numbers do not overlap the fixed grips. Reading mode retains its existing inset and has no block controls. Controls remain outside serialized article content.

## Verification

- 49 frontend tests pass; type-check and production build pass.
- 24 browser cases pass against an isolated real server and built frontend. Existing cases exercise pointer/keyboard/touch movement, item/list scope, heading folding, text selection, undo/redo, source-preserving saves, image protection, reading mode and draft conflicts.
- Three new cases cover 1440px/light, 1024px/dark and 390px/light: direct entry at the visible left edge, horizontal travel below a multiline block's first line, stable gutter alignment across nested/bullet/ordered/task lists, five-digit marker clearance, adjacent grip geometry, slow item-to-list-to-item travel, unchanged Markdown and hidden reading-mode controls.
- After feedback requesting visually distinct group grips, all seven grip/list/gutter browser cases pass again, including the two-column group brackets, whole-list dragging, keyboard/touch operation and stable hover transitions. The updated production build/type-check and diff checks pass; a dark-theme screenshot confirms visible distinction between the group and item grips.
- Existing gutter regressions retain vertical travel across paragraph, heading, list and table gaps and full-list dragging with history/save verification.
- Screenshots at desktop and mobile widths confirm separate grips, intact list markers and no horizontal overflow. Python source compilation, example configuration validation and diff checks pass.

No commit, release or deployment is implied by these local development checks.
