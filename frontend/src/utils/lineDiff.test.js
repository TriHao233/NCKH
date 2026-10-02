import test from 'node:test';
import assert from 'node:assert/strict';
import { diffLines, diffSummary } from './lineDiff.js';

test('line diff marks added and removed lines and keeps the rest', () => {
  const rows = diffLines('a\nb\nc', 'a\nx\nc\nd');
  assert.deepEqual(rows, [
    { type: 'same', text: 'a' },
    { type: 'removed', text: 'b' },
    { type: 'added', text: 'x' },
    { type: 'same', text: 'c' },
    { type: 'added', text: 'd' },
  ]);
  assert.deepEqual(diffSummary(rows), { added: 2, removed: 1 });
});

test('line diff of identical text has no changes', () => {
  assert.deepEqual(diffSummary(diffLines('one\ntwo', 'one\ntwo')), { added: 0, removed: 0 });
});
