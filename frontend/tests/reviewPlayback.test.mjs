import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import ts from 'typescript';

const { outputText } = ts.transpileModule(readFileSync(new URL('../src/reviewPlayback.ts', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 }
});
const { ReviewPlayback } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`);

test('a large network burst advances across frames and drains to the last character', () => {
  const player = new ReviewPlayback();
  const body = '长文段落🙂e\u0301。\n\n'.repeat(5000);
  player.update(body, 1000);
  assert.equal(player.text, '');
  const lengths = [1016, 1032, 1048, 1064].map(now => player.frame(now).length);
  assert.ok(lengths.every((length, i) => length > 0 && length < body.length && (!i || length > lengths[i - 1])));
  assert.equal(player.pending, true);
  assert.equal(player.frame(6000), body);
  assert.equal(player.pending, false);
});

test('periodic snapshots use their arrival cadence without restarting already shown text', () => {
  const player = new ReviewPlayback();
  player.update('a'.repeat(1000), 1000);
  player.frame(1160);
  player.update('a'.repeat(1000) + 'b'.repeat(3000), 2500);
  const first = player.frame(2516);
  assert.ok(first.length > 1000 && first.length < 1100);
  assert.ok(first.startsWith('a'.repeat(1000)));
  assert.equal(player.frame(4100).length, 4000);
});

test('completion does not flush or abandon the remaining playback queue', () => {
  const player = new ReviewPlayback();
  player.update('first', 1000);
  player.frame(1160);
  player.update('first' + ' final reviewed prose'.repeat(4000), 2000);
  player.frame(2016);
  // The producer can finish here; animation continues independently.
  const before = player.text.length;
  assert.equal(player.pending, true);
  player.frame(2032);
  assert.ok(player.text.length > before);
  assert.equal(player.frame(6000), 'first' + ' final reviewed prose'.repeat(4000));
  assert.equal(player.pending, false);
});

test('graphemes, final whitespace corrections and retained history remain intact', () => {
  const text = '👨‍👩‍👧‍👦e\u0301'.repeat(20);
  const player = new ReviewPlayback();
  player.update(text, 1000);
  const partial = player.frame(1080);
  assert.equal(partial, text.slice(0, partial.length));
  assert.ok(!partial.endsWith('\u200d'));
  player.frame(1160);
  player.update(' \n' + text + '\n', 2000);
  assert.ok(player.text.includes(text));
  assert.equal(player.frame(4000), ' \n' + text + '\n');
  const retained = new ReviewPlayback(text, true);
  assert.equal(retained.text, text);
  assert.equal(retained.pending, false);
});

test('appended Unicode clusters and repeated snapshots preserve continuous playback', () => {
  const player = new ReviewPlayback();
  let text = 'Beginning.\n\n';
  player.update(text, 1000);
  player.frame(1200);
  for (const [index, delta] of ['e', '\u0301', '👨', '\u200d', '👩', '\u200d👧\u200d👦', '\n\nEnd.'].entries()) {
    const now = 2000 + index * 5000;
    text += delta;
    player.update(text, now);
    assert.equal(player.frame(now + 4000), text);
    player.update(text, now + 4001);
    assert.equal(player.text, text);
  }
});
