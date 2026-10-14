import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import ts from 'typescript';

const source = readFileSync(new URL('../src/blockDrag.ts', import.meta.url), 'utf8');
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } });
const resolved = outputText.replace(/from "([^"]+)"/g, (_, name) => `from ${JSON.stringify(import.meta.resolve(name))}`);
const { markdownBlocks, moveArticleBlockMarkdown, moveListItemMarkdown, moveMappedBlockMarkdown, remapMovedBlock, reconcileBlockEdits, markdownStateKey, headingSectionEnd, articleBlockMovePlan, moveArticleRangeMarkdown, remapMovedRange } = await import(`data:text/javascript;base64,${Buffer.from(resolved).toString('base64')}`);

test('moves the exact paragraph with inline formatting, hard breaks, links and reused image references', () => {
  const paragraph = 'Text **bold** [link](https://example.test/a?q=one)  \nnext ![one](<assets/a b.png> "caption") ![two](<assets/a b.png>)';
  const markdown = `# Title\n\n${paragraph}\n\nSecond paragraph.\n\nThird paragraph.`;
  const next = moveArticleBlockMarkdown(markdown, 1, 3, 'after');
  assert.ok(next.endsWith(paragraph));
  assert.ok(next.indexOf('Second paragraph.') < next.indexOf('Third paragraph.'));
  assert.equal(next.match(/assets\/a b\.png/g).length, 2);
});

test('keeps nested lists, quotation, aligned table, code and HTML byte-for-byte beside a moved paragraph', () => {
  const structures = ['- One\n  - Nested\n- Two', '> Quote\n>\n> Next paragraph', '| A | B |\n| :-- | --: |\n| x | y |', '```js\n## Not a heading\n\nconsole.log(1)\n```', '<div>HTML body</div>'];
  const markdown = ['# Title', 'Moving paragraph.', ...structures, 'Final paragraph.'].join('\n\n');
  const next = moveArticleBlockMarkdown(markdown, 1, markdownBlocks(markdown).length - 1, 'after');
  assert.ok(next.endsWith('Moving paragraph.'));
  for (const block of structures) assert.ok(next.includes(block));
  assert.ok(next.indexOf(structures[0]) < next.indexOf(structures.at(-1)));
});

test('moves the chosen occurrence of duplicate paragraph text', () => {
  const markdown = '# Title\n\nSame.\n\nMiddle.\n\nSame.\n\nLast.';
  const next = moveArticleBlockMarkdown(markdown, 3, 1, 'before');
  assert.deepEqual(markdownBlocks(next).map(block => block.raw), ['# Title', 'Same.', 'Same.', 'Middle.', 'Last.']);
});

test('retains footnote and link definitions when a paragraph changes position', () => {
  const markdown = '# Title\n\nReference [link][source] and note[^one].\n\nOther text.\n\n[source]: https://example.test "Title"\n\n[^one]: Footnote\n\n    Second note paragraph.\n';
  const next = moveArticleBlockMarkdown(markdown, 1, 2, 'after');
  assert.ok(next.includes('Reference [link][source] and note[^one].'));
  assert.ok(next.includes('[source]: https://example.test "Title"'));
  assert.ok(next.includes('[^one]: Footnote\n\n    Second note paragraph.'));
});

test('rejects unchanged boundaries, invalid sources and placement before the title', () => {
  const markdown = '# Title\n\nOne.\n\nTwo.\n\n```txt\nCode\n```';
  for (const args of [[1, 1, 'before'], [1, 2, 'before'], [2, 1, 'after'], [1, 0, 'before'], [0, 2, 'after'], [9, 1, 'after']]) {
    assert.equal(moveArticleBlockMarkdown(markdown, ...args), null);
  }
});

test('moves complete single-line quotes, tables, lists, code and dividers without rewriting their contents', () => {
  const blocks = ['> 单行引用。', '|Left|Right|\n|:---|---:|\n|**one**|two|', '- First\n  - Child\n- Last', '```js\n// A comment\n\nconsole.log(1)\n```', '---'];
  for (const block of blocks) {
    const markdown = ['# Title', 'Before.', block, 'After.'].join('\n\n');
    const next = moveArticleBlockMarkdown(markdown, 2, 1, 'before');
    assert.deepEqual(markdownBlocks(next).map(node => node.raw), ['# Title', block, 'Before.', 'After.']);
    assert.equal(moveArticleBlockMarkdown(next, 1, 3, 'after'), ['# Title', 'Before.', 'After.', block].join('\n\n'));
  }
});

test('rejects a movement that would silently merge distinct list blocks', () => {
  const markdown = ['# Title', '- Item', 'Separating paragraph.', '- Other item', 'Last.'].join('\n\n');
  assert.equal(moveArticleBlockMarkdown(markdown, 2, 4, 'after'), null);
});

test('moves one list item together with nested lists, task states, formatting and image occurrences', () => {
  const first = '- [x] **First** ![one](assets/a.png)\n  - Child ![two](assets/a.png)';
  const markdown = `# Title\n\n${first}\n- [ ] Second\n- [ ] Third\n\nEnd.`;
  const next = moveListItemMarkdown(markdown, [1, 0], [1, 2], 'after');
  assert.equal(next, `# Title\n\n- [ ] Second\n- [ ] Third\n${first}\n\nEnd.`);
  assert.equal(moveListItemMarkdown(next, [1, 2], [1, 0], 'before'), markdown);
});

test('moves nested siblings without flattening their parent or changing reference definitions', () => {
  const markdown = '# Title\n\n- Parent\n  - First [link][ref]\n  - Second\n- Other\n\n[ref]: https://example.test';
  const next = moveListItemMarkdown(markdown, [1, 0, 1, 0], [1, 0, 1, 1], 'after');
  assert.equal(next, markdown.replace('  - First [link][ref]\n  - Second', '  - Second\n  - First [link][ref]'));
});

test('retains loose item paragraphs, code indentation and CRLF', () => {
  const first = '- First\r\n\r\n  Second paragraph.\r\n\r\n  ```js\r\n  console.log(1)\r\n  ```';
  const markdown = `# Title\r\n\r\n${first}\r\n\r\n- Last\r\n\r\nEnd.`;
  const next = moveListItemMarkdown(markdown, [1, 0], [1, 1], 'after');
  assert.equal(next, `# Title\r\n\r\n- Last\r\n\r\n${first}\r\n\r\nEnd.`);
});

test('preserves ordered-list start and adjusts continuation indentation when marker widths change', () => {
  const markdown = '# Title\n\n9. First\n   - Child\n10. Second\n11. Third\n\nEnd.';
  const next = moveListItemMarkdown(markdown, [1, 0], [1, 2], 'after');
  assert.equal(next, '# Title\n\n9. Second\n10. Third\n11. First\n    - Child\n\nEnd.');
  assert.equal(moveListItemMarkdown(next, [1, 2], [1, 0], 'before'), markdown);
});

test('list-item movement rejects no-ops, invalid items and different parents', () => {
  const markdown = '# Title\n\n- Parent\n  - Child\n- Other\n\nParagraph.\n\n- Separate';
  for (const [source, target, side] of [[[1, 0], [1, 0], 'after'], [[1, 0], [1, 1], 'before'], [[1, 2], [1, 0], 'before'], [[1, 0], [3, 0], 'before'], [[1, 0], [1, 0, 1, 0], 'before'], [[2, 0], [2, 1], 'after']]) {
    assert.equal(moveMappedBlockMarkdown(markdown, source, target, side), null);
  }
});

test('pending cell and list edits reconcile while preserving untouched code and table syntax', () => {
  const original = '# Title\n\n- First\n- Second\n\n|a|b|\n|---|---|\n|x|y|\n\n~~~js\ncode()\n~~~';
  const rendered = original.replace('|a|b|\n|---|---|\n|x|y|', '| a | b |\n| --- | --- |\n| x | y |');
  const edited = rendered.replace('Second', 'Edited second').replace('| x | y |', '| edited | y |');
  const next = reconcileBlockEdits(original, rendered, edited);
  assert.ok(next.includes('- First\n- Edited second'));
  assert.ok(next.includes('| edited | y |'));
  assert.ok(next.endsWith('~~~js\ncode()\n~~~'));
});

test('does not merge adjacent paragraphs when moving the last paragraph without a trailing newline', () => {
  const next = moveArticleBlockMarkdown('# Title\n\nFirst.\n\nLast.', 2, 1, 'before');
  assert.deepEqual(markdownBlocks(next).map(block => block.raw), ['# Title', 'Last.', 'First.']);
});

test('preserves CRLF and Unicode paragraph content', () => {
  const next = moveArticleBlockMarkdown('# 标题\r\n\r\n段落 😀\r\n下一行\r\n\r\n末尾段落', 1, 2, 'after');
  assert.ok(next.endsWith('段落 😀\r\n下一行'));
  assert.equal(next.replaceAll('\r\n', '').includes('\n'), false);
});

test('selection endpoints follow both the moved paragraph and surrounding blocks', () => {
  assert.deepEqual([0, 1, 2, 3].map(index => remapMovedBlock(index, 1, 4)), [0, 3, 1, 2]);
  assert.deepEqual([0, 1, 2, 3].map(index => remapMovedBlock(index, 3, 1)), [0, 2, 3, 1]);
});

test('pending typing is merged without rewriting unrelated Markdown formatting', () => {
  const original = '# Title\n\nText.\n\n|a|b|\n|---|---|\n|x|y|\n\n```py\n# code\n\nprint(1)\n```\n';
  const rendered = original.replace('|a|b|\n|---|---|\n|x|y|', '| a | b |\n| --- | --- |\n| x | y |');
  const edited = rendered.replace('Text.', 'Text. New typing.');
  assert.equal(reconcileBlockEdits(original, rendered, edited), original.replace('Text.', 'Text. New typing.'));
  assert.equal(reconcileBlockEdits(original, rendered, rendered), original);
});

test('new paragraphs survive reconciliation and changed footnote text stays with its coherent definitions', () => {
  const original = '# Title\n\nNote[^name].\n\n[^name]: Footnote.';
  const rendered = '# Title\n\nNote[^1].\n\n[^1]: Footnote.';
  const edited = rendered.replace('Note[^1].', 'Edited note[^1].');
  assert.equal(reconcileBlockEdits(original, rendered, edited), edited);
  assert.equal(reconcileBlockEdits(original, rendered, rendered + '\n\nNew paragraph.'), rendered + '\n\nNew paragraph.');
});

test('history identifies final newline variants without swallowing meaningful trailing spaces', () => {
  assert.equal(markdownStateKey('Text.\n'), markdownStateKey('Text.\r\n'));
  assert.notEqual(markdownStateKey('Text.  \n'), markdownStateKey('Text.\n'));
  const original = '# Title\n\nText.\n';
  assert.ok(reconcileBlockEdits(original, original, '# Title\n\nText.  \n').includes('Text.  '));
});


test('heading sections include lower headings and structural content, excluding terminal definitions', () => {
  const markdown = '# Title\n\n## Alpha\n\nA.\n\n### Child\n\n- Item\n\n## Beta\n\nB.\n\n[ref]: https://example.test\n\n[^one]: Note';
  const blocks = markdownBlocks(markdown);
  assert.equal(headingSectionEnd(blocks, 1), 5);
  assert.equal(headingSectionEnd(blocks, 3), 5);
  assert.equal(headingSectionEnd(blocks, 5), 7);
  assert.equal(blocks[1].depth, 2);
});

test('an expanded heading moves alone while a folded section retains exact nested source and CRLF', () => {
  const section = ['## Alpha', 'A **bold** [link][ref].', '### Child', '- Item ![one](assets/a.png)\n  - Nested', '|a|b|\n|---|---|\n|x|y|', '~~~js\n## Not a heading\n\ncode()\n~~~'].join('\n\n');
  const markdown = ['# Title', section, '## Beta', 'B.', '[ref]: https://example.test'].join('\n\n').replaceAll('\n', '\r\n');
  const blocks = markdownBlocks(markdown), end = headingSectionEnd(blocks, 1);
  const alone = moveArticleBlockMarkdown(markdown, 1, 2, 'after');
  assert.ok(alone.indexOf('A **bold**') < alone.indexOf('## Alpha'));
  const next = moveArticleRangeMarkdown(markdown, 1, end, end + 1, 'after');
  assert.ok(next.includes(section.replaceAll('\n', '\r\n')));
  assert.ok(next.indexOf('B.') < next.indexOf('## Alpha'));
  assert.ok(next.endsWith('[ref]: https://example.test'));
  assert.equal(next.replaceAll('\r\n', '').includes('\n'), false);
});

test('collapsed section destinations skip full chapters and reject absorbing unrelated content', () => {
  const markdown = '# Title\n\n## A\n\nA.\n\n### Child\n\nChild.\n\n## B\n\nB.\n\n## C\n\nC.';
  const blocks = markdownBlocks(markdown);
  assert.deepEqual(articleBlockMovePlan(blocks, 1, 5, 'after', new Set([1])), {source: 1, end: 5, target: 6, side: 'after', insertion: 7});
  assert.equal(moveArticleRangeMarkdown(markdown, 1, 5, 5, 'after'), null);
  assert.ok(moveArticleRangeMarkdown(markdown, 1, 5, 6, 'after'));
  assert.equal(moveArticleRangeMarkdown(markdown, 1, 5, 3, 'before'), null);
  assert.equal(articleBlockMovePlan(blocks, 7, 3, 'after', new Set([1])).target, 4);
});

test('range movement remaps all selection and fold addresses including duplicate headings', () => {
  const markdown = '# Title\n\n## Same\n\nFirst.\n\n## Same\n\nSecond.\n\n## End\n\nLast.';
  const next = moveArticleRangeMarkdown(markdown, 3, 5, 1, 'before');
  assert.deepEqual(markdownBlocks(next).map(block => block.raw), ['# Title', '## Same', 'Second.', '## Same', 'First.', '## End', 'Last.']);
  assert.deepEqual([0,1,2,3,4,5,6].map(index => remapMovedRange(index, 3, 5, 1)), [0,3,4,1,2,5,6]);
  assert.deepEqual([0,1,2,3,4,5,6].map(index => remapMovedRange(index, 1, 3, 5)), [0,3,4,1,2,5,6]);
});


test('a collapsed chapter can move after the article introduction without moving to the document end', () => {
  const markdown = '# Title\n\nIntroduction.\n\n## A\n\nA.\n\n## B\n\nB.';
  const blocks = markdownBlocks(markdown);
  const plan = articleBlockMovePlan(blocks, 4, 0, 'after', new Set([4]));
  assert.equal(plan.target, 1);
  assert.equal(plan.insertion, 2);
  assert.equal(moveArticleRangeMarkdown(markdown, 4, 6, plan.target, plan.side).trimEnd(), '# Title\n\nIntroduction.\n\n## B\n\nB.\n\n## A\n\nA.');
  assert.equal(moveArticleRangeMarkdown(markdown, 2, 4, articleBlockMovePlan(blocks, 2, 1, 'after', new Set([2])).target, 'after'), null);
});
