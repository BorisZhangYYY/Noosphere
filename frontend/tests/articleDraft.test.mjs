import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import ts from 'typescript';
const source = readFileSync(new URL('../src/articleDraft.ts', import.meta.url), 'utf8');
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext } });
const { articleDraftReducer: reduce, emptyArticleDraft } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`);
const initial = () => reduce(emptyArticleDraft, { type: 'receive', articleId: 'one', text: 'original', revision: 'r1', hasImageChanges: false });
test('refreshes and reflection updates preserve unsaved prose and its base revision', () => {
  const dirty = reduce(initial(), { type: 'edit', text: 'unsaved' });
  const refreshed = reduce(dirty, { type: 'receive', articleId: 'one', text: 'changed remotely', revision: 'r2', hasImageChanges: false });
  assert.equal(refreshed.text, 'unsaved');
  assert.equal(refreshed.revision, 'r1');
});
test('typing during save remains dirty after acknowledgement', () => {
  const typed = reduce(initial(), { type: 'edit', text: 'more typing' });
  const saved = reduce(typed, { type: 'saved', articleId: 'one', submitted: 'submitted', text: 'normalized', revision: 'r2' });
  assert.equal(saved.text, 'more typing');
  assert.equal(saved.saved, 'normalized');
  assert.equal(saved.revision, 'r2');
});
test('clean drafts refresh, new articles reset, old save responses cannot leak', () => {
  const refreshed = reduce(initial(), { type: 'receive', articleId: 'one', text: 'fresh', revision: 'r2', hasImageChanges: false });
  assert.equal(refreshed.text, 'fresh');
  const other = reduce(refreshed, { type: 'receive', articleId: 'two', text: 'other', revision: 'r1', hasImageChanges: false });
  assert.deepEqual(reduce(other, { type: 'saved', articleId: 'one', submitted: 'fresh', text: 'late', revision: 'r3' }), other);
});
test('image-only edits preserve the base revision', () => {
  const state = initial();
  assert.deepEqual(reduce(state, { type: 'receive', articleId: 'one', text: 'fresh', revision: 'r2', hasImageChanges: true }), state);
});
