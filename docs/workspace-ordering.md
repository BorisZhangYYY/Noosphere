# Knowledge workspace ordering

Drag a category name in the sidebar to change its position among categories at the same level. A category moves with its existing children; dragging does not change its parent or any article's category.

Drag an article title to reorder it among articles in its current category. Unfiled articles can be reordered only within the unfiled group. Category index pages use the same saved order and support ordering their direct articles and child categories.

During dragging, a dashed boundary outlines the allowed group and an insertion line shows the proposed position. Other categories are dimmed. Hovering a forbidden destination shows a red border, a prohibited cursor and an explanation. Dropping there leaves all entries unchanged. Dropping outside the ordering lists is blocked, including over the article editor, so a workspace drag cannot insert text into the draft.

Focus an article title or category name and use **Alt + Up/Down** to reorder it with the keyboard. Entries cannot be moved across category or hierarchy boundaries with that shortcut either.

Order is saved in the workspace database and survives refresh, reopening and language changes. Entries without a saved order retain the original alphabetical category order or article capture order; newly added entries appear after a manually ordered group. Search filters can narrow the visible entries without discarding hidden entries when saving an order.

Sorting does not rewrite article files or AI classification reasons, confidence, source or timestamps. The server checks the current category before accepting an order; if AI has reclassified an article during a drag, the old destination is rejected and the workspace refreshes. Explicit category placement through article controls, MCP or CLI remains a separate operation.

The shared operation is available as MCP `reorder_workspace` and CLI `nsphr collections order`; see the [MCP reference](mcp-reference.md) and [CLI reference](cli-reference.md).
