import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import ts from 'typescript';
const source = readFileSync(new URL('../src/imageDrag.ts', import.meta.url), 'utf8');
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } });
const { preserveDraggedImageReferences, insertionWouldMove, dropMarkerBounds, nearestDragBlock, dragScrollVelocity, dragScrollDistance } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`);

test('gap targeting chooses the nearest block edge and handles article bounds', () => {
  const blocks = [{ top: 20, bottom: 50 }, { top: 80, bottom: 300 }, { top: 340, bottom: 400 }];
  assert.equal(nearestDragBlock([], 100), -1);
  for (const y of [-100, 20, 49, 51, 65]) assert.equal(nearestDragBlock(blocks, y), 0);
  for (const y of [66, 80, 200, 300, 320]) assert.equal(nearestDragBlock(blocks, y), 1);
  for (const y of [321, 340, 399, 1000]) assert.equal(nearestDragBlock(blocks, y), 2);
});

test('edge scrolling ramps up toward either edge and stops in the reading area', () => {
  assert.equal(dragScrollVelocity(50, 50, 650), -480);
  assert.equal(dragScrollVelocity(78, 50, 650), -240);
  assert.equal(dragScrollVelocity(350, 50, 650), 0);
  assert.equal(dragScrollVelocity(622, 50, 650), 240);
  assert.equal(dragScrollVelocity(750, 50, 650), 480);
  assert.equal(dragScrollVelocity(80, 50, 110), 0);
});

test('edge scrolling covers the same distance at different refresh rates without jumping after a stall', () => {
  const distance = frames => Array.from({ length: frames }, () => dragScrollDistance(480, 1000 / frames)).reduce((a, b) => a + b, 0);
  assert.ok(Math.abs(distance(60) - distance(120)) < 0.001);
  assert.equal(dragScrollDistance(480, 1000), 24);
  assert.equal(dragScrollDistance(-480, 50), -24);
  assert.equal(dragScrollDistance(480, -1), 0);
});

test('both boundaries beside the dragged image are unchanged positions', () => {
  assert.equal(insertionWouldMove(1, 1), false);
  assert.equal(insertionWouldMove(1, 2), false);
  assert.equal(insertionWouldMove(1, 0), true);
  assert.equal(insertionWouldMove(1, 3), true);
  assert.equal(insertionWouldMove(-1, 1), true);
});

test('a block gap has one marker between its neighbors rather than at either block edge', () => {
  const parent = { top: 0, bottom: 400, left: 10, width: 300 };
  const previous = { top: 80, bottom: 120, left: 30, width: 260 };
  const next = { top: 180, bottom: 350, left: 30, width: 260 };
  assert.deepEqual(dropMarkerBounds(previous, next, parent), { top: 150, left: 30, width: 260 });
  assert.equal(dropMarkerBounds(null, previous, parent).top, 80);
  assert.equal(dropMarkerBounds(next, null, parent).top, 350);
});

test('drag serialization retains exact source image references after reordering', () => {
  const original = 'Point 1\n\n![First](assets/one.png "caption")\n\nPoint 2\n\n![Second](assets/two.png)';
  const candidate = 'Point 1\n\n![Second](/api/v1/articles/id/assets/two.png)\n\nPoint 2\n\n![First](/api/v1/articles/id/assets/one.png)';
  assert.equal(preserveDraggedImageReferences(candidate, original),
    'Point 1\n\n![Second](assets/two.png)\n\nPoint 2\n\n![First](assets/one.png "caption")');
});

test('missing, duplicate and unknown images abort a drag transaction', () => {
  const original = '![a](assets/a.png)\n\n![b](assets/b.png)';
  for (const candidate of ['![a](assets/a.png)', '![a](assets/a.png)\n\n![a](assets/a.png)', '![a](assets/a.png)\n\n![c](assets/c.png)']) {
    assert.equal(preserveDraggedImageReferences(candidate, original), null);
  }
});

test('repeated image references retain their occurrence count and captions', () => {
  const original = '![first](<assets/a b.png>)\n\n![second](<assets/a b.png>)';
  const candidate = '![x](/api/assets/a%20b.png)\n\nText\n\n![y](/api/assets/a%20b.png)';
  assert.equal(preserveDraggedImageReferences(candidate, original),
    '![first](<assets/a b.png>)\n\nText\n\n![second](<assets/a b.png>)');
});

test('moving a reused image preserves the caption attached to that occurrence', () => {
  const original = '![Before](assets/shared.png "before")\n\n![After](assets/shared.png "after")';
  const candidate = '![After](/api/assets/shared.png)\n\nPoint\n\n![Before](/api/assets/shared.png)';
  assert.equal(preserveDraggedImageReferences(candidate, original),
    '![After](assets/shared.png "after")\n\nPoint\n\n![Before](assets/shared.png "before")');
});
