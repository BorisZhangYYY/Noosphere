import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import ts from 'typescript';

function moduleUrl(file, resolve = name => import.meta.resolve(name)) {
  const { outputText } = ts.transpileModule(readFileSync(new URL(file, import.meta.url), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX }
  });
  const resolved = outputText.replace(/from "([^"]+)"/g, (_, name) => `from ${JSON.stringify(resolve(name))}`);
  return `data:text/javascript;base64,${Buffer.from(resolved).toString('base64')}`;
}
const planUrl = moduleUrl('../src/reviewMarkdown.ts');
const { reviewMarkdownPlan } = await import(planUrl);
const { ReviewMarkdown } = await import(moduleUrl('../src/components/ReviewMarkdown.tsx', name => name === '../reviewMarkdown' ? planUrl : import.meta.resolve(name)));
const normalize = html => html.replace(/>\n+</g, '><');
const render = (text, source = text) => normalize(renderToStaticMarkup(createElement(ReviewMarkdown, { text, source, components: {} })));
const whole = text => normalize(renderToStaticMarkup(createElement(ReactMarkdown, { remarkPlugins: [remarkGfm], children: text })));

test('streaming blocks preserve complete lists, tables, fences, images and duplicate paragraphs', () => {
  const source = ['# 标题', 'Same paragraph.', '- One\n  - Nested **bold**\n- [x] Two', '> Quote\n>\n> Next line', '| A | B |\n| :- | -: |\n| x | y |', '```js\n## Code heading\n\nconsole.log(1)\n```', '![diagram](assets/a.png)', 'Same paragraph.'].join('\n\n');
  assert.equal(render(source), whole(source));
  for (let length = 1; length < source.length; length += 7) {
    assert.equal(render(source.slice(0, length), source), whole(source.slice(0, length)), `Prefix ${length}`);
  }
});

test('cross-block link definitions and document-scoped footnotes retain their meaning', () => {
  const references = '[first][link]\n\n![picture][img]\n\n[link]: https://example.test "Title"\n[img]: assets/image.png';
  assert.equal(render(references), whole(references));
  const notes = 'First[^a].\n\nSecond[^a].\n\n[^a]: A note with **bold**.';
  assert.equal(render(notes), whole(notes));
  assert.equal(reviewMarkdownPlan(notes).blocks.length, 1);
});

test('block offsets stay stable as a later paragraph grows and final rewrites remain supported', () => {
  const source = '## Heading\n\nFirst **complete** paragraph.\n\nLast ';
  const a = reviewMarkdownPlan(source), b = reviewMarkdownPlan(source + 'growing paragraph.');
  assert.deepEqual(a.blocks.slice(0, -1), b.blocks.slice(0, -1));
  assert.equal(render('Replacement text.', source), whole('Replacement text.'));
  assert.equal(render(''), '');
});
