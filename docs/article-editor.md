# Article editor

Open an article and choose **Edit / 编辑** to edit its reviewed text. Reading mode keeps the continuous article layout; block controls appear only while editing.

## Move a block

Hover over a paragraph, body heading, list item, quotation, table or code block, or place the cursor inside it. You can also enter anywhere in the visible left margin directly and move vertically between blocks or across their gaps; entering the text first is unnecessary. A two-column six-dot handle appears in the fixed leftmost gutter column, and a subtle outline identifies everything that will move. Single-line paragraphs and quotations use the same controls as longer blocks. Moving left from any line of a multiline block keeps its controls available.

Drag the handle to a new position. The insertion line shows the gap where the complete block will be placed. Near the reading area's upper or lower edge, the article scrolls automatically. Release to move the block; press **Escape** to cancel. Dropping beside the block's current position leaves the draft unchanged.

Blocks retain their formatting, links and embedded images. Tables move with all rows and cells, quotations with their full contents, and code with its language and indentation. Blocks are inserted before or after other complete blocks. The article title stays at the beginning.

## Lists and list items

Hovering a list item selects that item, including its child lists and other nested contents. Move it up or down among siblings in the same list. Nested items can also move among their own siblings. Ordered lists retain their starting number and update item numbering and continuation indentation after movement.

The outline includes the list marker, while the handle sits farther to its left. Bullets, numbers and task checkboxes remain visible as you move toward the handle.

Two six-dot grips appear together on the active row: the left grip, enclosed by grouping brackets with a subtle accent background, moves the complete outer list between article blocks; the plain grip immediately to its right moves the current item. Their columns stay fixed when selecting nested items. The entire left margin and indentation between the grips and the item remain selectable, so moving from the item grip to the list grip keeps the active row available. Hover or focus either grip to see its boundary, then drag it directly or use its direction buttons. Nested items still move within their own sibling list.

## Headings and folding

Body headings have a movement grip and, when they have content, a small fold triangle. A section extends through all following text and lower-level headings until the next heading at the same or a higher level. Click the triangle to fold or expand that section.

An expanded heading moves alone. A folded heading moves together with its complete section, including nested headings, lists, tables, code and images. Section movement uses chapter boundaries so it does not absorb unrelated destination content. Nested sections retain their own fold state when a parent expands or moves.

Folding changes the display without changing Markdown or making the draft dirty. Outline, search and quote navigation reveal hidden destinations. Reading mode shows the complete article. Fold state is retained while the editor is open; reopening the article expands it. The article's assembled title remains anchored.

## Keyboard and touch

Focus the handle and press **Alt + Up/Down** to move the selected block one position at a time. Alternatively, click the handle to reveal compact up/down buttons. On a touch screen, tap the block, then its handle to use those buttons. The rest of the article continues to scroll normally.

Use **Ctrl/Command + Z** to undo and **Ctrl/Command + Y** to redo. The editor retains the text selection during movement, including selections inside a table or nested list item.

## Save

Choose **Save reviewed Markdown / 保存审阅稿** to persist the new position. Reopening the article uses the saved order. The original captured article, personal reflection and quote interpretations remain independent; protected source metadata and existing save-conflict checks still apply.

List items currently reorder within the same parent list. Moving items into another list or changing indentation remains separate scope. Paragraphs inside quotations retain ordinary text editing; the quotation moves as one complete block. Image removal and recovery continue through the existing image controls.

## Quoted interpretations

In reading mode, select an exact passage to create an independent Markdown interpretation. Resolved quotes have a subtle background and dashed underline. Click the annotated words to open a compact speech bubble above the right end of the quote. Near an edge, it stays inside the viewport and can appear below when there is insufficient space above. Moving the pointer away does not dismiss it; click outside, click the quote again, use the close button, or press Escape to close it. Choose **Edit / 编辑** inside the bubble to modify the interpretation. Long notes scroll inside the bubble while its actions remain available. Touch users can tap the quote, and the article rail retains its quote list and management actions. Saving changes only the interpretation, preserving the article, source text and reflection. An ambiguous or stale quote is not attached to an unrelated sentence.

Search highlights cover all matching article text and remain separate from these private interpretations. Interpretations and reflections do not participate in full-text search.
