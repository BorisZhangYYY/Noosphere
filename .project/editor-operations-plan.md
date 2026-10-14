# Article block operations: implementation notes

Prepared: 2026-10-13. Planned version: `v0.3.3.1`. Status: all eight scoped product issues implemented and verified locally. Release preparation remains in TODO.

## Development base

The original checkout is on `main` at `4985431` and contains uncommitted search and interface work. Remote `main` is at `c23561b`, after the merged `v0.3.2.8` and `v0.3.3.0` releases. The independent managed worktree uses that exact merged commit on `codex/v0.3.3.1`; the original checkout and its uncommitted files are preserved.

The latest release already includes image dragging, list-point image placement, one marker per equivalent gap, original-position no-ops, release-coordinate targeting and frame-coalesced edge scrolling. Reuse those behaviors for paragraph movement.

## Frozen scope

The user specified paragraph dragging and block-level presentation on 2026-10-13, and confirmed a simple interface that adopts only the needed behavior rather than replicating SiYuan's UI. Preview feedback added structural block movement and corrected list control layout before release. Keep the existing Vditor WYSIWYG editor and deliver eight independently testable product outcomes:

| Issue | User outcome | Essential acceptance |
| --- | --- | --- |
| 1. Block-level presentation | The hovered or focused paragraph has a subtle boundary and a gutter handle in edit mode | Existing typography and continuous article layout retained; controls excluded from Markdown; selection, keyboard and touch access preserved |
| 2. Paragraph dragging | Move one complete paragraph between article block boundaries | Formatting, links and embedded image occurrences retained; valid drop marker and edge scrolling; undo/redo and save/reload work |
| 3. Structural movement | Move complete quotations, tables, code, dividers and lists; reorder list items with nested contents | Single-line sources work; whole outer-list movement; sibling item ordering and ordered numbering retained; selection, history and saving work |
| 4. List control layout | List markers and movement handles remain distinct | Outline includes the marker gutter; nested and long-numbered lists stay legible; gradual pointer travel to the handle retains the selected item; desktop and touch movement works |
| 5. Paired list grips | Inner grip moves the item; outer list icon moves the complete list | Both entrances appear simultaneously, with direct pointer, keyboard and touch operation and clear movement boundaries |
| 6. Heading folding | Body sections fold through the next same- or higher-level heading | Complete Markdown retained; folding does not dirty the draft; nested fold state survives; navigation reveals hidden destinations |
| 7. Heading/chapter movement | Expanded headings move alone; folded headings carry their complete section | Raw source, images, fold state, selection, history and saving retained; duplicate headings remain distinct; article title stays anchored |
| 8. Continuous gutter controls | Blocks remain selectable from the left margin, with compact paired grips | Direct gutter entry and vertical travel across gaps work without entering prose first; inner/outer scopes stay distinct; compact group grip preserves pointer, keyboard and touch movement |

Interpret block-level presentation as contextual boundaries and handles within the existing document layout. Keep reading mode visually continuous. Do not introduce permanent paragraph cards, heavy borders or extra editor panels.

Paragraphs, quotations, tables, code, dividers and complete lists move among the article's outermost blocks. Hovering a list item selects that item with its nested contents. Nested items reorder within their own parent; an outer compact list grip selects the entire outer list while the inner grip remains available. The boundary always indicates movement scope. Nested paragraph or cross-list reparenting requires separate scope. The article title stays anchored at the beginning, following the existing image-drop restriction. Existing single-image placement inside list points continues to work.

Dragging a paragraph moves its inline formatting, links and embedded images together. Use the existing recoverable action for image removal. Empty or unsupported structures must not become ambiguous drag sources. A drop at either current boundary is a no-op and does not mark the article dirty.

Body headings fold and move according to the user’s reference screenshots. A folded heading carries content through the next same- or higher-level heading; an expanded heading moves alone. Section destinations use chapter boundaries, keeping introductory prose and global definitions outside accidental movement scopes. Full block menus, slash commands, selection-formatting toolbars, persistent block references/backlinks and arbitrary multiblock selection remain follow-up scope.

## Editor relationship and implementation choice

Noosphere imports `Vditor` directly in `frontend/src/components/MarkdownEditor.tsx` and uses its WYSIWYG mode. SiYuan's editor implementation is `Protyle`. Both use Lute for Markdown parsing/rendering, but their editor DOM, block interactions and document transactions are different layers.

References: [SiYuan Protyle entry](https://github.com/siyuan-note/siyuan/blob/master/app/src/protyle/index.ts), [Protyle Lute initialization](https://github.com/siyuan-note/siyuan/blob/master/app/src/protyle/render/setLute.ts), and [Vditor Lute initialization](https://github.com/Vanessa219/vditor/blob/master/src/ts/markdown/setLute.ts).

Retain Vditor and add a focused block interaction adapter. Its current DOM and Lute serializer already supply semantic block structure; handles and legal movement transactions must be implemented in Noosphere's wrapper. No engine replacement or article storage migration is planned.

SiYuan distinguishes `NodeList` and `NodeListItem` as containers and `NodeTable` as a leaf block. This iteration follows those movement scopes without adopting persistent block IDs or SiYuan's document model. Reference: [official SiYuan structure specification](https://github.com/siyuan-note/siyuan/blob/master/docs/SY-FORMAT.zh-CN.md).

## Existing implementation and consequences

- `frontend/src/components/MarkdownEditor.tsx` hosts Vditor and owns image protection, drag events and annotation decoration. Its toolbar and structural popovers are suppressed. Add handles as a separate presentation layer outside the editable document.
- `frontend/src/imageDrag.ts` supplies reusable boundary, marker and scrolling behavior. Its transaction requires unchanged full-document `textContent`, which is appropriate for moving images. Moving paragraphs changes text order, so validate the permitted block reordering and preserved surrounding structure instead.
- The editor's image guard requires the same image order unless a Markdown state belongs to `imageMoveHistoryRef`. A legitimate paragraph move with an image can change that order. Generalize the accepted transaction/history path rather than disabling protection or accepting arbitrary image reordering.
- Current moves call `setValue`; the paragraph adapter must restore a predictable selection and cooperate with normal undo/redo. Duplicate paragraphs must remain distinct movement sources.
- `frontend/src/articleDraft.ts` and `frontend/src/pages/ArticlePage.tsx` preserve typing during saves and reject stale revisions. Keep the same save contract. Showing a handle does not dispatch a content edit; a valid paragraph move dispatches exactly one update.
- Outline, search and annotations continue to operate on the complete article. Confirm paragraph movement does not expose controls to their text walkers or cause stale anchors to attach to unrelated text.

## Transaction design

Keep block lookup and legal insertion rules independent from pointer events. Represent the source as one complete block or list item and the destination as a sibling boundary. Dragging and keyboard movement call the same transaction operation. Reuse the current frame scheduler and scrolling calculations where their assumptions hold.

Build a candidate from a complete structural snapshot and validate it before committing. Preserve surrounding block order, nested structure, exact image targets, captions, occurrence counts and active/removed state. A generic DOM-to-Markdown round trip can normalize formatting; assess source-range mapping if it changes code, HTML, formulas, footnotes or meaningful prose. Never reorder Markdown by splitting on blank lines, which divides lists, quotations and fenced code incorrectly.

Keep operation controls outside serialized content. Avoid persistent block IDs or wrappers in reviewed Markdown. Rebind the handle after editor rendering and theme/mode changes without rebuilding the editor instance.

## Acceptance scenarios

| Case | Required observation |
| --- | --- |
| Paragraph with emphasis, link and hard break | Complete text and inline meaning retained; predictable focus after movement |
| Paragraph containing an image or repeated image reference | Image occurrences, targets, captions and removal state retained |
| Paragraph moved beside a nested list, quotation, table or code block | Other blocks remain intact and retain their relative order |
| Complete table, quotation or code moved | Full contents and original source formatting retained |
| List item or nested item reordered | Descendants, task states and selection follow the item; ordered list retains its start |
| Paired list grips | Inner item and outer list grips are simultaneously visible; either scope moves directly |
| Expanded heading | Only the selected heading moves; following prose stays in place |
| Folded heading | Complete section moves, including lower-level headings, protected images and structural blocks |
| Nested and duplicate headings | Fold state follows the correct occurrence through movement, undo/redo and subsequent typing |
| Fold without editing | Draft stays clean; full content remains in Markdown and reading mode; outline reveals hidden destinations |
| Formula, footnote and supported HTML around a paragraph | No semantic loss or accidental image mutation during serialization |
| Duplicate paragraph text | The selected occurrence moves; the other occurrence stays in place |
| Original-position drop and Escape | No content edit; marker and drag feedback disappear |
| Pointer release after scrolling | Placement matches the latest visible marker and final pointer coordinates |
| Move, undo, redo, save, reload | Complete content persists; controls never enter Markdown |
| Search and quote navigation after movement | Correct passage found or stale anchor disclosed safely |
| Type during save; another client saves first | New typing remains dirty; stale replacement rejected |
| Chinese input, themes, languages and responsive widths | Composition and selection preserved; keyboard and touch movement usable |

## Verification

Verified on 2026-10-13 in the independent implementation worktree:

- Frontend: 49 tests pass; type-check and production build pass.
- Backend: 292 tests pass. Source compilation and example configuration JSON validation pass.
- Browser: 21 cases pass. They cover pending typing, paragraph movement with inline and repeated images, byte-preserved neighboring lists/tables/code/formulas/HTML, multiple footnote references, undo/redo, revision-aware save/reload, unchanged raw source, protected image deletion and existing image movement/undo. Structural cases verify complete table dragging and selected cell text, quotation/code movement, nested task-list item movement, paired list grips and touch selection of tables and single-line quotations. Additional cases cover duplicate paragraph text, original-position no-ops, Escape cancellation while focus remains outside the editor, edge scrolling/stopping, selected-text preservation and keyboard/touch controls across themes and locales. Composition-marked movement shortcuts are ignored.
- Gutter cases verify direct entry from the left reading margin, continuous vertical travel across paragraph/heading/list/table gaps, nested row selection, compact paired grips, full-list pointer dragging, undo/redo, complete source saving and hidden controls in reading mode at 1440px/light and 1024px/dark.
- Heading cases verify independent expanded-heading movement, folded chapter dragging/touch movement, nested folding, duplicate heading undo/redo followed by typing, full source/image preservation, reading-mode expansion, outline reveals, clean folding and save/reload. Terminal link and footnote definitions stay outside fold ranges and visible block mapping.
- Production dependency audit reports zero vulnerabilities; diff checks pass.
- Visual inspection confirms the block handle and on-demand movement buttons at 1440px, 1024px and 390px widths, including the distinct item/list boundaries. The reading layout and article typography are retained.
- List layout follow-up: geometry assertions and gradual pointer travel verify separate grips and markers. Separate 1440px/light, 1024px/dark and 390px/touch checks verify four- and five-digit numbered markers, simultaneous outer/inner grips, keyboard/touch movement and fold-triangle clearance. Narrow ordered lists reserve enough space for both grips; bullet, nested and task layouts retain their existing presentation.

The browser test suite also received two necessary locator corrections for existing UI changes: Article text backup / Refresh text copy and View in article / the in-article focus marker. These are test maintenance changes rather than new product scope.

Block movement uses parsed Markdown source ranges. A canonical rendering maps visible blocks and nested list items and reconciles unreported typing, while unchanged source spans are retained. Ordered-item movement updates marker widths and continuation indentation, with complete AST validation before applying a candidate. Accepted before/after Markdown states are bounded and paired with their canonical representations so undo/redo does not lose exact image references or rewrite unrelated source formatting. Selection follows Markdown block addresses and text offsets rather than transient editor caret nodes; cell-boundary affinity preserves exact selected text. Controls rebind after editor normalization and remain outside article serialization.

No Docker release check or publication is implied by these implementation results. Version metadata and release notes remain part of the release gates in TODO.

## Implementation structure

1. `frontend/src/blockDrag.ts` owns parsed source ranges, canonical block/list-item mapping, legal insertion, ordered numbering, pending-edit reconciliation and selection remapping.
2. `frontend/src/components/blockControls.ts` owns contextual grips, lightweight boundaries, the heading triangle, pointer capture, keyboard/touch buttons and cancellation.
3. `MarkdownEditor.tsx` connects block transactions to the existing Vditor editor, image protection, bounded structural history and drag scheduler. Parsed drop validation is cached per destination during a drag, including rejection of movements that would merge distinct lists.
4. Dragging and keyboard/touch movement share the same transaction; the existing marker and edge-scroll behavior are reused.
5. `frontend/src/components/headingFolds.ts` owns temporary heading view state, nested hiding, navigation reveals and matching across native history rebuilds. Fold classes are excluded by the serializer; Markdown stays complete. Duplicate headings use nearby content to retain identity before Vditor’s delayed history callback.
6. Pure source-preservation regressions and full browser cases verify new behavior alongside the existing draft, image, search and authentication contracts.

List-item rectangles exclude native outside markers. Their outlines start at the parent list gutter and extend further for wide ordered markers measured with the marker's actual font variants. The presentation layer keeps a stable pointer corridor between content and handle. Cached vertical ranges cover the left reading margin and fill inter-block gaps, including nested list rows. Both grips remain compact beside the active row; the outer list icon identifies the group scope without a full-height bar. Scroll, layout and font changes invalidate the range cache, and reader listeners and timers are removed on teardown.

Keep tests and changelog entries with each implemented outcome. Version metadata and release documentation change only when the scope is implemented and verified. Commits, pushes, pull requests and release operations remain subject to the repository's existing user-authorization rules.

## Release verification — 2026-10-14

The production Dockerfile builds a Linux arm64 verification image (`13f492f7a5ed`) with matching business source and version metadata. The image passes 292 backend tests, isolated PostgreSQL/authentication/revision/restart/source-preservation checks and non-root Chromium rendering. Host verification passes 292 backend, 49 frontend and 21 browser cases. The release is prepared for the tag-triggered amd64 registry build; published artifacts and merge-back are recorded by the GitHub Release and release PR.
