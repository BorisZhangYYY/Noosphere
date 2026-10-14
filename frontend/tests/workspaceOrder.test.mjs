import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import ts from 'typescript';

const source = readFileSync(new URL('../src/workspaceOrder.ts', import.meta.url), 'utf8');
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } });
const { canReorderWorkspace, orderedWorkspaceArticles } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`);

test('reordering cannot cross category, hierarchy level or entry kind', () => {
  const article = { kind: 'article', id: 'one', scopeId: 'category' };
  assert.equal(canReorderWorkspace(article, { ...article, id: 'two' }), true);
  for (const target of [article, { ...article, id: 'two', scopeId: null }, { ...article, id: 'two', scopeId: 'nested' }, { ...article, kind: 'collection', id: 'two' }]) {
    assert.equal(canReorderWorkspace(article, target), false);
  }
  assert.equal(canReorderWorkspace({ kind: 'collection', id: 'a', scopeId: null }, { kind: 'collection', id: 'b', scopeId: null }), true);
});

test('saved article order wins while unsorted entries retain capture order and input stays unchanged', () => {
  const entries = [{ id: 'new' }, { id: 'second', workspaceOrder: 1 }, { id: 'first', workspaceOrder: 0 }, { id: 'older', workspaceOrder: null }];
  assert.deepEqual(orderedWorkspaceArticles(entries).map(item => item.id), ['first', 'second', 'new', 'older']);
  assert.deepEqual(entries.map(item => item.id), ['new', 'second', 'first', 'older']);
});
