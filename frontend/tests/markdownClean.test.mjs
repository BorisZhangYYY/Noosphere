import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import ts from 'typescript';
const source = readFileSync(new URL('../src/markdownClean.ts', import.meta.url), 'utf8');
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } });
const { cleanPassage, cleanPassageBlocks } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`);

test('strips image syntax and keeps a placeholder', () => {
  const { text } = cleanPassage('前文 ![image 03](assets/image_03.png) 后文', [], '[图片]');
  assert.equal(text, '前文 [图片] 后文');
});

test('drops header metadata lines and blockquote markers', () => {
  const { text } = cleanPassage('> Platform: 微信公众号\n> Author: 卡兹克\n> 真正的引用保留\n正文', []);
  assert.equal(text, '真正的引用保留\n正文');
});

test('keeps link anchor text and drops url', () => {
  const { text } = cleanPassage('请看[这篇文章](https://example.com/a?x=1)的内容', []);
  assert.equal(text, '请看这篇文章的内容');
});

test('strips heading markers and emphasis', () => {
  const { text } = cleanPassage('## AI 摘要\n- 本文认为**大模型**会赢', []);
  assert.equal(text, 'AI 摘要\n本文认为大模型会赢');
});

test('reprojects highlights onto cleaned text', () => {
  const raw = '开头 **关键词** 结尾';
  const start = raw.indexOf('关键词');
  const { text, highlights } = cleanPassage(raw, [[start, start + 3]]);
  assert.equal(text, '开头 关键词 结尾');
  assert.deepEqual(highlights, [[3, 6]]);
  assert.equal(text.slice(3, 6), '关键词');
});

test('highlights survive a dropped image before the match', () => {
  const raw = '![a](x.png)关键词命中';
  const start = raw.indexOf('关键词');
  const { text, highlights } = cleanPassage(raw, [[start, start + 3]], '[图片]');
  assert.equal(text, '[图片]关键词命中');
  assert.equal(highlights.length, 1);
  assert.equal(text.slice(highlights[0][0], highlights[0][1]), '关键词');
});

test('compacts empty lines left by images without moving the match', () => {
  const raw = '  开头\n\n![图](assets/image.png)\n\n\n\n关键词  ';
  const start = raw.indexOf('关键词');
  const { text, highlights } = cleanPassage(raw, [[start, start + 3]], '');
  assert.equal(text, '开头\n\n关键词');
  assert.equal(text.slice(...highlights[0]), '关键词');
});

test('cleans a link truncated mid-url by the passage window', () => {
  const { text } = cleanPassage('关键证据见[这篇分析](https:/', [], '[图片]');
  assert.equal(text, '关键证据见这篇分析');
});

test('drops horizontal-rule-only lines', () => {
  const { text } = cleanPassage('上文\n---\n下文', [], '[图片]');
  assert.equal(text, '上文\n下文');
});

test('keeps highlights aligned after dropped metadata lines', () => {
  const raw = '> Platform: 微信公众号\n正文里的关键词';
  const start = raw.indexOf('关键词');
  const { text, highlights } = cleanPassage(raw, [[start, start + 3]], '[图片]');
  assert.equal(text, '正文里的关键词');
  assert.deepEqual(highlights, [[4, 7]]);
  assert.equal(text.slice(highlights[0][0], highlights[0][1]), '关键词');
});

test('preserves UTF-16 offsets when emoji precede a highlight', () => {
  const raw = '😀 关键词';
  const start = raw.indexOf('关键词');
  const { text, highlights } = cleanPassage(raw, [[start, start + 3]], '[图片]');
  assert.deepEqual(highlights, [[3, 6]]);
  assert.equal(text.slice(highlights[0][0], highlights[0][1]), '关键词');
});

test('renders search excerpt structure while keeping its match highlight', () => {
  const raw = '## AI 摘要\n\n文章以“拉塔恩”为原型。\n- 描述拉塔恩的生平。';
  const start = raw.indexOf('拉塔恩');
  const blocks = cleanPassageBlocks(raw, [[start, start + 3]]);

  assert.deepEqual(blocks.map(block => block.kind), ['heading', 'paragraph', 'list']);
  assert.equal(blocks[0].text, 'AI 摘要');
  assert.equal(blocks[1].text.slice(...blocks[1].highlights[0]), '拉塔恩');
  assert.equal(blocks[2].text, '描述拉塔恩的生平。');
});
